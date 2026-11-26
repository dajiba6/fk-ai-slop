"""Xiaohongshu creators. Note pages render without login for a mobile UA. Profile pages need a logged-in
browser, which the xiaohongshu-mcp container (config.XHS_MCP_URL) provides; it also needs any valid
xsec_token from that user."""
import json
import re
import urllib.parse

import httpx

from fkslop import config
from fkslop.platforms.net import UA, http_client, iso_from_ts

PLATFORM = "xiaohongshu"
MOBILE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
             "Version/17.0 Mobile/15E148 Safari/604.1")
_PROFILE_NOTES = """() => {
  const unwrap = (v) => (v && v._value !== undefined ? v._value : v)
  const tabs = unwrap(window.__INITIAL_STATE__?.user?.notes) || []
  return JSON.parse(JSON.stringify(Array.from(unwrap(tabs[0]) || [])))
}"""


def require_container():
    if not config.XHS_MCP_URL:
        raise RuntimeError("没有配置小红书：需要运行 xiaohongshu-mcp 容器并设置 FK_XHS_MCP_URL")


def published(note_id):
    """The first 8 hex digits of a note ID are its publish time."""
    return iso_from_ts(int(note_id[:8], 16))


def note_url(note_id, token):
    """The App only opens a note from /discovery/item/ links; /explore/ opens its home screen."""
    return (f"https://www.xiaohongshu.com/discovery/item/{note_id}"
            f"?xsec_token={urllib.parse.quote(token, safe='')}&xsec_source=app_share")


def cover(url):
    """Signed webp cover URLs expire; the image ID gives a stable JPEG."""
    match = re.search(r"/([0-9a-z]{30,})(?:!|\?|$)", url or "")
    return f"https://sns-img-qc.xhscdn.com/{match.group(1)}?imageView2/2/w/640/format/jpg" if match else url


def _get(url, follow):
    with http_client(PLATFORM, headers={"User-Agent": MOBILE_UA}, timeout=30, follow_redirects=follow) as client:
        return client.get(url)


def expand(url):
    """Short share links redirect to the real URL; logged-out redirects past that lead to a login page."""
    if "xhslink" not in url.lower():
        return url
    return _get(url, follow=False).headers.get("location") or url


def _query(url, key):
    return (urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get(key) or [None])[0]


def note(url):
    """One note from its share link (xhslink.cn) or a note URL carrying its xsec_token."""
    url = expand(url)
    response = _get(url, follow=True)
    response.raise_for_status()
    final, html = str(response.url), response.text
    match = re.search(r"window\.__INITIAL_STATE__=(.*?)</script>", html, re.S)
    state = json.loads(re.sub(r"(?<=[:\[,])undefined(?=[,}\]])", "null", match.group(1))) if match else {}
    data = ((state.get("noteData") or {}).get("data") or {}).get("noteData") or {}
    if not data.get("noteId"):
        raise RuntimeError("没有解析出小红书笔记，链接需要带 xsec_token（用 App 里的“复制链接”）")
    token = _query(final, "xsec_token") or _query(url, "xsec_token")
    user = data.get("user") or {}
    video = data.get("video") or {}
    image = ((data.get("imageList") or [{}])[0].get("infoList") or [{}])[-1].get("url")
    return {
        "native_id": data["noteId"], "title": data.get("title") or (data.get("desc") or "")[:40],
        "author": user.get("nickName") or user.get("nickname"), "user_id": user.get("userId"),
        "xsec_token": token, "url": note_url(data["noteId"], token) if token else final,
        "published": iso_from_ts(int(data["time"]) // 1000) if data.get("time") else published(data["noteId"]),
        "duration": (video.get("capa") or {}).get("duration"), "thumbnail": cover(image),
        "description": (data.get("desc") or "").replace("[话题]#", "").strip(),
        "format": "video" if data.get("type") == "video" else "note",
    }


def profile_notes(user_id, token):
    """The notes on a user's profile page (the first screen, newest first apart from pinned notes)."""
    require_container()
    with httpx.Client(trust_env=False, timeout=180) as client:
        payload = client.post(f"{config.XHS_MCP_URL}/api/v1/user/profile",
                              json={"user_id": user_id, "xsec_token": token}).json()
        if not payload.get("success"):
            raise RuntimeError(f"xiaohongshu-mcp：{payload.get('error')} {str(payload.get('details') or '')[:200]}")
        data = (payload.get("data") or {}).get("data") or {}
        feeds = data.get("feeds") or []
        # Logged out, the page still shows a few notes but without IDs.
        if not any(feed.get("id") for feed in feeds):
            status = client.get(f"{config.XHS_MCP_URL}/api/v1/login/status").json()
            if not (status.get("data") or {}).get("is_logged_in"):
                raise RuntimeError("xiaohongshu-mcp 已掉线，需要重新扫码登录")
            raise RuntimeError("小红书主页没有返回笔记，xsec_token 可能失效：重新用该博主的笔记分享链接添加来源")
    name = (data.get("userBasicInfo") or {}).get("nickname")
    return name, _feed_entries(feeds, name)


def _feed_entries(feeds, name):
    out = []
    for feed in feeds:
        card = feed.get("noteCard") or {}
        note_id = feed.get("id")
        if not note_id or not feed.get("xsecToken"):
            continue
        image = card.get("cover") or {}
        out.append({
            "native_id": note_id, "title": card.get("displayTitle") or "（无标题）",
            "author": (card.get("user") or {}).get("nickname") or name, "xsec_token": feed["xsecToken"],
            "url": note_url(note_id, feed["xsecToken"]), "published": published(note_id),
            "thumbnail": cover(image.get("urlDefault") or image.get("urlPre") or image.get("url")),
            "duration": None, "description": "", "format": "video" if card.get("type") == "video" else "note",
        })
    return out


def profile_notes_since(user_id, token, since):
    """Profile notes back to `since` (YYYY-MM-DD). The container only reads the first screen (~60 notes), so
    this scrolls the profile in a local headless browser with the container's login cookies; the page keeps
    appending the loaded notes to __INITIAL_STATE__."""
    from playwright.sync_api import sync_playwright

    if not config.XHS_COOKIES or not config.XHS_COOKIES.is_file():
        raise RuntimeError("回填小红书需要容器的登录 cookie：设置 FK_XHS_COOKIES")
    cookies = []
    for c in json.loads(config.XHS_COOKIES.read_text())["cookies"]:
        cookie = {"name": c["name"], "value": c["value"], "domain": c["domain"], "path": c.get("path") or "/",
                  "httpOnly": bool(c.get("httpOnly")), "secure": bool(c.get("secure"))}
        if not c.get("session") and (c.get("expires") or -1) > 0:
            cookie["expires"] = c["expires"]
        cookies.append(cookie)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 900}, locale="zh-CN")
            context.add_cookies(cookies)
            page = context.new_page()
            page.goto(f"https://www.xiaohongshu.com/user/profile/{user_id}?xsec_token="
                      f"{urllib.parse.quote(token, safe='')}&xsec_source=pc_note",
                      wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)
            feeds, stalled = [], 0
            for _ in range(300):
                loaded = page.evaluate(_PROFILE_NOTES)
                stalled = stalled + 1 if len(loaded) == len(feeds) else 0
                feeds = loaded
                ids = [f["id"] for f in feeds if f.get("id")]
                if stalled >= 6 or (ids and published(min(ids, key=lambda i: int(i[:8], 16)))[:10] < since):
                    break
                page.mouse.wheel(0, 2500)
                page.wait_for_timeout(1500)
        finally:
            browser.close()
    if not any(f.get("id") for f in feeds):
        raise RuntimeError("滚动主页没有拿到笔记：xiaohongshu-mcp 可能已掉线或 xsec_token 失效")
    return _feed_entries(feeds, None)


def resolve(url):
    """A profile URL with xsec_token, a profile share link, or any of the user's note share links."""
    require_container()
    url = expand(url)
    match = re.search(r"/user/profile/([0-9a-f]{24})", url)
    if match:
        user_id, token = match.group(1), _query(url, "xsec_token")
        if not token:
            raise RuntimeError("主页链接缺少 xsec_token：请贴 App 里“分享主页 → 复制链接”或他任意一条笔记的分享链接")
    else:
        shared = note(url)
        user_id, token = shared["user_id"], shared["xsec_token"]
        if not user_id or not token:
            raise RuntimeError("笔记链接里没有作者或 xsec_token")
    name, _ = profile_notes(user_id, token)
    return {"id": f"xhs-{user_id}", "platform": PLATFORM, "user_id": user_id, "xsec_token": token,
            "url": f"https://www.xiaohongshu.com/user/profile/{user_id}", "name": name or user_id}


def poll(source, backfill):
    if backfill:
        return profile_notes_since(source["user_id"], source["xsec_token"], source.get("since") or "0000-00-00")
    return profile_notes(source["user_id"], source["xsec_token"])[1]
