"""Stage 2: chunks.created -> embed -> upsert into Qdrant -> update document progress."""
import asyncio
import logging

from . import config, db, vectorstore
from .embedder import get_embedder
from .kafka_utils import make_producer, run_worker

log = logging.getLogger("indexer")


async def handle_chunk(payload: dict, client, embedder) -> None:
    doc_id, idx = payload["doc_id"], payload["chunk_index"]
    vector = (await asyncio.to_thread(embedder.embed, [payload["text"]]))[0]
    # deterministic point id -> a re-delivered chunk overwrites itself, no duplicates
    await vectorstore.upsert_chunk(
        client, doc_id=doc_id, chunk_index=idx,
        filename=payload.get("filename", ""), text=payload["text"], vector=vector,
    )
    indexed, total = await asyncio.to_thread(db.record_chunk_indexed, doc_id, idx)
    log.info("indexed %s chunk %d (%d/%d)", doc_id, idx, indexed, total)


async def handle_chunks(payloads: list[dict], client, embedder) -> None:
    """Batch path: embed and upsert many chunks in one pass.

    One embedding call and one Qdrant request per batch instead of per chunk — the
    main throughput win, and it matters most for real models. Idempotent for the same
    reason as the single path: ids are deterministic and progress rows are INSERT OR IGNORE.
    """
    if not payloads:
        return
    vectors = await asyncio.to_thread(embedder.embed, [p["text"] for p in payloads])
    points = [
        vectorstore.make_point(
            doc_id=p["doc_id"], chunk_index=p["chunk_index"],
            filename=p.get("filename", ""), text=p["text"], vector=vector,
        )
        for p, vector in zip(payloads, vectors)
    ]
    await vectorstore.upsert_points(client, points)
    for p in payloads:
        await asyncio.to_thread(db.record_chunk_indexed, p["doc_id"], p["chunk_index"])
    log.info("indexed batch of %d chunks", len(payloads))


async def mark_dead(payload: dict | None, error: Exception) -> None:
    if payload and payload.get("doc_id"):
        await asyncio.to_thread(db.mark_failed, payload["doc_id"], f"indexer: {error}")


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    await asyncio.to_thread(db.init_db)
    embedder = get_embedder()
    client = vectorstore.make_client()
    await vectorstore.ensure_collection(client, embedder.dim)
    producer = await make_producer("indexer")
    await run_worker(
        name="indexer",
        topic=config.TOPIC_CHUNKS,
        group="indexer",
        producer=producer,
        handler=lambda payload: handle_chunk(payload, client, embedder),
        on_dead=mark_dead,
        batch_handler=lambda payloads: handle_chunks(payloads, client, embedder),
        max_batch=config.INDEXER_BATCH_SIZE,
        batch_wait_ms=config.INDEXER_BATCH_WAIT_MS,
    )


if __name__ == "__main__":
    asyncio.run(main())
