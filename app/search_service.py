"""Search orchestration: blend vector similarity with BM25 lexical scoring.

The vector store gives semantic candidates; a cached BM25 index over the whole
corpus adds exact-word matches (with stemming and typo correction) and powers
facets/pagination. The index is rebuilt only when the number of points changes.
"""
import asyncio
from collections import Counter

from . import config, vectorstore
from .lexical import BM25, correct_terms, terms, tokenize
from .snippets import make_snippet

_cache: dict = {"client": None, "count": -1, "records": [], "bm25": None}


async def _get_index(client):
    count = (await client.count(config.COLLECTION)).count
    if (
        _cache["client"] is client
        and _cache["count"] == count
        and _cache["bm25"] is not None
    ):
        return _cache["records"], _cache["bm25"]
    records = await vectorstore.scroll_all(client)
    bm25 = BM25([terms(r.get("text", "")) for r in records])
    _cache.update(client=client, count=count, records=records, bm25=bm25)
    return records, bm25


def _overlap(qterms: list[str], text: str) -> float:
    wanted = set(qterms)
    if not wanted:
        return 0.0
    return len(wanted & set(terms(text))) / len(wanted)


async def search(
    client,
    embedder,
    q: str,
    limit: int = 5,
    doc_id: str | None = None,
    filename: str | None = None,
    offset: int = 0,
) -> dict:
    raw_terms = tokenize(q)
    stems = terms(q)

    vector = (await asyncio.to_thread(embedder.embed, [q]))[0]
    records, bm25 = await _get_index(client)
    qterms = correct_terms(stems, bm25.vocab)
    corrections = [
        raw_terms[i]
        for i in range(min(len(stems), len(raw_terms)))
        if stems[i] != qterms[i]
    ]
    bm25_scores = bm25.scores(qterms)

    candidates = min(max(limit + offset, 20) * config.SEARCH_CANDIDATE_FACTOR, 200)
    # Vector candidates are fetched without the filename filter so facets can
    # summarise every file; when a filename is selected we also fetch that
    # file directly so its chunks surface even if outside the global top-N.
    vhits = await vectorstore.search(client, vector, candidates, doc_id=doc_id)

    def keep(rec: dict) -> bool:
        return not doc_id or rec.get("doc_id") == doc_id

    combined: dict[tuple, dict] = {}
    for h in vhits:
        combined[(h["doc_id"], h["chunk_index"])] = {
            "payload": h,
            "vector": max(0.0, min(1.0, h["score"])),
            "lexical": 0.0,
        }

    if filename:
        for h in await vectorstore.search(
            client, vector, candidates, doc_id=doc_id, filename=filename
        ):
            key = (h["doc_id"], h["chunk_index"])
            entry = combined.setdefault(
                key, {"payload": h, "vector": 0.0, "lexical": 0.0}
            )
            entry["vector"] = max(entry["vector"], max(0.0, min(1.0, h["score"])))

    max_bm25 = max(bm25_scores) if bm25_scores else 0.0
    for i, rec in enumerate(records):
        score = bm25_scores[i]
        if score <= 0 or not keep(rec):
            continue
        key = (rec.get("doc_id"), rec.get("chunk_index"))
        entry = combined.setdefault(key, {"payload": rec, "vector": 0.0, "lexical": 0.0})
        entry["payload"] = rec
        entry["lexical"] = score / max_bm25 if max_bm25 > 0 else 0.0

    weight = max(0.0, min(1.0, config.SEARCH_LEXICAL_WEIGHT))
    results = []
    for entry in combined.values():
        rec = entry["payload"]
        text = rec.get("text", "")
        score = (1 - weight) * entry["vector"] + weight * entry["lexical"]
        results.append(
            {
                "score": round(score, 4),
                "match": round(_overlap(qterms, text), 4),
                "doc_id": rec.get("doc_id"),
                "filename": rec.get("filename", ""),
                "chunk_index": rec.get("chunk_index", 0),
                "text": text,
                "snippet": make_snippet(text, raw_terms + qterms),
            }
        )

    results.sort(key=lambda r: (r["score"], r["match"]), reverse=True)

    seen: set[tuple] = set()
    deduped: list[dict] = []
    for r in results:
        key = (r["filename"], r["chunk_index"], r["text"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)

    facets = [
        {"filename": name, "count": n}
        for name, n in Counter(r["filename"] for r in deduped).most_common(20)
    ]

    if filename:
        deduped = [r for r in deduped if r["filename"] == filename]

    return {
        "query": q,
        "count": len(deduped[offset : offset + limit]),
        "total": len(deduped),
        "offset": offset,
        "terms": raw_terms,
        "corrected_terms": qterms,
        "corrections": corrections,
        "facets": facets,
        "results": deduped[offset : offset + limit],
    }
