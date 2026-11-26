"""YouTube channels: RSS for polling, yt-dlp channel tabs for backfill and members-only uploads."""
import json
import re
import time
from datetime import datetime, timezone

import feedparser
import httpx

from fkslop import config
from fkslop.platforms.net import http_client, iso_from_ts, ytdlp

PLATFORM = "youtube"


def channel_base(url):
    url = url.strip().rstrip("/")
    return re.sub(r"/(videos|shorts|streams|featured|playlists|community|about)$", "", url)


def resolve(url):
    result = ytdlp(["--flat-playlist", "-J", "--playlist-end", "1", channel_base(url) + "/videos"],
                   PLATFORM, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip()[-500:])
    data = json.loads(result.stdout)
    channel_id = data.get("channel_id")
    if not channel_id:
        raise RuntimeError("没有识别出 YouTube 频道 ID")
    return {"id": f"yt-{channel_id}", "platform": PLATFORM, "channel_id": channel_id,
            "url": f"https://www.youtube.com/channel/{channel_id}",
            "name": data.get("channel") or data.get("uploader") or channel_id,
            "handle": data.get("uploader_id")}


def poll(source, backfill):
    if backfill:
        return channel_backfill(source["channel_id"], config.POLL_BACKFILL)
    return channel_recent(source["channel_id"])


def thumbnail(vid):
    return f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg"


def channel_tab(channel_id, tab, limit):
    """Newest first. Members-only uploads are listed even without login (availability subscriber_only).
    Shorts listings carry no dates at all; the other tabs only approximate ones ("3 months ago")."""
    result = ytdlp(["--flat-playlist", "-J", "--playlist-end", str(limit),
                    "--extractor-args", "youtubetab:approximate_date",
                    f"https://www.youtube.com/channel/{channel_id}/{tab}"], PLATFORM)
    if result.returncode != 0:
        if "does not have a" in result.stderr:
            return []
        raise RuntimeError(result.stderr.strip()[-500:])
    data = json.loads(result.stdout)
    out = []
    for entry in data.get("entries") or []:
        vid = entry.get("id")
        if not vid:
            continue
        out.append({
            "native_id": vid, "title": entry.get("title"),
            "author": data.get("channel") or data.get("uploader"),
            "url": f"https://www.youtube.com/watch?v={vid}",
            "published": iso_from_ts(entry.get("timestamp")), "date_approx": True,
            "duration": int(entry["duration"]) if entry.get("duration") else None,
            "thumbnail": thumbnail(vid),
            "format": "short" if tab == "shorts" else ("live" if tab == "streams" else "video"),
            "members_only": entry.get("availability") == "subscriber_only",
        })
    return out


def published(vid, short=False):
    """Exact publish time from the watch page, also for members-only uploads and without login: seconds
    instead of a full yt-dlp extraction. Shorts only carry the ISO date on their /shorts/ page."""
    url = f"https://www.youtube.com/shorts/{vid}" if short else f"https://www.youtube.com/watch?v={vid}"
    for attempt in range(3):
        try:
            with http_client(PLATFORM) as client:
                html = client.get(url, headers={"Accept-Language": "en"}).text
            break
        except httpx.HTTPError:
            if attempt == 2:
                raise
            time.sleep(3)
    match = re.search(r'"publishDate":"([^"]+)"', html) or re.search(r'itemprop="datePublished" content="([^"]+)"', html)
    if not match:
        return None
    moment = datetime.fromisoformat(match.group(1))
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat() if moment.tzinfo else None


def channel_backfill(channel_id, limit):
    seen, entries = set(), []
    for tab in ("videos", "shorts", "streams"):
        for entry in channel_tab(channel_id, tab, limit):
            if entry["native_id"] not in seen:
                seen.add(entry["native_id"])
                entries.append(entry)
    # Stable sort: undated shorts keep their newest-first order, which since_filter relies on.
    entries.sort(key=lambda e: e["published"] or "", reverse=True)
    return entries[:limit]


def channel_recent(channel_id):
    with http_client(PLATFORM) as client:
        response = client.get(f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}")
        response.raise_for_status()
    feed = feedparser.parse(response.content)
    out = []
    for entry in feed.entries:
        vid = entry.get("yt_videoid")
        if not vid:
            continue
        link = entry.get("link") or ""
        out.append({
            "native_id": vid, "title": entry.get("title"), "author": entry.get("author"),
            "url": f"https://www.youtube.com/watch?v={vid}",
            "published": entry.get("published"), "date_approx": False, "duration": None,
            "thumbnail": thumbnail(vid),
            "format": "short" if "/shorts/" in link else "video",
            "description": (entry.get("media_description") or entry.get("summary") or "").strip(),
        })
    # The RSS feed leaves out members-only uploads.
    seen = {e["native_id"] for e in out}
    for tab in ("videos", "streams"):
        out += [e for e in channel_tab(channel_id, tab, 30) if e["members_only"] and e["native_id"] not in seen]
    return out
