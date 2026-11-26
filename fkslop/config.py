"""Settings come from the environment, with `.env` in the project root filling in what is unset.
Every external tool is optional: a feature whose setting is empty is switched off, not an error."""
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_env_file():
    path = ROOT / ".env"
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file()


def _env(name, default=""):
    return os.environ.get(name, default).strip()


def _path(name, default=""):
    value = _env(name, default)
    return Path(value).expanduser() if value else None


def _list(name, default=""):
    return {part.strip() for part in _env(name, default).split(",") if part.strip()}


def _tool(name, binary):
    """An explicit setting, else the binary on PATH, else the one installed next to this Python."""
    configured = _env(name)
    if configured:
        return str(Path(configured).expanduser())
    beside = Path(sys.executable).with_name(binary)
    return shutil.which(binary) or (str(beside) if beside.is_file() else binary)


# ---------- site ----------

DATA_DIR = _path("FK_DATA_DIR", "~/media-archive")
ITEMS_DIR = DATA_DIR / "items"
SOURCES_FILE = DATA_DIR / "sources.yaml"
STATE_FILE = DATA_DIR / "state.json"
INDEX_DB = DATA_DIR / "index.sqlite3"

ADMIN_KEY = _env("ADMIN_KEY")
HOST = _env("FK_HOST", "0.0.0.0")
PORT = int(_env("FK_PORT", "8090"))
SITE_NAME = _env("FK_SITE_NAME", "fk ai slop")
POLL_BACKFILL = int(_env("FK_BACKFILL", "1000"))
TRANSCRIPT_GAP_SECONDS = 30

# ---------- network ----------

PROXY = _env("FK_PROXY")
# Sites reached without the proxy even when one is set (mainland sites are usually faster direct).
DIRECT_PLATFORMS = _list("FK_DIRECT_PLATFORMS", "bilibili,xiaohongshu")
# Bind direct connections to IPv4, for hosts whose IPv6 route is broken.
FORCE_IPV4 = _env("FK_FORCE_IPV4") == "1"

# ---------- media tools ----------

YTDLP = _tool("FK_YTDLP", "yt-dlp")
FFMPEG = _tool("FK_FFMPEG", "ffmpeg")
NODE = _tool("FK_NODE", "node")
# yt-dlp --cookies-from-browser value (e.g. "firefox"); YouTube often asks single-video requests to sign in.
YOUTUBE_COOKIES_BROWSER = _env("FK_YOUTUBE_COOKIES_BROWSER")
YOUTUBE_SUB_LANGS = _env("FK_YOUTUBE_SUB_LANGS", "en,en-orig,en-en,en-US")
BILIBILI_SUB_LANGS = _env("FK_BILIBILI_SUB_LANGS", "ai-zh,zh-Hans,zh-CN,zh,zh-Hant,en")
BILIBILI_COOKIES = _path("FK_BILIBILI_COOKIES")

# ---------- Xiaohongshu (needs the xiaohongshu-mcp container) ----------

XHS_MCP_URL = _env("FK_XHS_MCP_URL")
XHS_COOKIES = _path("FK_XHS_COOKIES")

# ---------- speech recognition (SenseVoice in its own venv, see docs) ----------

ASR_PYTHON = _path("FK_ASR_PYTHON")
ASR_DEVICE = _env("FK_ASR_DEVICE", "cuda:0")
ASR_BATCH = int(_env("FK_ASR_BATCH", "2"))
ASR_CPU_PYTHON = _path("FK_ASR_CPU_PYTHON")
ASR_ENABLED = bool(ASR_PYTHON or ASR_CPU_PYTHON)

# ---------- embeddings (Ollama) ----------

OLLAMA_URL = _env("FK_OLLAMA_URL", "http://127.0.0.1:11434")
EMBED_MODEL = _env("FK_EMBED_MODEL", "qwen3-embedding:0.6b")
EMBED_DIM = int(_env("FK_EMBED_DIM", "1024"))

# ---------- summaries (any OpenAI-compatible chat API) ----------

LLM_BASE_URL = _env("FK_LLM_BASE_URL")
LLM_API_KEY = _env("FK_LLM_API_KEY")
LLM_MODEL = _env("FK_LLM_MODEL")
# Extra JSON merged into the request body, e.g. {"thinking": {"type": "disabled"}} for GLM.
LLM_EXTRA_BODY = json.loads(_env("FK_LLM_EXTRA_BODY") or "{}")
LLM_ENABLED = bool(LLM_BASE_URL and LLM_MODEL)
