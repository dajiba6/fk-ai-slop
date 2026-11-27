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


_CJK = re.compile(r"[\u3400-\u9fff]")
# These codes are uploads or original auto-captions. Bare zh-Hans / zh-Hant / yue are also
# the names YouTube gives a translation, so they only win once metadata says they are not one.
_ZH_ORIGINAL = {"zh", "zh-cn", "zh-tw", "zh-hk"}


def _cjk_extension(previous, text):
    """Unspaced Chinese auto-captions repeat the previous cue; return only the new tail."""
    if not previous or not _CJK.search(text):
        return None
    if text == previous:
        return ""
    if text.startswith(previous):
        return text[len(previous):].strip()
    limit = min(len(previous), len(text) - 1)
    for size in range(limit, 3, -1):
        if previous[-size:] == text[:size]:
            return text[size:].strip()
    return None


def dedupe_rolling(cues):
    """YouTube auto captions repeat the previous line inside each cue; keep only the new words."""
    out, tail, previous = [], [], ""
    for cue in cues:
        if cue["end"] - cue["start"] < 0.05:
            continue
        words = cue["text"].split()
        overlap = 0
        for size in range(min(len(words), len(tail)), 0, -1):
            if tail[-size:] == words[:size]:
                overlap = size
                break
        if overlap:
            fresh = " ".join(words[overlap:])
        else:
            extended = _cjk_extension(previous, cue["text"])
            fresh = cue["text"] if extended is None else extended
        previous = cue["text"]
        if not fresh:
            continue
        tail = (tail + fresh.split())[-40:]
        out.append({"start": cue["start"], "end": cue["end"], "text": fresh})
    return out


def _track_lang(path: Path):
    """yt-dlp names tracks <id>.<lang>.<ext>."""
    return path.name[: -len(path.suffix)].rsplit(".", 1)[-1].lower()


def _caption_record(info, lang):
    """(uploaded, track) for this language. An upload wins over an auto caption of the same code."""
    found = {}
    for key, uploaded in (("subtitles", True), ("automatic_captions", False)):
        for code, tracks in (info.get(key) or {}).items():
            if code.lower() == lang and tracks:
                if uploaded:
                    return True, tracks[0]
                found = tracks[0]
    return False, found


def _translated(track):
    url = track.get("url") or ""
    name = (track.get("name") or "").lower()
    return "tlang=" in url or " from " in name


def _youtube_tier(lang, info):
    """Lower is better. Chinese speech beats English speech; a translation loses to both."""
    uploaded, track = _caption_record(info, lang)
    known = bool(track)
    translated = _translated(track) if known else False
    chinese = lang.startswith(("zh", "yue", "cmn"))
    if chinese:
        if not known:
            return 1 if lang in _ZH_ORIGINAL or lang.endswith("-orig") else 3
        if translated:
            return 3
        return 0 if uploaded else 1
    if lang.startswith("en") and not translated:
        return 2
    return 3


def _pick_track(work: Path, langs, info=None):
    tracks = [p for p in work.iterdir() if p.suffix.lower() in (".vtt", ".srt", ".json3")
              and "danmaku" not in p.name.lower()]
    order = [lang.lower() for lang in langs]

    def rank(path):
        lang = _track_lang(path)
        tier = _youtube_tier(lang, info) if info is not None else 0
        pref = order.index(lang) if lang in order else len(order)
        return (tier, pref, path.suffix == ".json3", -path.stat().st_size)

    return min(tracks, key=rank) if tracks else None


def fetch_subtitles(url, platform):
    """The best subtitle track, plus duration / upload date / chapters.
    YouTube prefers Chinese speech and skips tracks translated from another language.
    Only those languages are requested: asking for every translation trips the 429 limit."""
    youtube = platform == "youtube"
    langs = (config.YOUTUBE_SUB_LANGS if youtube else config.BILIBILI_SUB_LANGS).split(",")
    with tempfile.TemporaryDirectory(prefix="fk-subs-") as tmp:
        work = Path(tmp)
        args = [*(youtube_auth_args() if youtube else []), "--no-playlist", "--skip-download",
                "--ignore-no-formats-error",
                "--write-auto-sub", "--write-sub", "--sub-langs", ",".join(langs),
                "--sub-format", "vtt/json3" if youtube else "srt/vtt", "--write-info-json",
                "-o", str(work / "%(id)s"), url]
        try:
            result = ytdlp(args, platform, timeout=180)
            output = (result.stderr or "") + (result.stdout or "")
        except subprocess.TimeoutExpired:
            output = "yt-dlp timed out"
        info_files = list(work.glob("*.info.json"))
        info = json.loads(info_files[0].read_text(encoding="utf-8")) if info_files else {}
        track = _pick_track(work, langs, info if youtube else None)
        if track is None:
            if RATE_LIMIT.search(output):
                raise RateLimited(output.strip()[-300:])
            raise NoSubtitles(output.strip()[-300:])
        raw = track.read_text(encoding="utf-8")
        cues = parse_json3(raw) if track.suffix == ".json3" else parse_cues(raw)
        lang = _track_lang(track)
        uploaded, _ = _caption_record(info, lang)
    if youtube and not uploaded:
        cues = dedupe_rolling(cues)
    lang = lang.removeprefix("ai-").split("-")[0]
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
