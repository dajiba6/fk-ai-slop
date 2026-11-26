"""Talking to YouTube, Bilibili, Xiaohongshu, RSS and podcasts. Nothing here touches the index.

Each source platform module has `resolve(url) -> source` and `poll(source, backfill) -> entries`."""
import re

from fkslop.platforms import bilibili, feeds, xiaohongshu, youtube
from fkslop.platforms.net import NoSubtitles, RateLimited  # noqa: F401

SOURCES = {"youtube": youtube, "bilibili": bilibili, "xiaohongshu": xiaohongshu, "rss": feeds, "podcast": feeds}


def classify(url):
    """(kind, url): kind is <platform>_channel / _video / _space / _user / _note, or "web"."""
    text = url.strip()
    lower = text.lower()
    if re.fullmatch(r"BV[0-9A-Za-z]{10}", text):
        return "bilibili_video", f"https://www.bilibili.com/video/{text}"
    if "space.bilibili.com" in lower:
        return "bilibili_space", text
    if "bilibili.com/video/" in lower or "b23.tv" in lower:
        return "bilibili_video", text
    if "youtu.be/" in lower or "youtube.com/watch" in lower or "youtube.com/shorts/" in lower \
            or "youtube.com/live/" in lower:
        return "youtube_video", text
    if "youtube.com/" in lower:
        return "youtube_channel", text
    if "xiaohongshu.com/user/profile/" in lower:
        return "xhs_user", text
    if "xhslink.com" in lower or "xhslink.cn" in lower or "xiaohongshu.com/" in lower:
        return "xhs_note", text
    return "web", text


SOURCE_KINDS = {"youtube_channel": youtube, "bilibili_space": bilibili, "xhs_user": xiaohongshu,
                "xhs_note": xiaohongshu, "web": feeds}
