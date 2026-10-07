"""Runs the whole pipeline logic without Kafka or Docker:
fake producer captures what the API/chunker publish, and we feed those messages
straight into the next stage. Qdrant runs in its in-memory local mode.
"""
import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from qdrant_client import AsyncQdrantClient

from app import api, config, db, vectorstore
from app.chunker_worker import handle_document
from app.embedder import HashEmbedder
from app.indexer_worker import handle_chunk
from app.kafka_utils import _with_retries


class FakeProducer:
    def __init__(self):
        self.sent = []  # (topic, value, key)

    async def send_and_wait(self, topic, value, key=None):
        self.sent.append((topic, value, key))


class BrokenProducer:
    async def send_and_wait(self, *a, **k):
        raise RuntimeError("broker down")


KAFKA_DOC = (
    "Kafka consumer groups let several consumers share the partitions of a topic. "
    "Each partition is read by exactly one consumer in the group, so adding consumers "
    "increases throughput until there is one consumer per partition."
)
BREAD_DOC = (
    "Sourdough bread needs a mature starter, flour, water and salt. "
    "Let the dough rise slowly overnight before baking in a hot oven."
)


@pytest.fixture
def client():
    """API wired to a fake producer and an in-memory Qdrant (no lifespan, no Kafka)."""
    embedder = HashEmbedder()
    qdrant = AsyncQdrantClient(":memory:")
    asyncio.run(vectorstore.ensure_collection(qdrant, embedder.dim))
    api.app.state.embedder = embedder
    api.app.state.qdrant = qdrant
    api.app.state.producer = FakeProducer()
    return TestClient(api.app)


def run_pipeline(client):
    """Deliver published messages stage by stage, like Kafka would."""
    producer = api.app.state.producer
    embedder, qdrant = api.app.state.embedder, api.app.state.qdrant

    docs = [v for t, v, _ in producer.sent if t == config.TOPIC_DOCS]
    chunker_out = FakeProducer()
    for payload in docs:
        asyncio.run(handle_document(payload, chunker_out))

    for topic, payload, _ in chunker_out.sent:
        assert topic == config.TOPIC_CHUNKS
        asyncio.run(handle_chunk(payload, qdrant, embedder))
    return chunker_out


def test_upload_end_to_end_then_search(client):
    r1 = client.post("/documents/text", json={"title": "kafka.md", "text": KAFKA_DOC})
    r2 = client.post("/documents", files={"file": ("bread.txt", BREAD_DOC.encode(), "text/plain")})
    assert r1.status_code == 202 and r2.status_code == 202

    run_pipeline(client)

    for r in (r1, r2):
        doc = client.get(f"/documents/{r.json()['doc_id']}").json()
        assert doc["status"] == "indexed"
        assert doc["indexed_chunks"] == doc["total_chunks"] >= 1

    hits = client.get("/search", params={"q": "how do consumers share partitions"}).json()["results"]
    assert hits[0]["filename"] == "kafka.md"

    hits = client.get("/search", params={"q": "baking sourdough starter"}).json()["results"]
    assert hits[0]["filename"] == "bread.txt"


def test_redelivery_is_idempotent(client):
    client.post("/documents/text", json={"title": "kafka.md", "text": KAFKA_DOC})
    run_pipeline(client)
    run_pipeline(client)  # Kafka delivers everything a second time

    stored = asyncio.run(api.app.state.qdrant.count(config.COLLECTION)).count
    doc = client.get("/documents").json()["documents"][0]
    assert stored == doc["total_chunks"]  # no duplicate points
    assert doc["indexed_chunks"] == doc["total_chunks"]
    assert doc["status"] == "indexed"


def test_multi_chunk_document_completes(client, monkeypatch):
    monkeypatch.setattr(config, "CHUNK_SIZE", 120)
    monkeypatch.setattr(config, "CHUNK_OVERLAP", 20)
    r = client.post("/documents/text", json={"title": "long.txt", "text": (KAFKA_DOC + " ") * 4})
    out = run_pipeline(client)
    assert len(out.sent) > 1
    assert client.get(f"/documents/{r.json()['doc_id']}").json()["status"] == "indexed"


def test_published_messages_are_keyed_by_doc_id(client):
    r = client.post("/documents/text", json={"title": "kafka.md", "text": KAFKA_DOC})
    topic, value, key = api.app.state.producer.sent[0]
    assert topic == config.TOPIC_DOCS
    assert key == r.json()["doc_id"].encode()
    json.dumps(value)  # must be JSON-serializable


def test_validation_errors(client):
    assert client.post("/documents/text", json={"title": "x", "text": "   "}).status_code == 400
    bad = client.post("/documents", files={"file": ("x.bin", b"\xff\xfe\x00\x80", "application/octet-stream")})
    assert bad.status_code == 400
    assert client.get("/search", params={"q": "  "}).status_code == 400
    assert client.get("/search", params={"q": "!!!"}).status_code == 400
    assert client.get("/documents/nope").status_code == 404


def test_oversize_upload_rejected(client, monkeypatch):
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 10)
    r = client.post("/documents", files={"file": ("big.txt", b"a" * 11, "text/plain")})
    assert r.status_code == 413


def test_kafka_down_returns_503_and_marks_document_failed(client):
    api.app.state.producer = BrokenProducer()
    r = client.post("/documents/text", json={"title": "kafka.md", "text": KAFKA_DOC})
    assert r.status_code == 503
    failed = client.get("/documents", params={"status": "failed"}).json()["documents"]
    assert len(failed) == 1 and "publish failed" in failed[0]["error"]


def test_chunker_rejects_text_without_words():
    doc_id = db.create_document("empty.txt")
    with pytest.raises(ValueError, match="no indexable text"):
        asyncio.run(handle_document({"doc_id": doc_id, "filename": "empty.txt", "text": "-----"}, FakeProducer()))


def test_retry_wrapper_retries_then_succeeds_or_raises(monkeypatch):
    monkeypatch.setattr(config, "MAX_ATTEMPTS", 3)
    monkeypatch.setattr(config, "RETRY_BACKOFF", 0.0)

    calls = {"n": 0}

    async def flaky(payload):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("transient")

    asyncio.run(_with_retries("t", flaky, {}))
    assert calls["n"] == 3

    async def always_fails(payload):
        raise RuntimeError("poison")

    with pytest.raises(RuntimeError, match="poison"):
        asyncio.run(_with_retries("t", always_fails, {}))
