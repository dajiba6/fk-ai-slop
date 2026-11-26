"""Retrieval shared by the website and MCP. Swap this module's internals to move off sqlite-vec."""
import json
import logging
from datetime import datetime, timezone

import httpx

from fkslop import config, db, indexer, store

log = logging.getLogger("fkslop")


def timed_url(item, start):
    if start is None or item["kind"] != "video":
        return item["url"]
    seconds = int(start)
    if item["platform"] == "youtube":
        return f"https://www.youtube.com/watch?v={item['id'].split('-', 1)[1]}&t={seconds}s"
    return f"https://www.bilibili.com/video/{item['id'].split('-', 1)[1]}?t={seconds}"


def _ts(value, end=False):
    if not value:
        return None
    text = str(value)
    if len(text) == 7:
        year, month = int(text[:4]), int(text[5:7])
        if end:
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)
            return int(datetime(year, month, 1, tzinfo=timezone.utc).timestamp()) - 1
        return int(datetime(year, month, 1, tzinfo=timezone.utc).timestamp())
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    stamp = int(moment.timestamp())
    return stamp + 86399 if end and len(text) == 10 else stamp


def _item_filters(author=None, source=None, platform=None, title=None, date_from=None, date_to=None):
    clauses, params = [], []
    if author:
        clauses.append("i.author LIKE ?")
        params.append(f"%{author}%")
    if source:
        clauses.append("(i.source_id = ? OR i.source_id IN (SELECT id FROM src_names WHERE name LIKE ?))")
        params += [source, f"%{source}%"]
    if platform:
        clauses.append("i.platform = ?")
        params.append(platform)
    if title:
        clauses.append("i.title LIKE ?")
        params.append(f"%{title}%")
    if date_from:
        clauses.append("i.published_ts >= ?")
        params.append(_ts(date_from))
    if date_to:
        clauses.append("i.published_ts <= ?")
        params.append(_ts(date_to, end=True))
    return clauses, params


def _with_source_names(conn):
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS src_names (id TEXT PRIMARY KEY, name TEXT)")
    conn.execute("DELETE FROM src_names")
    conn.executemany("INSERT OR REPLACE INTO src_names VALUES (?,?)",
                     [(s["id"], s.get("name") or s["id"]) for s in store.load_sources()])


def _hit(row, score):
    item = dict(row)
    return {
        "item_id": item["id"], "title": item["title"], "author": item["author"], "platform": item["platform"],
        "source_id": item["source_id"], "published": item["published"], "chunk": item.get("seq"),
        "start": item.get("start"), "section": item.get("section"),
        "url": timed_url(item, item.get("start")), "text": item.get("text"), "score": round(score, 4),
    }


def search(query=None, author=None, source=None, platform=None, title=None, date_from=None, date_to=None,
           mode="semantic", top_k=10, per_item=2, item_ids=None):
    """item_ids limits the search to those items (e.g. favorites); an empty collection matches nothing."""
    conn = db.connect()
    _with_source_names(conn)
    top_k = max(1, min(int(top_k), 50))
    clauses, params = _item_filters(author, source, platform, title, date_from, date_to)
    if item_ids is not None:
        clauses.append(f"i.id IN ({','.join('?' * len(item_ids)) or 'NULL'})")
        params += list(item_ids)
    if not query:
        return list_items(author=author, source=source, platform=platform, title=title,
                          date_from=date_from, date_to=date_to, limit=top_k, only_ids=item_ids)
    rows = None
    if mode != "keyword" and config.EMBED_MODEL:
        # A narrow id filter is applied after the nearest-neighbour search, so search wider.
        k = 4096 if item_ids is not None else top_k * 8
        try:
            rows = _semantic(conn, query, clauses, params, platform, date_from, date_to, k)
        except httpx.HTTPError:
            log.warning("embedding service unavailable, falling back to keyword search")
    if rows is None:
        rows = _keyword(conn, query, clauses, params, top_k * 8)
    hits, per = [], {}
    for row, score in rows:
        if per.get(row["id"], 0) >= per_item:
            continue
        per[row["id"]] = per.get(row["id"], 0) + 1
        hits.append(_hit(row, score))
        if len(hits) >= top_k:
            break
    return hits


SELECT_HIT = """SELECT i.*, c.id AS chunk_id, c.seq, c.start, c.section, c.text
                FROM chunks c JOIN items i ON i.id = c.item_id"""


def _semantic(conn, query, clauses, params, platform, date_from, date_to, k):
    vector = json.dumps(indexer.query_vector(query))
    vec_where, vec_params = ["embedding MATCH ?", "k = ?"], [vector, min(k, 4096)]
    if platform:
        vec_where.append("platform = ?")
        vec_params.append(platform)
    if date_from:
        vec_where.append("published_ts >= ?")
        vec_params.append(_ts(date_from))
    if date_to:
        vec_where.append("published_ts <= ?")
        vec_params.append(_ts(date_to, end=True))
    knn = conn.execute(f"SELECT rowid, distance FROM chunk_vec WHERE {' AND '.join(vec_where)}",
                       vec_params).fetchall()
    if not knn:
        return []
    distance = {r["rowid"]: r["distance"] for r in knn}
    marks = ",".join("?" * len(distance))
    where = " AND ".join([f"c.id IN ({marks})"] + clauses)
    rows = conn.execute(f"{SELECT_HIT} WHERE {where}", list(distance) + params).fetchall()
    return sorted(((row, 1 - distance[row["chunk_id"]]) for row in rows), key=lambda pair: -pair[1])


def _keyword(conn, query, clauses, params, k):
    query = query.strip()
    results = []
    title_where = " AND ".join(["i.title LIKE ?"] + clauses)
    for row in conn.execute(
            f"""SELECT i.*, c.seq, c.start, c.section, c.text FROM items i
                LEFT JOIN chunks c ON c.item_id = i.id AND c.seq = 0
                WHERE {title_where} ORDER BY i.published_ts DESC LIMIT ?""",
            [f"%{query}%"] + params + [k]):
        results.append((row, 1.0))
    where = " AND ".join(clauses) if clauses else "1"
    if len(query) >= 3:
        phrase = '"' + query.replace('"', '""') + '"'
        rows = conn.execute(
            f"""{SELECT_HIT} JOIN chunks_fts f ON f.rowid = c.id
                WHERE chunks_fts MATCH ? AND {where} ORDER BY f.rank LIMIT ?""",
            [phrase] + params + [k]).fetchall()
        results += [(row, 0.5) for row in rows]
    else:
        rows = conn.execute(f"{SELECT_HIT} WHERE c.text LIKE ? AND {where} ORDER BY i.published_ts DESC LIMIT ?",
                            [f"%{query}%"] + params + [k]).fetchall()
        results += [(row, 0.5) for row in rows]
    return results


def list_items(author=None, source=None, platform=None, title=None, date_from=None, date_to=None,
               limit=20, offset=0, only_ids=None, exclude_ids=None, include_removed=True, kind=None,
               source_ids=None):
    conn = db.connect()
    _with_source_names(conn)
    clauses, params = _item_filters(author, source, platform, title, date_from, date_to)
    if source_ids:
        clauses.append(f"i.source_id IN ({','.join('?' * len(source_ids))})")
        params += list(source_ids)
    if kind:
        clauses.append("i.kind = ?")
        params.append(kind)
    if only_ids is not None:
        clauses.append(f"i.id IN ({','.join('?' * len(only_ids)) or 'NULL'})")
        params += list(only_ids)
    if exclude_ids:
        clauses.append(f"i.id NOT IN ({','.join('?' * len(exclude_ids))})")
        params += list(exclude_ids)
    if not include_removed:
        removed = [s["id"] for s in store.load_sources() if s.get("removed")]
        if removed:
            clauses.append(f"i.source_id NOT IN ({','.join('?' * len(removed))})")
            params += removed
    where = " AND ".join(clauses) if clauses else "1"
    rows = conn.execute(f"SELECT i.* FROM items i WHERE {where} ORDER BY i.published_ts DESC LIMIT ? OFFSET ?",
                        params + [int(limit), int(offset)]).fetchall()
    return [dict(row) for row in rows]


def count_items(**filters):
    conn = db.connect()
    _with_source_names(conn)
    clauses, params = _item_filters(**filters)
    where = " AND ".join(clauses) if clauses else "1"
    return conn.execute(f"SELECT COUNT(*) FROM items i WHERE {where}", params).fetchone()[0]


def item_chunks(iid, start=0, limit=None):
    conn = db.connect()
    sql = "SELECT seq, start, end, section, text FROM chunks WHERE item_id=? AND seq>=? ORDER BY seq"
    args = [iid, start]
    if limit:
        sql += " LIMIT ?"
        args.append(limit)
    return [dict(r) for r in conn.execute(sql, args)]


def get_item(iid, part="summary", around_chunk=None, window=2, offset_chunk=0, limit_chunks=12):
    meta, body = store.read_item(iid)
    if meta is None:
        return {"error": f"没有这个条目：{iid}"}
    info = {k: meta.get(k) for k in ("id", "title", "author", "platform", "kind", "source_id", "url", "published",
                                     "date_approx", "duration", "transcript", "subtitle")}
    total = db.connect().execute("SELECT COUNT(*) FROM chunks WHERE item_id=?", (iid,)).fetchone()[0]
    info["chunk_count"] = total
    if part == "summary":
        info["summary"] = store.read_summary(iid) or "（还没有生成总结）"
        if meta.get("kind") == "article":
            info["excerpt"] = body[:1500]
        return info
    if around_chunk is not None:
        start = max(0, int(around_chunk) - window)
        chunks = item_chunks(iid, start, window * 2 + 1)
    elif part == "full" and meta.get("kind") == "article":
        info["body"] = body
        return info
    else:
        chunks = item_chunks(iid, int(offset_chunk), int(limit_chunks))
    row = {"id": iid, "kind": meta.get("kind"), "platform": meta.get("platform"), "url": meta.get("url")}
    for chunk in chunks:
        chunk["url"] = timed_url(row, chunk["start"])
    info["chunks"] = chunks
    if chunks and chunks[-1]["seq"] + 1 < total:
        info["next_offset_chunk"] = chunks[-1]["seq"] + 1
    return info
