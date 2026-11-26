"""RSS / Atom feeds and web articles. A feed whose entries carry audio enclosures is a podcast."""
import hashlib
import html as html_lib
import re
import urllib.parse
from datetime import datetime, timezone

import feedparser
import trafilatura

from fkslop.platforms.net import http_client


def _get_feed(url):
    with http_client() as client:
        response = client.get(url)
        response.raise_for_status()
    return feedparser.parse(response.content), response


def _stamp(entry):
    stamp = entry.get("published_parsed") or entry.get("updated_parsed")
    return datetime(*stamp[:6], tzinfo=timezone.utc).isoformat() if stamp else None


def _audio_url(entry):
    for link in entry.get("links") or []:
        if link.get("rel") == "enclosure" and (link.get("type") or "").startswith("audio/") and link.get("href"):
            return link["href"]
    return None


def resolve(url):
    feed, response = _get_feed(url)
    if not feed.entries and not feed.feed.get("title"):
        discovered = re.search(r'<link[^>]+type="application/(?:rss|atom)\+xml"[^>]+href="([^"]+)"', response.text)
        if discovered:
            return resolve(urllib.parse.urljoin(str(response.url), discovered.group(1)))
        raise RuntimeError("这个链接不是 RSS/Atom，也没有找到 feed 地址")
    digest = hashlib.sha1(url.encode()).hexdigest()[:10]
    name = feed.feed.get("title") or url
    if any(_audio_url(e) for e in feed.entries[:10]):
        return {"id": f"pod-{digest}", "platform": "podcast", "url": url, "name": name,
                "site": feed.feed.get("link")}
    return {"id": f"rss-{digest}", "platform": "rss", "url": url, "name": name, "site": feed.feed.get("link")}


def poll(source, backfill):
    return podcast_entries(source["url"]) if source["platform"] == "podcast" else article_entries(source["url"])


def html_text(html):
    text = re.sub(r"(?i)<br\s*/?>", "\n", html or "")
    text = re.sub(r"(?i)</(p|div|li|h\d)>", "\n\n", text)
    text = html_lib.unescape(re.sub(r"<[^>]+>", "", text))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def duration(value):
    """itunes:duration is seconds, MM:SS or HH:MM:SS."""
    parts = [int(p) for p in str(value or "").split(":") if p.strip().isdigit()]
    if not parts:
        return None
    seconds = 0
    for part in parts:
        seconds = seconds * 60 + part
    return seconds


def podcast_entries(url):
    feed, _ = _get_feed(url)
    show = feed.feed.get("title")
    cover = (feed.feed.get("image") or {}).get("href")
    out = []
    for entry in feed.entries:
        audio = _audio_url(entry)
        if not audio:
            continue
        html = max([entry.get("summary") or ""] + [c.get("value") or "" for c in entry.get("content") or []], key=len)
        out.append({
            "native_id": hashlib.sha1((entry.get("id") or audio).encode()).hexdigest()[:12],
            "url": entry.get("link") or audio, "audio_url": audio, "title": entry.get("title"),
            "author": entry.get("author") or show, "published": _stamp(entry),
            "duration": duration(entry.get("itunes_duration")), "description": html_text(html),
            "thumbnail": (entry.get("image") or {}).get("href") or cover,
        })
    return out


def article_entries(url):
    feed, _ = _get_feed(url)
    out = []
    for entry in feed.entries:
        link = entry.get("link")
        if not link:
            continue
        html = ""
        if entry.get("content"):
            html = max((c.get("value") or "" for c in entry.content), key=len)
        image = None
        for media in (entry.get("media_content") or []) + (entry.get("media_thumbnail") or []):
            if media.get("url"):
                image = media["url"]
                break
        out.append({
            "url": link, "title": entry.get("title"), "author": entry.get("author") or feed.feed.get("title"),
            "published": _stamp(entry), "html": html, "summary": entry.get("summary") or "", "thumbnail": image,
        })
    return out


def article_from_html(html, url):
    body = trafilatura.extract(html, url=url, output_format="markdown", include_links=True,
                               include_images=False, include_tables=True, favor_recall=True)
    meta = trafilatura.extract_metadata(html, default_url=url)
    return body or "", meta


def fetch_article(url):
    with http_client() as client:
        response = client.get(url)
        response.raise_for_status()
    body, meta = article_from_html(response.text, str(response.url))
    return {
        "body": body,
        "title": meta.title if meta else None,
        "author": meta.author if meta else None,
        "published": (meta.date + "T00:00:00+00:00") if meta and meta.date else None,
        "thumbnail": meta.image if meta else None,
        "site": meta.sitename if meta else None,
    }
