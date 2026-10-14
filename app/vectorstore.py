import asyncio
import logging
import uuid

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
    VectorParams,
)

from . import config

log = logging.getLogger(__name__)

_NAMESPACE = uuid.UUID("6f1d2c9e-3b7a-4c55-9a1e-2d8f0b6c4a11")


def make_client() -> AsyncQdrantClient:
    return AsyncQdrantClient(url=config.QDRANT_URL)


def point_id(doc_id: str, chunk_index: int) -> str:
    """Deterministic id: re-indexing the same chunk overwrites instead of duplicating."""
    return str(uuid.uuid5(_NAMESPACE, f"{doc_id}:{chunk_index}"))


async def delete_by_doc(client: AsyncQdrantClient, doc_id: str) -> None:
    """Remove every chunk belonging to a document."""
    await client.delete(
        config.COLLECTION,
        points_selector=FilterSelector(
            filter=Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))])
        ),
    )


async def ensure_collection(
    client: AsyncQdrantClient,
    dim: int,
    embedder=None,
    attempts: int = 30,
    delay: float = 2.0,
):
    """Create the collection if missing. Retries so services can start in any order.

    If the collection exists but was built with a different vector size (e.g. the
    embedder changed), it is rebuilt. When ``embedder`` is supplied the stored
    chunks are re-embedded so no data is lost.
    """
    for attempt in range(1, attempts + 1):
        try:
            if not await client.collection_exists(config.COLLECTION):
                await client.create_collection(
                    config.COLLECTION,
                    vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
                )
                return
            existing = _vector_size(await client.get_collection(config.COLLECTION))
            if existing is not None and existing != dim:
                if embedder is None:
                    # Only the API migrates; other services wait for the new dim.
                    raise RuntimeError(
                        f"collection dim {existing} != {dim}; waiting for migration"
                    )
                log.warning(
                    "collection %s has dim %s but embedder needs %s; rebuilding",
                    config.COLLECTION,
                    existing,
                    dim,
                )
                await _rebuild(client, dim, embedder)
            return
        except Exception as e:
            # another service may have created it between our check and create
            try:
                if await client.collection_exists(config.COLLECTION):
                    return
            except Exception:
                pass
            if attempt == attempts:
                raise
            log.warning("Qdrant not ready (%s), retry %d/%d", e, attempt, attempts)
            await asyncio.sleep(delay)


def _vector_size(info) -> int | None:
    vectors = getattr(getattr(info, "config", None), "params", None)
    vectors = getattr(vectors, "vectors", None)
    size = getattr(vectors, "size", None)
    return size if isinstance(size, int) else None


async def scroll_all(client: AsyncQdrantClient) -> list[dict]:
    """Read every point's payload. Fine at demo scale; used to build lexical search."""
    payloads: list[dict] = []
    offset = None
    while True:
        points, offset = await client.scroll(
            config.COLLECTION, limit=256, offset=offset, with_payload=True
        )
        payloads.extend(p.payload for p in points if p.payload)
        if offset is None:
            return payloads


async def _rebuild(client: AsyncQdrantClient, dim: int, embedder) -> None:
    payloads = await scroll_all(client)
    await client.delete_collection(config.COLLECTION)
    await client.create_collection(
        config.COLLECTION,
        vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
    )
    if not payloads or embedder is None:
        return
    for start in range(0, len(payloads), 64):
        batch = payloads[start : start + 64]
        vectors = await asyncio.to_thread(embedder.embed, [p["text"] for p in batch])
        await upsert_points(
            client,
            [
                make_point(
                    doc_id=p["doc_id"],
                    chunk_index=p["chunk_index"],
                    filename=p.get("filename", ""),
                    text=p["text"],
                    vector=v,
                )
                for p, v in zip(batch, vectors)
            ],
        )
    log.info("re-embedded %d chunks into %s", len(payloads), config.COLLECTION)


def make_point(*, doc_id: str, chunk_index: int, filename: str, text: str,
               vector: list[float]) -> PointStruct:
    return PointStruct(
        id=point_id(doc_id, chunk_index),
        vector=vector,
        payload={"doc_id": doc_id, "chunk_index": chunk_index,
                 "filename": filename, "text": text},
    )


async def upsert_points(client: AsyncQdrantClient, points: list[PointStruct]):
    if not points:
        return
    await client.upsert(config.COLLECTION, points=points)


async def upsert_chunk(client: AsyncQdrantClient, *, doc_id: str, chunk_index: int,
                       filename: str, text: str, vector: list[float]):
    await upsert_points(client, [make_point(
        doc_id=doc_id, chunk_index=chunk_index, filename=filename, text=text, vector=vector,
    )])


async def search(
    client: AsyncQdrantClient,
    vector: list[float],
    limit: int = 5,
    doc_id: str | None = None,
    filename: str | None = None,
) -> list[dict]:
    """Closest chunks by cosine similarity, optionally restricted to one document."""
    conditions = []
    if doc_id:
        conditions.append(FieldCondition(key="doc_id", match=MatchValue(value=doc_id)))
    if filename:
        conditions.append(FieldCondition(key="filename", match=MatchValue(value=filename)))
    query_filter = Filter(must=conditions) if conditions else None
    res = await client.query_points(
        config.COLLECTION,
        query=vector,
        limit=limit,
        with_payload=True,
        query_filter=query_filter,
    )
    return [
        {
            "score": round(p.score, 4),
            "doc_id": p.payload["doc_id"],
            "filename": p.payload["filename"],
            "chunk_index": p.payload["chunk_index"],
            "text": p.payload["text"],
        }
        for p in res.points
    ]
