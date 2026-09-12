"""Local RAG: ingest reference documents and retrieve relevant passages.

Embeddings are served by nomic-embed-text through the same LiteLLM proxy
(model name "embeddings") - everything stays on-premise. The vector store is
a plain JSON file; cosine similarity is computed with numpy (no external DB).
"""
import json
import sys

import numpy as np

from . import config
from .llm import client

STORE_PATH = config.BASE_DIR / "workbench" / "data" / "vectorstore.json"
EMBED_MODEL = "embeddings"
CHUNK_SIZE = 600
CHUNK_OVERLAP = 120


def _embed(texts: list) -> list:
    resp = client.embeddings.create(model=EMBED_MODEL, input=texts)
    return [d.embedding for d in resp.data]


def _chunk(text: str) -> list:
    text = text.strip()
    chunks, i = [], 0
    while i < len(text):
        chunks.append(text[i:i + CHUNK_SIZE])
        i += CHUNK_SIZE - CHUNK_OVERLAP
    return [c for c in chunks if c.strip()]


def _load() -> dict:
    if STORE_PATH.exists():
        return json.loads(STORE_PATH.read_text(encoding="utf-8"))
    return {"chunks": []}


def ingest(paths: list) -> str:
    from .tools import resolve_path  # late import avoids a module cycle
    store = _load()
    n = 0
    for p in paths:
        fp = resolve_path(p)
        chunks = _chunk(fp.read_text(encoding="utf-8", errors="ignore"))
        for c, e in zip(chunks, _embed(chunks)):
            store["chunks"].append({
                "text": c,
                "source": str(fp.relative_to(config.BASE_DIR)),
                "embedding": e,
            })
        n += len(chunks)
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORE_PATH.write_text(json.dumps(store), encoding="utf-8")
    return f"ingested {n} chunks from {len(paths)} file(s); store holds {len(store['chunks'])} chunks"


def search(query: str, top_k: int = 4, min_score: float = 0.35) -> str:
    store = _load()
    if not store["chunks"]:
        return "Vector store is empty - no reference documents have been ingested yet."
    q = np.array(_embed([query])[0], dtype=np.float32)
    m = np.array([c["embedding"] for c in store["chunks"]], dtype=np.float32)
    sims = (m @ q) / (np.linalg.norm(m, axis=1) * np.linalg.norm(q) + 1e-9)
    out = []
    for i in np.argsort(-sims)[:top_k]:
        if sims[int(i)] < min_score:
            continue
        c = store["chunks"][int(i)]
        out.append(f"[score {sims[int(i)]:.3f} | {c['source']}]\n{c['text']}")
    if not out:
        return ("NO_RELEVANT_DOCUMENTS_FOUND: nothing in the ingested reference set is "
                "closely related to this query. Do not use these results to ground an "
                "answer - either answer from general knowledge or say you do not have "
                "grounded plant-specific information on this.")
    return "\n\n---\n\n".join(out)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "ingest":
        print(ingest(sys.argv[2:]))
    elif len(sys.argv) >= 3 and sys.argv[1] == "search":
        print(search(" ".join(sys.argv[2:])))
    else:
        print("usage: python -m workbench.rag ingest <files...> | search <query>")
