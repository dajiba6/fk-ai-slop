"""What each queued job does, plus the entry points that put work on the queue."""
import json
import logging
import subprocess
import tempfile
import threading
from datetime import date, timedelta
from pathlib import Path

from fkslop import config, db, favorites, indexer, platforms, store, summary
from fkslop.platforms import feeds, media, net, xiaohongshu, youtube

log = logging.getLogger("fkslop")

PRIO_DEMAND, PRIO_MANUAL, PRIO_SOURCE, PRIO_NEW, PRIO_BACKFILL = 100, 80, 60, 50, 0
RATE_LIMIT_RETRIES = 2
MEMBERS_NOTE = "会员专属，需要在 FK_YOUTUBE_COOKIES_BROWSER 指定的浏览器里登录有会员的 YouTube 账号后重试"
# A small GPU may not hold SenseVoice and the resident embedding model at once: embedding waits during ASR.
GPU_BUSY = threading.Event()


class Retry(Exception):
    def __init__(self, delay, message):
        super().__init__(message)
        self.delay = delay


# ---------- entry points ----------

def default_since():
    return f"{date.today().year}-01-01"


def add_source(url, since=None):
    """since: YYYY-MM-DD; older posts are never fetched. Defaults to January 1 of this year, "" means no limit."""
    kind, url = platforms.classify(url)
    module = platforms.SOURCE_KINDS.get(kind)
    if module is None:
        raise ValueError("这是单个视频链接，请用“投递链接”；来源请填频道 / UP 主主页或 RSS 地址")
    source = module.resolve(url)
    sources = store.load_sources()
    existing = next((s for s in sources if s["id"] == source["id"]), None)
    if existing:
        existing["removed"] = False
    else:
        source.update(added_at=store.now_iso(), removed=False, since=default_since() if since is None else since or None)
        sources.append(source)
    store.save_sources(sources)
    db.enqueue("poll", source["id"], priority=PRIO_SOURCE)
    return source


def set_since(source_id, since):
    """Change the start date and backfill again; posts already fetched are kept."""
    store.update_source(source_id, since=since or None, backfilled_at=None)
    db.enqueue("poll", source_id, priority=PRIO_SOURCE)


def exact_date(platform, entry):
    meta, _ = store.read_item(store.item_id(platform, entry["native_id"]))
    if meta and meta.get("published") and not meta.get("date_approx"):
        return meta["published"]
    try:
        if platform == "youtube":
            published = youtube.published(entry["native_id"], entry.get("format") == "short")
            if published:
                return published
        return media.video_metadata(entry["url"], platform).get("published")
    except Exception:
        log.warning("exact date lookup failed for %s", entry["url"], exc_info=True)
        return None


def undated_since(platform, entries, since):
    """Undated entries (YouTube shorts) are listed newest first: binary-search the first one published
    before `since`, then look up the kept ones too. A borrowed date would sort old shorts to the top of
    the feed until their transcript corrects it."""
    known = {}

    def date_at(i):
        if i not in known:
            known[i] = exact_date(platform, entries[i])
        return known[i]

    if entries:
        date_at(0)
    lo, hi = 0, len(entries)
    while lo < hi:
        mid = (lo + hi) // 2
        found = date_at(mid)
        if found and found[:10] < since:
            hi = mid
        else:
            lo = mid + 1
    kept, bound = [], None
    for i, entry in enumerate(entries[:lo]):
        if date_at(i):
            bound = known[i]
            kept.append({**entry, "published": bound, "date_approx": False})
        else:
            kept.append({**entry, "published": bound, "date_approx": True})
    log.info("%s undated entries: kept %d of %d after %d lookups", platform, lo, len(entries), len(known))
    return kept


def since_filter(platform, entries, since):
    """Drop entries published before `since`. YouTube backfill dates ("3 months ago") are upper bounds,
    so entries that land in the month after the cutoff get their exact date looked up."""
    if not since:
        return entries
    edge = (date.fromisoformat(since) + timedelta(days=31)).isoformat()
    kept = []
    for entry in entries:
        published = (entry.get("published") or "")[:10]
        if not published or published < since:
            continue
        if entry.get("date_approx") and published < edge:
            exact = exact_date(platform, entry)
            if exact:
                if exact[:10] < since:
                    continue
                entry = {**entry, "published": exact, "date_approx": False}
        kept.append(entry)
    return kept + undated_since(platform, [e for e in entries if not e.get("published")], since)


def remove_source(source_id):
    store.update_source(source_id, removed=True)


def poll_all():
    count = 0
    for source in store.load_sources():
        if not source.get("removed"):
            db.enqueue("poll", source["id"], priority=PRIO_SOURCE)
            count += 1
    return count


def submit_url(url):
    kind, url = platforms.classify(url)
    if kind == "xhs_note":
        url = xiaohongshu.expand(url)
        kind = "xhs_user" if "/user/profile/" in url else kind
    if kind in ("youtube_channel", "bilibili_space", "xhs_user"):
        return {"source": add_source(url)}
    if kind == "xhs_note":
        note = xiaohongshu.note(url)
        source_id = f"xhs-{note['user_id']}"
        return {"item": create_note(note, source_id if store.get_source(source_id) else "manual", backfill=False)}
    if kind in ("youtube_video", "bilibili_video"):
        platform = kind.split("_")[0]
        info = media.video_metadata(url, platform)
        prefix = "yt" if platform == "youtube" else "bili"
        source_id = f"{prefix}-{info.get('channel_id')}"
        if not store.get_source(source_id):
            source_id = "manual"
        iid = create_video(platform, info, source_id, backfill=False, priority=PRIO_MANUAL)
        return {"item": iid}
    article = feeds.fetch_article(url)
    iid = create_article({"url": url, **article}, "manual", body=article["body"])
    return {"item": iid}


def demand(iid):
    """The item was opened: move its transcript to the front, or start ASR if it has no subtitles."""
    meta, _ = store.read_item(iid)
    if not meta or meta.get("kind") != "video":
        return
    state = meta.get("transcript")
    if state == "pending":
        db.enqueue("transcript", iid, priority=PRIO_DEMAND)
    elif state in ("none", "failed") or (state == "n/a" and meta.get("platform") == "podcast"):
        if config.ASR_ENABLED:
            queue_asr(iid, PRIO_DEMAND)


def request_transcript(meta):
    iid = meta["id"]
    if meta.get("transcript") == "pending":
        db.enqueue("transcript", iid, priority=PRIO_DEMAND)
    elif config.ASR_ENABLED:
        queue_asr(iid, PRIO_DEMAND)


def queue_asr(iid, priority, sort_ts=0, note=None):
    changes = {"transcript": "asr_queued"}
    if note:
        changes["transcript_note"] = note
    store.update_item(iid, **changes)
    indexer.refresh_row(iid)
    db.enqueue("asr", iid, priority=priority, sort_ts=sort_ts)


def request_summary(iid):
    """A video without a transcript gets one first; the summary job waits for it."""
    meta, _ = store.read_item(iid)
    if meta and meta.get("kind") == "video" and meta.get("transcript") in ("pending", "none", "failed", "n/a"):
        request_transcript(meta)
    db.enqueue("summary", iid, priority=PRIO_DEMAND)


# ---------- item creation ----------

def create_video(platform, entry, source_id, backfill, priority):
    iid = store.item_id(platform, entry["native_id"])
    meta, _ = store.read_item(iid)
    if meta is not None:
        if meta.get("date_approx") and entry.get("published") and not entry.get("date_approx"):
            store.update_item(iid, published=entry["published"], date_approx=False)
            indexer.refresh_row(iid)
        if priority > PRIO_BACKFILL and meta.get("transcript") == "pending":
            db.enqueue("transcript", iid, priority=priority, sort_ts=db.published_ts(meta.get("published")))
        return iid
    meta = {
        "id": iid, "platform": platform, "kind": "video", "native_id": entry["native_id"],
        "source_id": source_id, "title": entry.get("title"), "author": entry.get("author"),
        "url": entry["url"], "published": entry.get("published"), "date_approx": bool(entry.get("date_approx")),
        "duration": entry.get("duration"), "format": entry.get("format", "video"),
        "thumbnail_url": entry.get("thumbnail"), "transcript": "pending", "backfill": backfill,
        "members_only": bool(entry.get("members_only")), "added_at": store.now_iso(),
    }
    store.write_item(meta, entry.get("description") or "")
    indexer.index_item(iid, embed=False)
    sort_ts = db.published_ts(meta["published"])
    if meta["thumbnail_url"]:
        db.enqueue("thumb", iid, priority=priority, sort_ts=sort_ts)
    db.enqueue("transcript", iid, priority=priority, sort_ts=sort_ts)
    return iid


def create_note(entry, source_id, backfill, priority=PRIO_NEW):
    """Xiaohongshu notes are kept as links: title, cover and description. Video notes get a transcript only
    when asked for one ("n/a" until then)."""
    iid = store.item_id("xiaohongshu", entry["native_id"])
    if store.read_item(iid)[0] is not None:
        return iid
    meta = {
        "id": iid, "platform": "xiaohongshu", "kind": "video" if entry["format"] == "video" else "note",
        "native_id": entry["native_id"], "source_id": source_id, "title": entry.get("title"),
        "author": entry.get("author"), "url": entry["url"], "published": entry.get("published"),
        "date_approx": False, "duration": entry.get("duration"), "format": entry["format"],
        "thumbnail_url": entry.get("thumbnail"), "transcript": "n/a", "backfill": backfill,
        "added_at": store.now_iso(),
    }
    store.write_item(meta, entry.get("description") or "")
    indexer.index_item(iid, embed=False)
    if meta["thumbnail_url"]:
        db.enqueue("thumb", iid, priority=priority, sort_ts=db.published_ts(meta["published"]))
    return iid


def create_episode(entry, source_id, backfill, priority=PRIO_NEW):
    """Podcast episodes have no subtitles; ASR runs when the episode is opened or summarized."""
    iid = store.item_id("podcast", entry["native_id"])
    if store.read_item(iid)[0] is not None:
        return iid
    meta = {
        "id": iid, "platform": "podcast", "kind": "video", "native_id": entry["native_id"],
        "source_id": source_id, "title": entry.get("title"), "author": entry.get("author"), "url": entry["url"],
        "audio_url": entry["audio_url"], "published": entry.get("published"), "date_approx": False,
        "duration": entry.get("duration"), "format": "audio", "thumbnail_url": entry.get("thumbnail"),
        "transcript": "n/a", "backfill": backfill, "added_at": store.now_iso(),
    }
    store.write_item(meta, entry.get("description") or "")
    indexer.index_item(iid, embed=False)
    if meta["thumbnail_url"]:
        db.enqueue("thumb", iid, priority=priority, sort_ts=db.published_ts(meta["published"]))
    return iid


def create_article(entry, source_id, body=None, priority=PRIO_NEW):
    iid = store.item_id("article", store.article_native_id(entry["url"]))
    if store.read_item(iid)[0] is not None:
        return iid
    if body is None and len(entry.get("html") or "") > 1500:
        body, _ = feeds.article_from_html(entry["html"], entry["url"])
    meta = {
        "id": iid, "platform": "article", "kind": "article", "native_id": iid.split("-", 1)[1],
        "source_id": source_id, "title": entry.get("title"), "author": entry.get("author"),
        "url": entry["url"], "published": entry.get("published") or store.now_iso(), "date_approx": False,
        "thumbnail_url": entry.get("thumbnail"), "site": entry.get("site"),
        "transcript": "n/a", "body_status": "ok" if body else "pending", "added_at": store.now_iso(),
    }
    store.write_item(meta, body or "")
    indexer.index_item(iid)
    sort_ts = db.published_ts(meta["published"])
    if not body:
        db.enqueue("article", iid, priority=priority, sort_ts=sort_ts)
    if meta["thumbnail_url"]:
        db.enqueue("thumb", iid, priority=priority, sort_ts=sort_ts)
    return iid


def requeue_unfinished(meta):
    iid, sort_ts = meta["id"], db.published_ts(meta.get("published"))
    priority = PRIO_BACKFILL if meta.get("backfill") else PRIO_NEW
    if meta.get("transcript") == "pending":
        db.enqueue("transcript", iid, priority=priority, sort_ts=sort_ts)
    elif meta.get("transcript") == "asr_queued":
        db.enqueue("asr", iid, priority=priority, sort_ts=sort_ts)
    if meta.get("body_status") == "pending":
        db.enqueue("article", iid, priority=priority, sort_ts=sort_ts)
    if meta.get("thumbnail_url") and not store.thumb_path(iid).is_file():
        db.enqueue("thumb", iid, priority=priority, sort_ts=sort_ts)


# ---------- job handlers ----------

def handle_poll(job):
    source = store.get_source(job["target"])
    if not source or source.get("removed"):
        return
    backfill = not source.get("backfilled_at")
    platform = source["platform"]
    try:
        entries = platforms.SOURCES[platform].poll(source, backfill)
    except platforms.RateLimited as exc:
        store.update_source(source["id"], last_error=str(exc))
        raise Retry(1800, str(exc))
    except Exception as exc:
        store.update_source(source["id"], last_error=str(exc)[:300])
        raise
    for entry in since_filter(platform, entries, source.get("since")):
        if platform == "rss":
            create_article(entry, source["id"], priority=PRIO_BACKFILL if backfill else PRIO_NEW)
        elif platform == "xiaohongshu":
            create_note(entry, source["id"], backfill=backfill, priority=PRIO_BACKFILL if backfill else PRIO_NEW)
        elif platform == "podcast":
            create_episode(entry, source["id"], backfill=backfill, priority=PRIO_BACKFILL if backfill else PRIO_NEW)
        else:
            create_video(platform, entry, source["id"], backfill=backfill,
                         priority=PRIO_BACKFILL if backfill else PRIO_NEW)
    changes = {"last_polled": store.now_iso(), "last_error": None, "item_count_seen": len(entries)}
    if platform == "xiaohongshu":
        # Profile requests need a valid xsec_token from this user; keep the newest one so it does not age out.
        changes["xsec_token"] = max(entries, key=lambda e: e["published"])["xsec_token"]
    if backfill:
        changes["backfilled_at"] = store.now_iso()
    store.update_source(source["id"], **changes)


def handle_transcript(job):
    iid = job["target"]
    meta, _ = store.read_item(iid)
    if not meta or meta.get("transcript") == "ok":
        return
    try:
        cues, info = media.fetch_subtitles(meta["url"], meta["platform"])
    except platforms.RateLimited as exc:
        if job["attempts"] <= RATE_LIMIT_RETRIES:
            raise Retry(1800 * job["attempts"], str(exc))
        no_subtitles(meta, job, "限流重试后仍失败")
        return
    except platforms.NoSubtitles:
        no_subtitles(meta, job, "没有字幕")
        return
    except Exception:
        if not meta.get("members_only"):
            raise
        log.warning("members-only transcript failed for %s", iid, exc_info=True)
        store.update_item(iid, transcript="failed", transcript_note=MEMBERS_NOTE)
        indexer.refresh_row(iid)
        return
    if not cues:
        no_subtitles(meta, job, "字幕为空")
        return
    store.write_transcript(iid, cues)
    changes = {"transcript": "ok", "transcript_method": "subtitles", "transcript_lang": info.get("language"),
               "transcript_note": None}
    if info.get("duration"):
        changes["duration"] = int(info["duration"])
    if info.get("upload_date") and meta.get("date_approx"):
        changes.update(published=net.iso_from_ymd(info["upload_date"]), date_approx=False)
    if info.get("chapters"):
        changes["chapters"] = info["chapters"]
    store.update_item(iid, **changes)
    indexer.index_item(iid)
    favorites.refresh(iid)


def no_subtitles(meta, job, note):
    iid = meta["id"]
    if config.ASR_ENABLED and not (meta.get("backfill") and job["priority"] < PRIO_DEMAND):
        queue_asr(iid, job["priority"], job["sort_ts"], note)
        return
    store.update_item(iid, transcript="none", transcript_note=note)
    indexer.refresh_row(iid)


def _run_asr(python, audio, out, device, batch):
    worker = Path(__file__).with_name("asr_worker.py")
    return subprocess.run([str(python), str(worker), str(audio), str(out), config.FFMPEG, device, str(batch)],
                          capture_output=True, text=True, timeout=6 * 3600)


def handle_asr(job):
    iid = job["target"]
    meta, _ = store.read_item(iid)
    if not meta or meta.get("transcript") == "ok":
        return
    store.update_item(iid, transcript="asr_running")
    indexer.refresh_row(iid)
    try:
        with tempfile.TemporaryDirectory(prefix="fk-audio-") as tmp:
            if meta.get("audio_url"):
                audio = net.download_file(meta["audio_url"], Path(tmp) / "audio.m4a")
            else:
                audio = media.download_audio(meta["url"], meta["platform"], Path(tmp))
            out = Path(tmp) / "cues.json"
            result = None
            if config.ASR_PYTHON:
                GPU_BUSY.set()
                try:
                    indexer.unload_embedder()
                    result = _run_asr(config.ASR_PYTHON, audio, out, config.ASR_DEVICE, config.ASR_BATCH)
                finally:
                    GPU_BUSY.clear()
            if config.ASR_CPU_PYTHON and (result is None or result.returncode != 0 or not out.is_file()):
                if result is not None:
                    log.warning("ASR failed for %s, falling back to CPU: %s", iid, result.stderr[-300:])
                result = _run_asr(config.ASR_CPU_PYTHON, audio, out, "cpu", 1)
            if result.returncode != 0 or not out.is_file():
                raise RuntimeError(result.stderr.strip()[-500:])
            cues = json.loads(out.read_text(encoding="utf-8"))
    except Exception:
        note = {"transcript_note": MEMBERS_NOTE} if meta.get("members_only") else {}
        store.update_item(iid, transcript="failed", **note)
        indexer.refresh_row(iid)
        raise
    store.write_transcript(iid, cues)
    store.update_item(iid, transcript="ok" if cues else "none", transcript_method="asr")
    indexer.index_item(iid)
    favorites.refresh(iid)


def handle_article(job):
    iid = job["target"]
    meta, _ = store.read_item(iid)
    if not meta:
        return
    article = feeds.fetch_article(meta["url"])
    changes = {"body_status": "ok" if article["body"] else "failed"}
    if article.get("thumbnail") and not meta.get("thumbnail_url"):
        changes["thumbnail_url"] = article["thumbnail"]
        db.enqueue("thumb", iid, priority=job["priority"], sort_ts=job["sort_ts"])
    meta.update(changes)
    store.write_item(meta, article["body"])
    indexer.index_item(iid)
    favorites.refresh(iid)


def handle_thumb(job):
    iid = job["target"]
    meta, _ = store.read_item(iid)
    if not meta or not meta.get("thumbnail_url"):
        return
    net.download(meta["thumbnail_url"], store.thumb_path(iid), meta["platform"])
    indexer.refresh_row(iid)


def handle_embed(job):
    indexer.embed_item(job["target"])


def handle_summary(job):
    meta, _ = store.read_item(job["target"])
    if meta and meta.get("transcript") in ("pending", "asr_queued", "asr_running"):
        raise Retry(20, "等逐字稿完成后再总结")
    summary.summarize(job["target"])
    indexer.refresh_row(job["target"])
    favorites.refresh(job["target"])


HANDLERS = {"poll": handle_poll, "transcript": handle_transcript, "asr": handle_asr, "article": handle_article,
            "thumb": handle_thumb, "embed": handle_embed, "summary": handle_summary}
