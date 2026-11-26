"""HTTP clients, yt-dlp invocation and downloads, with the proxy / direct / IPv4 rules from config."""
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import httpx

from fkslop import config

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/131.0.0.0 Safari/537.36")
PROXY_KEYS = ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")


class RateLimited(Exception):
    pass


class NoSubtitles(Exception):
    pass


def iso_from_ts(ts):
    return datetime.fromtimestamp(int(ts), timezone.utc).replace(microsecond=0).isoformat() if ts else None


def iso_from_ymd(ymd):
    if not ymd or len(str(ymd)) != 8:
        return None
    ymd = str(ymd)
    return f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}T00:00:00+00:00"


def proxied(platform):
    return bool(config.PROXY) and platform not in config.DIRECT_PLATFORMS


def proxy_env(platform):
    env = {k: v for k, v in os.environ.items() if k not in PROXY_KEYS}
    if proxied(platform):
        for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
            env[key] = config.PROXY
    return env


def transport(platform=None):
    if config.FORCE_IPV4 and not proxied(platform):
        return httpx.HTTPTransport(local_address="0.0.0.0")
    return None


def http_client(platform=None, **options):
    options = {"headers": {"User-Agent": UA}, "timeout": 60, "follow_redirects": True, **options}
    if proxied(platform):
        return httpx.Client(proxy=config.PROXY, trust_env=False, **options)
    return httpx.Client(trust_env=False, transport=transport(platform), **options)


def ytdlp(args, platform, timeout=600):
    command = [config.YTDLP, "--no-update", "--ignore-config"]
    if config.FORCE_IPV4 and not proxied(platform):
        command.append("--force-ipv4")
    cookies = None
    if platform == "bilibili" and config.BILIBILI_COOKIES and config.BILIBILI_COOKIES.is_file():
        cookies = _cookie_copy(config.BILIBILI_COOKIES)
        command += ["--cookies", cookies]
    try:
        return subprocess.run([*command, *args], capture_output=True, text=True, timeout=timeout,
                              env=proxy_env(platform))
    finally:
        if cookies:
            Path(cookies).unlink(missing_ok=True)


def _cookie_copy(source: Path):
    """yt-dlp rewrites its cookie jar, so hand each call a private copy (created 0600)."""
    fd, target = tempfile.mkstemp(prefix="fk-cookies-", suffix=".txt")
    with os.fdopen(fd, "wb") as handle:
        handle.write(source.read_bytes())
    return target


def youtube_auth_args():
    """Single-video YouTube requests hit the bot check without a logged-in cookie and a JS runtime."""
    args = []
    if config.YOUTUBE_COOKIES_BROWSER:
        args += ["--cookies-from-browser", config.YOUTUBE_COOKIES_BROWSER]
    if Path(config.NODE).is_file():
        args += ["--js-runtimes", f"node:{config.NODE}"]
    return args


def download(url, target: Path, platform=None):
    headers = {"Referer": "https://www.bilibili.com/"} if platform == "bilibili" else {}
    with http_client(platform) as client:
        response = client.get(url, headers=headers)
        response.raise_for_status()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(response.content)


def download_file(url, target: Path, platform=None):
    with http_client(platform) as client, \
            client.stream("GET", url, timeout=httpx.Timeout(60, read=300)) as response:
        response.raise_for_status()
        with target.open("wb") as handle:
            for chunk in response.iter_bytes(1 << 20):
                handle.write(chunk)
    return target
