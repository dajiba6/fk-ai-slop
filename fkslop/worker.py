"""Background lanes inside the web process. Each lane runs one job at a time."""
import logging
import threading
import time

from fkslop import config, db, pipeline

log = logging.getLogger("fkslop")

_last_transcript = {}
_stop = threading.Event()


def _platform(target):
    return target.split("-", 1)[0]


def _transcript_ready(row):
    if row["kind"] != "transcript":
        return True
    return time.time() - _last_transcript.get(_platform(row["target"]), 0) >= config.TRANSCRIPT_GAP_SECONDS


def _run_lane(lane):
    while not _stop.is_set():
        if lane == "embed" and pipeline.GPU_BUSY.is_set():
            _stop.wait(5)
            continue
        try:
            job = db.claim(lane, _transcript_ready if lane == "net" else None)
        except Exception:
            log.exception("claim failed in lane %s", lane)
            time.sleep(5)
            continue
        if job is None:
            _stop.wait(2)
            continue
        if job["kind"] == "transcript":
            _last_transcript[_platform(job["target"])] = time.time()
        started = time.time()
        try:
            pipeline.HANDLERS[job["kind"]](job)
            db.finish(job["id"])
            log.info("%s %s done in %.1fs", job["kind"], job["target"], time.time() - started)
        except pipeline.Retry as exc:
            db.retry_later(job["id"], exc.delay, str(exc)[:500])
            log.warning("%s %s retry in %ss: %s", job["kind"], job["target"], exc.delay, str(exc)[:200])
        except Exception as exc:
            if job["attempts"] < 3 and job["kind"] in ("thumb", "article", "embed", "poll"):
                db.retry_later(job["id"], 600 * job["attempts"], str(exc)[:500])
            else:
                db.finish(job["id"], "failed", str(exc)[:500])
            log.warning("%s %s failed: %s", job["kind"], job["target"], str(exc)[:300])


def start():
    db.reset_running()
    db.prune_jobs()
    for lane in ("net", "media", "asr", "embed", "llm"):
        threading.Thread(target=_run_lane, args=(lane,), name=f"lane-{lane}", daemon=True).start()


def stop():
    _stop.set()
