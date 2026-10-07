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
    )


if __name__ == "__main__":
    asyncio.run(main())
