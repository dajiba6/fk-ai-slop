"""Bilibili uploaders: the space video list API (WBI-signed), paged slowly to stay under the risk control."""
import hashlib
import re
import time
import urllib.parse
from http.cookiejar import MozillaCookieJar
from pathlib import Path

from fkslop import config
from fkslop.platforms.net import UA, RateLimited, http_client, iso_from_ts

PLATFORM = "bilibili"
MIXIN = [46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14,
         39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59,
         6, 63, 57, 62, 11, 36, 20, 34, 44, 52]
_wbi_cache = {"key": None, "at": 0}


def _cookies():
    if not config.BILIBILI_COOKIES or not config.BILIBILI_COOKIES.is_file():
        return {}
    jar = MozillaCookieJar(str(config.BILIBILI_COOKIES))
    jar.load(ignore_discard=True, ignore_expires=True)
    return {c.name: c.value for c in jar if "bilibili" in (c.domain or "")}


def _client(mid=None):
    referer = f"https://space.bilibili.com/{mid}/video" if mid else "https://www.bilibili.com/"
    return http_client(PLATFORM, timeout=30, cookies=_cookies(),
                       headers={"User-Agent": UA, "Referer": referer,
                                "Origin": "https://space.bilibili.com"})


def _wbi_key(client):
    if _wbi_cache["key"] and time.time() - _wbi_cache["at"] < 3600:
        return _wbi_cache["key"]
    data = client.get("https://api.bilibili.com/x/web-interface/nav").json()["data"]["wbi_img"]
    raw = Path(urllib.parse.urlparse(data["img_url"]).path).stem + Path(urllib.parse.urlparse(data["sub_url"]).path).stem
    key = "".join(raw[i] for i in MIXIN)[:32]
    _wbi_cache.update(key=key, at=time.time())
    return key


def _wbi_sign(params, key):
    params = dict(params, wts=int(time.time()))
    params = {k: re.sub(r"[!'()*]", "", str(v)) for k, v in sorted(params.items())}
    query = urllib.parse.urlencode(params)
    params["w_rid"] = hashlib.md5((query + key).encode()).hexdigest()
    return params


def space_mid(url):
    match = re.search(r"space\.bilibili\.com/(\d+)", url)
    if not match:
        raise RuntimeError("没有识别出 B 站 UP 主 ID")
    return match.group(1)


def resolve(url):
    mid = space_mid(url)
    with _client(mid) as client:
        data = client.get("https://api.bilibili.com/x/web-interface/card", params={"mid": mid}).json()
    name = ((data.get("data") or {}).get("card") or {}).get("name") or mid
    return {"id": f"bili-{mid}", "platform": PLATFORM, "mid": mid,
            "url": f"https://space.bilibili.com/{mid}", "name": name}


def poll(source, backfill):
    return space_videos(source["mid"], config.POLL_BACKFILL if backfill else 30, pages=None if backfill else 1)


def _duration(text):
    parts = [int(p) for p in str(text or "0").split(":") if p.isdigit()]
    seconds = 0
    for part in parts:
        seconds = seconds * 60 + part
    return seconds or None


def space_videos(mid, limit, pages=None):
    out = []
    with _client(mid) as client:
        key = _wbi_key(client)
        page = 1
        while len(out) < limit and (pages is None or page <= pages):
            params = _wbi_sign({"mid": mid, "ps": 30, "pn": page, "order": "pubdate", "platform": "web",
                                "dm_img_list": "[]", "dm_img_str": "V2ViR0wgMS4wIChPcGVuR0wgRVMgMi4wIENocm9taXVtKQ",
                                "dm_cover_img_str": "QU5HTEUgKE5WSURJQSwgTlZJRElBIEdlRm9yY2UgR1RYIDEwNjApLCBPcGVuR0w",
                                "dm_img_inter": '{"ds":[],"wh":[0,0,0],"of":[0,0,0]}'}, key)
            payload = client.get("https://api.bilibili.com/x/space/wbi/arc/search", params=params).json()
            if payload.get("code") in (-352, -412):
                raise RateLimited(f"B 站风控 {payload.get('code')}")
            if payload.get("code") != 0:
                raise RuntimeError(f"B 站接口错误 {payload.get('code')}: {payload.get('message')}")
            vlist = ((payload.get("data") or {}).get("list") or {}).get("vlist") or []
            for v in vlist:
                pic = v.get("pic") or ""
                if pic.startswith("//"):
                    pic = "https:" + pic
                out.append({
                    "native_id": v["bvid"], "title": v.get("title"), "author": v.get("author"),
                    "url": f"https://www.bilibili.com/video/{v['bvid']}",
                    "published": iso_from_ts(v.get("created")), "date_approx": False,
                    "duration": _duration(v.get("length")),
                    "thumbnail": pic + "@480w_270h_1c.jpg" if pic else None,
                    "description": (v.get("description") or "").strip(), "format": "video",
                })
            total = ((payload.get("data") or {}).get("page") or {}).get("count") or 0
            if not vlist or page * 30 >= total:
                break
            page += 1
            time.sleep(3)
    return out[:limit]
