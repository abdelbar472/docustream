"""Stage 1: documents.uploaded -> split into chunks -> chunks.created.

Run several copies (same consumer group) to split the topic's partitions between them.
"""
import asyncio
import logging

from . import config, db
from .chunking import split_text
from .kafka_utils import make_producer, run_worker

log = logging.getLogger("chunker")


async def handle_document(payload: dict, producer) -> None:
    doc_id = payload["doc_id"]
    chunks = split_text(payload["text"], config.CHUNK_SIZE, config.CHUNK_OVERLAP)
    if not chunks:
        raise ValueError("document has no indexable text")

    # Record the chunk count BEFORE publishing, so the indexer can tell when the doc is complete.
    await asyncio.to_thread(db.set_chunked, doc_id, len(chunks))
    await asyncio.gather(
        *(
            producer.send_and_wait(
                config.TOPIC_CHUNKS,
                {"doc_id": doc_id, "filename": payload.get("filename", ""),
                 "chunk_index": i, "text": chunk},
                key=doc_id.encode(),  # same doc -> same partition -> ordered
            )
            for i, chunk in enumerate(chunks)
        )
    )
    log.info("chunked %s into %d chunks", doc_id, len(chunks))


async def mark_dead(payload: dict | None, error: Exception) -> None:
    if payload and payload.get("doc_id"):
        await asyncio.to_thread(db.mark_failed, payload["doc_id"], f"chunker: {error}")


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    await asyncio.to_thread(db.init_db)
    producer = await make_producer("chunker")
    await run_worker(
        name="chunker",
        topic=config.TOPIC_DOCS,
        group="chunker",
        producer=producer,
        handler=lambda payload: handle_document(payload, producer),
        on_dead=mark_dead,
    )


if __name__ == "__main__":
    asyncio.run(main())
