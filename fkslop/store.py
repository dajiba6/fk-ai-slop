"""Files under DATA_DIR are the source of truth; everything else is derived from them."""
import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

import yaml

from fkslop import config

_lock = threading.RLock()


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _atomic_write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


# ---------- sources ----------

def load_sources():
    with _lock:
        if not config.SOURCES_FILE.is_file():
            return []
        data = yaml.safe_load(config.SOURCES_FILE.read_text(encoding="utf-8")) or {}
        return data.get("sources") or []


def save_sources(sources):
    with _lock:
        _atomic_write(config.SOURCES_FILE, yaml.safe_dump({"sources": sources}, allow_unicode=True, sort_keys=False))


def get_source(source_id):
    return next((s for s in load_sources() if s["id"] == source_id), None)


def update_source(source_id, **changes):
    with _lock:
        sources = load_sources()
        for source in sources:
            if source["id"] == source_id:
                source.update(changes)
        save_sources(sources)


# ---------- items ----------

def item_id(platform, native_id):
    prefix = {"youtube": "yt", "bilibili": "bili", "xiaohongshu": "xhs", "article": "art", "podcast": "pod"}[platform]
    return f"{prefix}-{native_id}"


def article_native_id(url):
    return hashlib.sha1(url.strip().encode()).hexdigest()[:12]


def split_id(iid):
    prefix, native = iid.split("-", 1)
    platform = {"yt": "youtube", "bili": "bilibili", "xhs": "xiaohongshu", "art": "article", "pod": "podcast"}[prefix]
    return platform, native


def item_dir(iid) -> Path:
    platform, native = split_id(iid)
    return config.ITEMS_DIR / platform / native


def _parse_item_md(text):
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    meta = yaml.safe_load(text[4:end]) or {}
    return meta, text[end + 5:]


def read_item(iid):
    path = item_dir(iid) / "item.md"
    if not path.is_file():
        return None, ""
    return _parse_item_md(path.read_text(encoding="utf-8"))


def write_item(meta, body=None):
    with _lock:
        path = item_dir(meta["id"]) / "item.md"
        if body is None and path.is_file():
            _, body = _parse_item_md(path.read_text(encoding="utf-8"))
        head = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False)
        _atomic_write(path, f"---\n{head}---\n{(body or '').strip()}\n")


def update_item(iid, **changes):
    with _lock:
        meta, body = read_item(iid)
        if meta is None:
            return None
        meta.update(changes)
        write_item(meta, body)
        return meta


def iter_item_ids():
    if not config.ITEMS_DIR.is_dir():
        return
    for platform_dir in config.ITEMS_DIR.iterdir():
        for directory in platform_dir.iterdir():
            if (directory / "item.md").is_file():
                yield item_id(platform_dir.name, directory.name)


def read_transcript(iid):
    path = item_dir(iid) / "transcript.json"
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def write_transcript(iid, cues):
    directory = item_dir(iid)
    _atomic_write(directory / "transcript.json", json.dumps(cues, ensure_ascii=False, indent=0))
    _atomic_write(directory / "transcript.txt", "\n".join(c["text"] for c in cues) + "\n")


def read_summary(iid):
    path = item_dir(iid) / "summary.md"
    return path.read_text(encoding="utf-8") if path.is_file() else None


def write_summary(iid, text):
    _atomic_write(item_dir(iid) / "summary.md", text)


def thumb_path(iid) -> Path:
    return item_dir(iid) / "thumb.jpg"


# ---------- reading state ----------

def load_state():
    with _lock:
        if not config.STATE_FILE.is_file():
            return {"read": [], "later": [], "favorite": []}
        return json.loads(config.STATE_FILE.read_text(encoding="utf-8"))


def set_flag(iid, flag, on):
    with _lock:
        state = load_state()
        values = set(state.get(flag) or [])
        if on:
            values.add(iid)
        else:
            values.discard(iid)
        state[flag] = sorted(values)
        _atomic_write(config.STATE_FILE, json.dumps(state, ensure_ascii=False))
        return state


HISTORY_LIMIT = 1000


def history():
    """Newest view first, capped. Each entry is {"id", "at"}."""
    with _lock:
        state = load_state()
        entries = []
        for entry in state.get("history") or []:
            if isinstance(entry, dict) and entry.get("id"):
                entries.append({"id": entry["id"], "at": entry.get("at") or ""})
        return entries[:HISTORY_LIMIT]


def remember_view(iid):
    """Move this item to the front of the viewing history."""
    with _lock:
        state = load_state()
        entries = [entry for entry in state.get("history") or []
                   if isinstance(entry, dict) and entry.get("id") and entry["id"] != iid]
        entries.insert(0, {"id": iid, "at": now_iso()})
        state["history"] = entries[:HISTORY_LIMIT]
        _atomic_write(config.STATE_FILE, json.dumps(state, ensure_ascii=False))
        return state["history"]


def watch_summary(iid, on):
    """Items in the summary dock, oldest request first."""
    with _lock:
        state = load_state()
        watched = [i for i in state.get("summary_watch") or [] if i != iid]
        if on:
            watched.append(iid)
        if watched != state.get("summary_watch"):
            state["summary_watch"] = watched
            _atomic_write(config.STATE_FILE, json.dumps(state, ensure_ascii=False))
        return watched
