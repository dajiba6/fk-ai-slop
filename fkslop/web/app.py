"""JSON API for the React frontend, plus thumbnails, /mcp and the built SPA."""
import contextlib
import hashlib
import hmac
import logging
from datetime import date

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

from fkslop import chunking, config, db, favorites, pipeline, store, worker
from fkslop import search as retrieval
from fkslop.mcp_server import server as mcp_server

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("fkslop")

DIST = config.ROOT / "frontend" / "dist"
PAGE_SIZE = 25
COOKIE = "fk_admin"

mcp_app = mcp_server.streamable_http_app(streamable_http_path="/", stateless_http=True, json_response=True,
                                         host="0.0.0.0")


@contextlib.asynccontextmanager
async def lifespan(_app):
    db.connect()
    worker.start()
    async with mcp_server.session_manager.run():
        yield
    worker.stop()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


class McpAuth:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers") or [])
            given = headers.get(b"authorization", b"").decode()
            if not config.ADMIN_KEY or not hmac.compare_digest(given, f"Bearer {config.ADMIN_KEY}"):
                await JSONResponse({"error": "unauthorized"}, status_code=401)(scope, receive, send)
                return
        await self.inner(scope, receive, send)


app.mount("/mcp", McpAuth(mcp_app))


# ---------- helpers ----------

def admin_token():
    return hmac.new(config.ADMIN_KEY.encode(), b"fk-admin", hashlib.sha256).hexdigest()


def is_admin(request):
    return bool(config.ADMIN_KEY) and hmac.compare_digest(request.cookies.get(COOKIE, ""), admin_token())


def require_admin(request):
    if not is_admin(request):
        raise HTTPException(status_code=403, detail="需要管理密钥")


def public_source(source):
    return {k: source.get(k) for k in ("id", "platform", "name", "url", "removed", "last_polled")}


def reading_state(request):
    """Read / watch-later / favorite lists are private: visitors who are not logged in see none."""
    if not is_admin(request):
        return set(), set(), set()
    state = store.load_state()
    return set(state.get("read") or []), set(state.get("later") or []), set(state.get("favorite") or [])


def feed_items(rows, request):
    read, later, favorite = reading_state(request)
    sources = {s["id"]: s for s in store.load_sources()}
    out = []
    for row in rows:
        source = sources.get(row["source_id"])
        out.append({
            "id": row["id"], "kind": row["kind"], "platform": row["platform"], "title": row["title"],
            "author": row["author"], "source_id": row["source_id"],
            "source_name": (source or {}).get("name") or row["author"] or "手动投递",
            "published": row["published"], "date_approx": bool(row["date_approx"]), "duration": row["duration"],
            "excerpt": row["description"], "has_thumb": bool(row["has_thumb"]),
            "has_summary": bool(row["has_summary"]), "transcript": row["transcript"],
            "read": row["id"] in read, "later": row["id"] in later, "favorite": row["id"] in favorite,
        })
    return out


def page(rows, request):
    return {"items": feed_items(rows[:PAGE_SIZE], request), "has_more": len(rows) > PAGE_SIZE}


def paragraphs(cues, chapters):
    """Group cues into ~60-second paragraphs, breaking at chapter starts."""
    starts = sorted((c.get("start_time") or 0, c.get("title")) for c in chapters or [])
    out, current, chapter_index = [], None, 0
    for cue in cues:
        heading = None
        while chapter_index < len(starts) and cue["start"] >= starts[chapter_index][0]:
            heading = starts[chapter_index][1]
            chapter_index += 1
        elapsed = cue["start"] - current["start"] if current else 0
        if heading or current is None or elapsed >= 90 or \
                (elapsed >= 60 and current["texts"][-1][-1:] in ".?!。？！"):
            current = {"start": cue["start"], "texts": [], "heading": heading}
            out.append(current)
        current["texts"].append(cue["text"])
    for paragraph in out:
        paragraph["text"] = chunking.join_cues(paragraph.pop("texts"))
    return out


def summary_job(iid):
    row = db.connect().execute(
        "SELECT status, error FROM jobs WHERE kind='summary' AND target=? ORDER BY id DESC LIMIT 1", (iid,)
    ).fetchone()
    return dict(row) if row else None


# ---------- reading ----------

@app.get("/api/site")
def site():
    return {"name": config.SITE_NAME, "features": {"summary": config.LLM_ENABLED, "asr": config.ASR_ENABLED}}


@app.get("/api/feed")
def feed(request: Request, tab: str = "all", source: str = "", kind: str = "", page_no: int = 1):
    if tab in ("later", "unread", "favorite"):
        require_admin(request)
    read, later, favorite = reading_state(request)
    source_ids = [s for s in source.split(",") if s]
    rows = retrieval.list_items(
        source_ids=source_ids, kind=kind or None, limit=PAGE_SIZE + 1, offset=(page_no - 1) * PAGE_SIZE,
        include_removed=bool(source_ids),
        only_ids={"later": later, "favorite": favorite}.get(tab),
        exclude_ids=read if tab == "unread" else None)
    return page(rows, request)


@app.get("/api/sources")
def sources():
    return [public_source(s) for s in store.load_sources()]


@app.get("/api/sources/{source_id}")
def source_detail(source_id: str):
    source = store.get_source(source_id)
    if source is None and source_id != "manual":
        raise HTTPException(404, "没有这个来源")
    source = source or {"id": "manual", "name": "手动投递", "platform": "manual"}
    return {**public_source(source), "total": retrieval.count_items(source=source_id)}


@app.get("/api/archive")
def archive(request: Request, source: str = "", platform: str = "", month: str = "", page_no: int = 1):
    rows = retrieval.list_items(source=source or None, platform=platform or None, date_from=month or None,
                                date_to=month or None, limit=PAGE_SIZE + 1, offset=(page_no - 1) * PAGE_SIZE)
    months = [r[0] for r in db.connect().execute(
        "SELECT DISTINCT substr(published,1,7) m FROM items WHERE published != '' ORDER BY m DESC")]
    return {**page(rows, request), "months": months}


@app.get("/api/items/{iid}")
def item_detail(request: Request, iid: str):
    meta, body = store.read_item(iid)
    if meta is None:
        raise HTTPException(404, "没有这个条目")
    if is_admin(request):
        pipeline.demand(iid)
        meta, body = store.read_item(iid)
    summary = store.read_summary(iid)
    job = summary_job(iid)
    if is_admin(request) and (summary is not None or (job and job["status"] == "failed")):
        store.watch_summary(iid, False)
    subtitle = (meta.get("subtitle") or "").strip()
    if summary and subtitle and summary.startswith(subtitle):
        summary = summary[len(subtitle):].strip()
    read, later, favorite = reading_state(request)
    source = store.get_source(meta.get("source_id") or "")
    return {
        "item": {k: meta.get(k) for k in (
            "id", "kind", "platform", "native_id", "title", "subtitle", "author", "url", "published",
            "date_approx", "duration", "transcript", "transcript_method", "transcript_note", "body_status",
            "source_id", "audio_url")},
        "source": public_source(source) if source else None,
        "body": body if meta.get("kind") == "article" or meta.get("platform") in ("xiaohongshu", "podcast") else "",
        "paragraphs": paragraphs(store.read_transcript(iid), meta.get("chapters")),
        "summary": summary,
        "summary_job": job,
        "read": iid in read,
        "later": iid in later,
        "favorite": iid in favorite,
    }


@app.get("/api/items/{iid}/status")
def item_status(iid: str):
    meta, _ = store.read_item(iid)
    if meta is None:
        raise HTTPException(404)
    job = summary_job(iid)
    return {"transcript": meta.get("transcript"), "body_status": meta.get("body_status"),
            "summary": store.read_summary(iid) is not None, "summary_job": job["status"] if job else None}


class Flag(BaseModel):
    on: bool


@app.post("/api/items/{iid}/flags/{flag}")
def set_flag(request: Request, iid: str, flag: str, payload: Flag):
    require_admin(request)
    if flag not in ("read", "later", "favorite"):
        raise HTTPException(400)
    store.set_flag(iid, flag, payload.on)
    if flag == "favorite":
        favorites.refresh(iid)
    return {"on": payload.on}


@app.post("/api/items/{iid}/transcribe")
def transcribe(request: Request, iid: str):
    require_admin(request)
    meta, _ = store.read_item(iid)
    if meta is None or meta.get("kind") != "video":
        raise HTTPException(404)
    pipeline.request_transcript(meta)
    return {"ok": True}


@app.post("/api/items/{iid}/summarize")
def summarize(request: Request, iid: str):
    require_admin(request)
    if store.read_item(iid)[0] is None:
        raise HTTPException(404)
    pipeline.request_summary(iid)
    store.watch_summary(iid, True)
    return {"ok": True}


TRANSCRIBING = ("pending", "asr_queued", "asr_running")


@app.get("/api/summaries")
def summary_tasks(request: Request):
    """The summary dock: queued / transcribing / summarizing / done / failed, oldest request first."""
    if not is_admin(request):
        return []
    out = []
    for iid in store.load_state().get("summary_watch") or []:
        meta, _ = store.read_item(iid)
        if meta is None:
            continue
        job = summary_job(iid)
        error = None
        if store.read_summary(iid) is not None:
            status = "done"
        elif job and job["status"] == "failed":
            status, error = "failed", job["error"]
        elif meta.get("kind") == "video" and meta.get("transcript") in TRANSCRIBING:
            status = "transcribing"
        elif job and job["status"] == "running":
            status = "summarizing"
        else:
            status = "queued"
        out.append({"id": iid, "title": meta.get("title"), "has_thumb": store.thumb_path(iid).is_file(),
                    "status": status, "error": error})
    return out


@app.delete("/api/summaries/{iid}")
def dismiss_summary(request: Request, iid: str):
    require_admin(request)
    store.watch_summary(iid, False)
    return {"ok": True}


@app.get("/api/search")
def search(q: str, mode: str = "semantic"):
    if not q.strip():
        return []
    try:
        return retrieval.search(q.strip(), mode=mode, top_k=30)
    except Exception as exc:
        log.exception("search failed")
        raise HTTPException(502, f"搜索失败：{str(exc)[:200]}")


@app.get("/thumb/{iid}")
def thumb(iid: str):
    path = store.thumb_path(iid)
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, headers={"Cache-Control": "public, max-age=604800"})


# ---------- admin ----------

class Key(BaseModel):
    key: str


class Url(BaseModel):
    url: str


class Since(BaseModel):
    since: str = ""

    @field_validator("since")
    @classmethod
    def iso_date(cls, value):
        if value:
            date.fromisoformat(value)
        return value


class NewSource(Url, Since):
    since: str | None = None


@app.get("/api/admin/me")
def admin_me(request: Request):
    return {"admin": is_admin(request), "configured": bool(config.ADMIN_KEY)}


@app.post("/api/admin/login")
def admin_login(payload: Key):
    if not config.ADMIN_KEY or not hmac.compare_digest(payload.key, config.ADMIN_KEY):
        raise HTTPException(401, "密钥不对")
    response = JSONResponse({"admin": True})
    response.set_cookie(COOKIE, admin_token(), max_age=30 * 86400, httponly=True, samesite="lax")
    return response


@app.post("/api/admin/logout")
def admin_logout():
    response = JSONResponse({"admin": False})
    response.delete_cookie(COOKIE)
    return response


@app.get("/api/admin/overview")
def admin_overview(request: Request):
    require_admin(request)
    conn = db.connect()
    counts = {r["source_id"]: r["n"] for r in conn.execute(
        "SELECT source_id, COUNT(*) n FROM items GROUP BY source_id")}
    transcripts = {r["source_id"]: r["n"] for r in conn.execute(
        "SELECT source_id, COUNT(*) n FROM items WHERE transcript='ok' GROUP BY source_id")}
    embedded = conn.execute("SELECT COALESCE(SUM(embedded), 0), COUNT(*) FROM chunks").fetchone()
    return {
        "sources": [{**public_source(s), "last_error": s.get("last_error"), "since": s.get("since"),
                     "items": counts.get(s["id"], 0),
                     "transcripts": transcripts.get(s["id"], 0)}
                    for s in store.load_sources()],
        "jobs": [dict(r) for r in db.job_stats()],
        "failures": [dict(r) for r in conn.execute(
            "SELECT kind, target, error, updated_at FROM jobs WHERE status='failed' "
            "ORDER BY updated_at DESC LIMIT 15")],
        "embedded": {"done": embedded[0], "total": embedded[1]},
    }


@app.post("/api/admin/sources")
def admin_add_source(request: Request, payload: NewSource):
    require_admin(request)
    try:
        return public_source(pipeline.add_source(payload.url, payload.since))
    except Exception as exc:
        raise HTTPException(400, f"添加失败：{str(exc)[:200]}")


@app.post("/api/admin/sources/{source_id}/since")
def admin_set_since(request: Request, source_id: str, payload: Since):
    require_admin(request)
    if store.get_source(source_id) is None:
        raise HTTPException(404)
    pipeline.set_since(source_id, payload.since)
    return {"ok": True}


@app.post("/api/admin/sources/{source_id}/remove")
def admin_remove_source(request: Request, source_id: str):
    require_admin(request)
    pipeline.remove_source(source_id)
    return {"ok": True}


@app.post("/api/admin/sources/{source_id}/restore")
def admin_restore_source(request: Request, source_id: str):
    require_admin(request)
    store.update_source(source_id, removed=False)
    db.enqueue("poll", source_id, priority=pipeline.PRIO_SOURCE)
    return {"ok": True}


@app.post("/api/admin/submit")
def admin_submit(request: Request, payload: Url):
    require_admin(request)
    try:
        result = pipeline.submit_url(payload.url)
    except Exception as exc:
        raise HTTPException(400, f"投递失败：{str(exc)[:200]}")
    if "source" in result:
        return {"source": public_source(result["source"])}
    return result


@app.post("/api/admin/poll")
def admin_poll(request: Request):
    require_admin(request)
    return {"queued": pipeline.poll_all()}


# ---------- SPA ----------

if (DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    if path.startswith("api/"):
        raise HTTPException(404)
    target = (DIST / path).resolve()
    if path and target.is_file() and DIST.resolve() in target.parents:
        return FileResponse(target)
    index = DIST / "index.html"
    if not index.is_file():
        return JSONResponse({"error": "前端还没构建：cd frontend && npm run build"}, status_code=503)
    return FileResponse(index, headers={"Cache-Control": "no-cache"})


def main():
    import uvicorn
    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="info")


if __name__ == "__main__":
    main()
