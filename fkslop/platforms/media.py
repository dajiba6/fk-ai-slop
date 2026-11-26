"""Single YouTube / Bilibili videos through yt-dlp: metadata, subtitle tracks and audio."""
import html
import json
import re
import subprocess
import tempfile
from pathlib import Path

from fkslop import config
from fkslop.platforms.net import NoSubtitles, RateLimited, iso_from_ts, iso_from_ymd, youtube_auth_args, ytdlp

RATE_LIMIT = re.compile(r"429|Too Many Requests|page needs to be reloaded|confirm you.re not a bot")


def video_metadata(url, platform):
    auth = youtube_auth_args() if platform == "youtube" else []
    result = ytdlp([*auth, "-J", "--skip-download", "--no-playlist", url], platform, timeout=180)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip()[-500:])
    info = json.loads(result.stdout)
    vid = info.get("id")
    if platform == "bilibili":
        vid = info.get("display_id") or info.get("webpage_url_basename") or vid
        match = re.search(r"BV[0-9A-Za-z]{10}", info.get("webpage_url") or url)
        vid = match.group(0) if match else vid
    thumb = info.get("thumbnail")
    if platform == "youtube":
        thumb = f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg"
    return {
        "native_id": vid, "title": info.get("title"),
        "author": info.get("channel") or info.get("uploader"),
        "channel_id": info.get("channel_id") or info.get("uploader_id"),
        "url": info.get("webpage_url") or url,
        "published": iso_from_ts(info.get("timestamp")) or iso_from_ymd(info.get("upload_date")),
        "date_approx": False, "duration": int(info["duration"]) if info.get("duration") else None,
        "thumbnail": thumb, "description": (info.get("description") or "").strip(),
        "format": "video",
    }


# ---------- subtitles ----------

_CUE = re.compile(r"(\d{2}:\d{2}:\d{2}[.,]\d{3}) --> (\d{2}:\d{2}:\d{2}[.,]\d{3})[^\n]*\n(.*?)(?=\n\n|\Z)", re.S)


def _seconds(stamp):
    h, m, rest = stamp.replace(",", ".").split(":")
    return int(h) * 3600 + int(m) * 60 + float(rest)


def _clean(text):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", text))).strip()


def parse_cues(raw):
    """VTT or SRT text to [{start, end, text}] in seconds."""
    cues = []
    for match in _CUE.finditer(raw.replace("\r\n", "\n")):
        text = _clean(match.group(3))
        if text:
            cues.append({"start": _seconds(match.group(1)), "end": _seconds(match.group(2)), "text": text})
    return cues


def parse_json3(raw):
    cues = []
    for event in json.loads(raw).get("events") or []:
        text = re.sub(r"\s+", " ", "".join(seg.get("utf8", "") for seg in event.get("segs") or [])).strip()
        if text:
            start = int(event.get("tStartMs") or 0) / 1000
            cues.append({"start": start, "end": start + int(event.get("dDurationMs") or 0) / 1000, "text": text})
    return cues


def dedupe_rolling(cues):
    """YouTube auto captions repeat the previous line inside each cue; keep only the new words."""
    out, tail = [], []
    for cue in cues:
        if cue["end"] - cue["start"] < 0.05:
            continue
        words = cue["text"].split()
        overlap = 0
        for size in range(min(len(words), len(tail)), 0, -1):
            if tail[-size:] == words[:size]:
                overlap = size
                break
        fresh = words[overlap:]
        if not fresh:
            continue
        tail = (tail + fresh)[-40:]
        out.append({"start": cue["start"], "end": cue["end"], "text": " ".join(fresh)})
    return out


def _track_lang(path: Path):
    """yt-dlp names tracks <id>.<lang>.<ext>."""
    return path.name[: -len(path.suffix)].rsplit(".", 1)[-1].lower()


def _pick_track(work: Path, langs):
    tracks = [p for p in work.iterdir() if p.suffix.lower() in (".vtt", ".srt", ".json3")
              and "danmaku" not in p.name.lower()]
    order = [lang.lower() for lang in langs]

    def rank(path):
        lang = _track_lang(path)
        return (order.index(lang) if lang in order else len(order), path.suffix == ".json3", -path.stat().st_size)

    return min(tracks, key=rank) if tracks else None


def fetch_subtitles(url, platform):
    """The best subtitle track in the configured languages, plus duration / upload date / chapters.
    Only a few languages are requested: asking for every YouTube translation trips its 429 limit."""
    youtube = platform == "youtube"
    langs = (config.YOUTUBE_SUB_LANGS if youtube else config.BILIBILI_SUB_LANGS).split(",")
    with tempfile.TemporaryDirectory(prefix="fk-subs-") as tmp:
        work = Path(tmp)
        args = [*(youtube_auth_args() if youtube else []), "--no-playlist", "--skip-download",
                "--write-auto-sub", "--write-sub", "--sub-langs", ",".join(langs),
                "--sub-format", "vtt/json3" if youtube else "srt/vtt", "--write-info-json",
                "-o", str(work / "%(id)s"), url]
        try:
            result = ytdlp(args, platform, timeout=180)
            output = (result.stderr or "") + (result.stdout or "")
        except subprocess.TimeoutExpired:
            output = "yt-dlp timed out"
        track = _pick_track(work, langs)
        if track is None:
            if RATE_LIMIT.search(output):
                raise RateLimited(output.strip()[-300:])
            raise NoSubtitles(output.strip()[-300:])
        raw = track.read_text(encoding="utf-8")
        cues = parse_json3(raw) if track.suffix == ".json3" else parse_cues(raw)
        info_files = list(work.glob("*.info.json"))
        info = json.loads(info_files[0].read_text(encoding="utf-8")) if info_files else {}
    if youtube:
        cues = dedupe_rolling(cues)
    lang = _track_lang(track).removeprefix("ai-").split("-")[0]
    chapters = [{"start_time": c.get("start_time"), "end_time": c.get("end_time"), "title": c.get("title")}
                for c in info.get("chapters") or []]
    return cues, {"language": lang, "duration": info.get("duration"), "upload_date": info.get("upload_date"),
                  "chapters": chapters}


# ---------- audio ----------

def download_audio(url, platform, workdir: Path):
    args = ["--socket-timeout", "15", "--retries", "3", "-f", "bestaudio/best", "--no-playlist",
            "-o", str(workdir / "audio.%(ext)s"), url]
    if platform == "youtube":
        args[0:0] = youtube_auth_args()
    # Bilibili hands out a different CDN node per extraction and some PCDN nodes are unreachable.
    for _ in range(4 if platform == "bilibili" else 1):
        result = ytdlp(args, platform, timeout=3600)
        files = [p for p in workdir.glob("audio.*") if not p.name.endswith(".part")]
        if result.returncode == 0 and files:
            return files[0]
        for leftover in workdir.glob("audio.*"):
            leftover.unlink()
    raise RuntimeError(result.stderr.strip()[-500:])
