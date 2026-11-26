import json

import httpx

from fkslop import chunking, config, db, store


def index_item(iid, embed=True):
    """Refresh one item's row and chunks from its files, then queue vectorisation."""
    meta, body = store.read_item(iid)
    if meta is None:
        return
    db.upsert_item(meta, body)
    cues = store.read_transcript(iid)
    if cues:
        chunks = chunking.transcript_chunks(cues)
    elif meta.get("kind") == "article" and body.strip():
        chunks = chunking.markdown_chunks(body)
    else:
        chunks = []
    db.replace_chunks(iid, chunks)
    if embed and chunks and config.EMBED_MODEL:
        db.enqueue("embed", iid, priority=10, sort_ts=db.published_ts(meta.get("published")))


def refresh_row(iid):
    meta, body = store.read_item(iid)
    if meta is not None:
        db.upsert_item(meta, body)


_ollama = httpx.Client(trust_env=False)


def embed_texts(texts):
    response = _ollama.post(
        f"{config.OLLAMA_URL}/api/embed",
        json={"model": config.EMBED_MODEL, "input": texts, "keep_alive": "30m", "options": {"num_ctx": 4096}},
        timeout=600,
    )
    response.raise_for_status()
    return response.json()["embeddings"]


def unload_embedder():
    if not config.EMBED_MODEL:
        return
    try:
        _ollama.post(f"{config.OLLAMA_URL}/api/embed", json={"model": config.EMBED_MODEL, "input": [], "keep_alive": 0},
                     timeout=30)
    except httpx.HTTPError:
        pass


def query_vector(text):
    return embed_texts([text])[0]


def embed_item(iid, batch=8):
    conn = db.connect()
    item = conn.execute("SELECT * FROM items WHERE id=?", (iid,)).fetchone()
    if item is None:
        return
    rows = conn.execute("SELECT id, section, text FROM chunks WHERE item_id=? AND embedded=0 ORDER BY seq",
                        (iid,)).fetchall()
    prefix = " / ".join(x for x in (item["title"], item["author"]) if x)
    for start in range(0, len(rows), batch):
        part = rows[start:start + batch]
        texts = ["\n".join(x for x in (prefix, row["section"], row["text"]) if x) for row in part]
        vectors = embed_texts(texts)
        db.store_vectors([(row["id"], json.dumps(vec), item["platform"], item["source_id"], item["published_ts"])
                          for row, vec in zip(part, vectors)])


def rebuild():
    """Recreate the index from files. Vectors are recomputed by the embed jobs."""
    conn = db.connect()
    for table in ("items", "chunks", "chunks_fts", "chunk_vec"):
        conn.execute(f"DELETE FROM {table}")
    count = 0
    for iid in store.iter_item_ids():
        index_item(iid)
        meta, _ = store.read_item(iid)
        from fkslop import pipeline
        pipeline.requeue_unfinished(meta)
        count += 1
    return count
