import asyncio
import logging
import uuid

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from . import config

log = logging.getLogger(__name__)

_NAMESPACE = uuid.UUID("6f1d2c9e-3b7a-4c55-9a1e-2d8f0b6c4a11")


def make_client() -> AsyncQdrantClient:
    return AsyncQdrantClient(url=config.QDRANT_URL)


def point_id(doc_id: str, chunk_index: int) -> str:
    """Deterministic id: re-indexing the same chunk overwrites instead of duplicating."""
    return str(uuid.uuid5(_NAMESPACE, f"{doc_id}:{chunk_index}"))


async def ensure_collection(client: AsyncQdrantClient, dim: int, attempts: int = 30, delay: float = 2.0):
    """Create the collection if missing. Retries so services can start in any order."""
    for attempt in range(1, attempts + 1):
        try:
            if not await client.collection_exists(config.COLLECTION):
                await client.create_collection(
                    config.COLLECTION,
                    vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
                )
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


async def upsert_chunk(client: AsyncQdrantClient, *, doc_id: str, chunk_index: int,
                       filename: str, text: str, vector: list[float]):
    await client.upsert(
        config.COLLECTION,
        points=[
            PointStruct(
                id=point_id(doc_id, chunk_index),
                vector=vector,
                payload={"doc_id": doc_id, "chunk_index": chunk_index,
                         "filename": filename, "text": text},
            )
        ],
    )


async def search(client: AsyncQdrantClient, vector: list[float], limit: int = 5) -> list[dict]:
    res = await client.query_points(
        config.COLLECTION, query=vector, limit=limit, with_payload=True
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
