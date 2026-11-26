"""Favorited items exported as self-contained Markdown under DATA_DIR/favorites, for use as agent context.

Derived from item files and state.json like the index: safe to delete and rebuild with `fk favorites`."""
import re

import yaml

from fkslop import config, store
from fkslop.search import timed_url

DIR = config.DATA_DIR / "favorites"
PLATFORM = {"youtube": "YouTube", "bilibili": "B 站", "xiaohongshu": "小红书", "article": "文章", "podcast": "播客"}


def is_favorite(iid):
    return iid in (store.load_state().get("favorite") or [])


def _existing(iid):
    return next(iter(DIR.glob(f"*_{iid}.md")), None) if DIR.is_dir() else None


def _filename(meta):
    def clean(text, limit):
        text = re.sub(r'[\\/:*?"<>|\n\r\t]+', " ", str(text or "")).strip()
        return re.sub(r"\s+", " ", text)[:limit].strip() or "无标题"
    day = str(meta.get("published") or "")[:10] or "unknown"
    return f"{day}_{clean(meta.get('author'), 20)}_{clean(meta.get('title'), 50)}_{meta['id']}.md"


def _clock(seconds):
    seconds = int(seconds or 0)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _transcript(meta, cues):
    """Cues grouped into roughly one-minute paragraphs, each starting with a timed link."""
    out, current = [], None
    for cue in cues:
        if current is None or cue["start"] - current["start"] >= 60:
            current = {"start": cue["start"], "texts": []}
            out.append(current)
        current["texts"].append(cue["text"].strip())
    return "\n\n".join(f"[{_clock(p['start'])}]({timed_url(meta, p['start'])}) {' '.join(p['texts'])}"
                       for p in out)


def render(iid, favorited_at):
    meta, body = store.read_item(iid)
    summary = store.read_summary(iid)
    cues = store.read_transcript(iid)
    head = {
        "id": iid, "title": meta.get("title"), "author": meta.get("author"),
        "platform": PLATFORM.get(meta.get("platform"), meta.get("platform")), "kind": meta.get("kind"),
        "url": meta.get("url"), "published": meta.get("published"), "duration": meta.get("duration"),
        "favorited_at": favorited_at, "has_summary": bool(summary), "has_transcript": bool(cues),
    }
    parts = [f"---\n{yaml.safe_dump(head, allow_unicode=True, sort_keys=False)}---", f"# {meta.get('title')}"]
    if summary:
        summary = re.sub(r"\(#t=(\d+)\)", lambda m: f"({timed_url(meta, int(m.group(1)))})", summary)
        summary = re.sub(r"^(#+) ", r"#\1 ", summary, flags=re.M)
        parts.append(f"## AI 总结\n\n{summary.strip()}")
    if body.strip():
        parts.append(f"## {'正文' if meta.get('kind') == 'article' else '简介'}\n\n{body.strip()}")
    if cues:
        parts.append(f"## 逐字稿\n\n{_transcript(meta, cues)}")
    return "\n\n".join(parts) + "\n"


def refresh(iid):
    """Write, rewrite or remove the item's file to match its favorite flag."""
    old = _existing(iid)
    meta, _ = store.read_item(iid)
    if meta is None or not is_favorite(iid):
        if old:
            old.unlink()
        return
    favorited_at = None
    if old:
        text = old.read_text(encoding="utf-8")
        if text.startswith("---\n"):
            favorited_at = (yaml.safe_load(text[4:text.find("\n---\n", 4)]) or {}).get("favorited_at")
    target = DIR / _filename(meta)
    store._atomic_write(target, render(iid, favorited_at or store.now_iso()))
    if old and old != target:
        old.unlink()


def sync_all():
    """Rebuild the folder from state.json; returns the number of favorites."""
    wanted = set(store.load_state().get("favorite") or [])
    if DIR.is_dir():
        for path in DIR.glob("*.md"):
            if not any(path.name.endswith(f"_{iid}.md") for iid in wanted):
                path.unlink()
    for iid in wanted:
        refresh(iid)
    return len(wanted)
