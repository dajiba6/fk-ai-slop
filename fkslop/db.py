"""Derived SQLite index: item metadata, chunks, FTS5, sqlite-vec vectors and the job queue."""
import re
import sqlite3
import threading
import time
from datetime import datetime

import sqlite_vec

from fkslop import config

_local = threading.local()

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS items (
  id TEXT PRIMARY KEY, platform TEXT, kind TEXT, source_id TEXT, title TEXT, author TEXT, url TEXT,
  published TEXT, published_ts INTEGER, date_approx INTEGER, duration INTEGER, description TEXT,
  transcript TEXT, has_summary INTEGER, has_thumb INTEGER, backfill INTEGER, added_at TEXT
);
CREATE INDEX IF NOT EXISTS items_published ON items(published_ts DESC);
CREATE INDEX IF NOT EXISTS items_source ON items(source_id, published_ts DESC);
CREATE TABLE IF NOT EXISTS chunks (
  id INTEGER PRIMARY KEY, item_id TEXT, seq INTEGER, start REAL, end REAL, section TEXT, text TEXT,
  embedded INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS chunks_item ON chunks(item_id, seq);
CREATE INDEX IF NOT EXISTS chunks_pending ON chunks(embedded);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(text, tokenize='trigram');
CREATE VIRTUAL TABLE IF NOT EXISTS chunk_vec USING vec0(
  embedding float[{config.EMBED_DIM}] distance_metric=cosine,
  platform text, source_id text, published_ts integer
);
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY, kind TEXT, target TEXT, lane TEXT, priority INTEGER, sort_ts INTEGER,
  not_before REAL, attempts INTEGER DEFAULT 0, status TEXT, error TEXT, payload TEXT,
  created_at REAL, updated_at REAL
);
CREATE INDEX IF NOT EXISTS jobs_pick ON jobs(lane, status, priority DESC, sort_ts DESC);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


def connect():
    conn = getattr(_local, "conn", None)
    if conn is not None:
        return conn
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.INDEX_DB, timeout=30, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.executescript(SCHEMA)
    _local.conn = conn
    return conn


def published_ts(value):
    if not value:
        return 0
    text = str(value)
    try:
        return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return 0


def plain_excerpt(body, title, limit=400):
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", body or "")
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^\s{0,3}(#{1,6}|>|[-*+]|\d+\.)\s+", "", text, flags=re.M)
    text = re.sub(r"[*_`~]+", "", text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines and title and lines[0].strip(" .…") == title.strip(" .…"):
        lines = lines[1:]
    return " ".join(lines)[:limit]


def upsert_item(meta, body):
    conn = connect()
    from fkslop import store
    directory = store.item_dir(meta["id"])
    conn.execute(
        """INSERT OR REPLACE INTO items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (meta["id"], meta["platform"], meta.get("kind", "video"), meta.get("source_id"), meta.get("title"),
         meta.get("author"), meta.get("url"), str(meta.get("published") or ""), published_ts(meta.get("published")),
         int(bool(meta.get("date_approx"))), meta.get("duration"), plain_excerpt(body, meta.get("title")),
         meta.get("transcript"), int((directory / "summary.md").is_file()),
         int((directory / "thumb.jpg").is_file()), int(bool(meta.get("backfill"))), meta.get("added_at")),
    )


def replace_chunks(item_id, chunks):
    conn = connect()
    conn.execute("BEGIN IMMEDIATE")
    try:
        old = [row[0] for row in conn.execute("SELECT id FROM chunks WHERE item_id=?", (item_id,))]
        for rowid in old:
            conn.execute("DELETE FROM chunks_fts WHERE rowid=?", (rowid,))
            conn.execute("DELETE FROM chunk_vec WHERE rowid=?", (rowid,))
        conn.execute("DELETE FROM chunks WHERE item_id=?", (item_id,))
        for seq, chunk in enumerate(chunks):
            cur = conn.execute(
                "INSERT INTO chunks(item_id, seq, start, end, section, text) VALUES (?,?,?,?,?,?)",
                (item_id, seq, chunk.get("start"), chunk.get("end"), chunk.get("section"), chunk["text"]),
            )
            conn.execute("INSERT INTO chunks_fts(rowid, text) VALUES (?,?)", (cur.lastrowid, chunk["text"]))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def store_vectors(rows):
    """rows: [(chunk_id, vector_json, platform, source_id, published_ts)]"""
    conn = connect()
    conn.execute("BEGIN IMMEDIATE")
    try:
        for chunk_id, vector, platform, source_id, ts in rows:
            conn.execute("DELETE FROM chunk_vec WHERE rowid=?", (chunk_id,))
            conn.execute(
                "INSERT INTO chunk_vec(rowid, embedding, platform, source_id, published_ts) VALUES (?,?,?,?,?)",
                (chunk_id, vector, platform, source_id or "", ts),
            )
            conn.execute("UPDATE chunks SET embedded=1 WHERE id=?", (chunk_id,))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


# ---------- jobs ----------

LANES = {"poll": "net", "transcript": "net", "article": "media", "thumb": "media",
         "asr": "asr", "embed": "embed", "summary": "llm"}


def enqueue(kind, target, priority=0, sort_ts=0, delay=0.0, payload=None):
    """Queue a job unless the same kind/target is already waiting or running."""
    conn = connect()
    existing = conn.execute(
        "SELECT id, priority FROM jobs WHERE kind=? AND target=? AND status IN ('queued','running')",
        (kind, target),
    ).fetchone()
    if existing:
        if priority > existing["priority"]:
            conn.execute("UPDATE jobs SET priority=?, not_before=MIN(not_before, ?) WHERE id=? AND status='queued'",
                         (priority, time.time() + delay, existing["id"]))
        return existing["id"]
    now = time.time()
    cur = conn.execute(
        """INSERT INTO jobs(kind, target, lane, priority, sort_ts, not_before, status, payload, created_at, updated_at)
           VALUES (?,?,?,?,?,?,'queued',?,?,?)""",
        (kind, target, LANES[kind], priority, sort_ts, now + delay, payload, now, now),
    )
    return cur.lastrowid


def claim(lane, exclude_kinds_until=None):
    """Take the best ready job in a lane. exclude_kinds_until: {kind_prefix: ts} rate limits."""
    conn = connect()
    now = time.time()
    conn.execute("BEGIN IMMEDIATE")
    try:
        rows = conn.execute(
            """SELECT * FROM jobs WHERE lane=? AND status='queued' AND not_before<=?
               ORDER BY priority DESC, sort_ts DESC, id LIMIT 50""",
            (lane, now),
        ).fetchall()
        chosen = None
        for row in rows:
            if exclude_kinds_until and not exclude_kinds_until(row):
                continue
            chosen = row
            break
        if chosen:
            conn.execute("UPDATE jobs SET status='running', attempts=attempts+1, updated_at=? WHERE id=?",
                         (now, chosen["id"]))
        conn.execute("COMMIT")
        return chosen
    except Exception:
        conn.execute("ROLLBACK")
        raise


def finish(job_id, status="done", error=None):
    connect().execute("UPDATE jobs SET status=?, error=?, updated_at=? WHERE id=?",
                      (status, error, time.time(), job_id))


def retry_later(job_id, delay, error=None):
    connect().execute("UPDATE jobs SET status='queued', not_before=?, error=?, updated_at=? WHERE id=?",
                      (time.time() + delay, error, time.time(), job_id))


def reset_running():
    connect().execute("UPDATE jobs SET status='queued' WHERE status='running'")


def prune_jobs(days=7):
    connect().execute("DELETE FROM jobs WHERE status IN ('done','failed') AND updated_at<?",
                      (time.time() - days * 86400,))


def job_stats():
    conn = connect()
    return conn.execute(
        "SELECT kind, status, COUNT(*) AS n FROM jobs GROUP BY kind, status ORDER BY kind, status"
    ).fetchall()
