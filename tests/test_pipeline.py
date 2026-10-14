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
from app.indexer_worker import handle_chunk, handle_chunks
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


def test_search_returns_snippets_terms_and_honors_doc_filter(client):
    r1 = client.post("/documents/text", json={"title": "kafka.md", "text": KAFKA_DOC})
    r2 = client.post("/documents/text", json={"title": "bread.txt", "text": BREAD_DOC})
    run_pipeline(client)

    body = client.get("/search", params={"q": "consumers share partitions"}).json()
    assert body["count"] >= 1
    assert "consumers" in body["terms"]

    top = body["results"][0]
    assert top["filename"] == "kafka.md"
    assert "snippet" in top
    # the snippet is scoped to the query terms rather than the chunk's head
    assert any(t in top["snippet"].lower() for t in body["terms"])

    # doc_id filter only returns that document's chunks
    bread_id = r2.json()["doc_id"]
    filtered = client.get("/search", params={"q": "consumers", "doc_id": bread_id}).json()
    assert filtered["results"]
    assert all(h["doc_id"] == bread_id for h in filtered["results"])


def test_search_deduplicates_identical_chunks(client):
    client.post("/documents/text", json={"title": "kafka.md", "text": KAFKA_DOC})
    client.post("/documents/text", json={"title": "kafka.md", "text": KAFKA_DOC})
    run_pipeline(client)

    results = client.get("/search", params={"q": "consumer groups partitions"}).json()["results"]
    keys = [(r["filename"], r["chunk_index"]) for r in results]
    assert len(keys) == len(set(keys))


def test_search_ranks_lexical_matches_first(client):
    client.post("/documents/text", json={"title": "kafka.md", "text": KAFKA_DOC})
    client.post("/documents/text", json={"title": "bread.txt", "text": BREAD_DOC})
    run_pipeline(client)

    top = client.get("/search", params={"q": "sourdough baking oven"}).json()["results"][0]
    assert top["filename"] == "bread.txt"
    assert top["match"] == 1.0
    assert top["score"] >= 0.5


def test_search_limit_is_clamped(client):
    client.post("/documents/text", json={"title": "kafka.md", "text": KAFKA_DOC})
    run_pipeline(client)

    assert client.get("/search", params={"q": "kafka", "limit": 0}).json()["count"] <= 1
    assert client.get("/search", params={"q": "kafka", "limit": 999}).status_code == 200


def test_search_stems_word_variants(client):
    """Inflected forms of a query word still match the indexed text."""
    client.post("/documents/text", json={"title": "kafka.md", "text": KAFKA_DOC})
    client.post("/documents/text", json={"title": "bread.txt", "text": BREAD_DOC})
    run_pipeline(client)

    for q in ("consuming partitions", "share a partition", "consumers"):
        top = client.get("/search", params={"q": q}).json()["results"][0]
        assert top["filename"] == "kafka.md", q


def test_search_tolerates_typos(client):
    """A misspelled query word is auto-corrected against the corpus vocabulary."""
    client.post("/documents/text", json={"title": "kafka.md", "text": KAFKA_DOC})
    run_pipeline(client)

    body = client.get("/search", params={"q": "kafka consummers"}).json()
    assert body["results"][0]["filename"] == "kafka.md"
    assert "consummers" in body["corrections"]


def test_search_reports_facets_and_filters_by_filename(client):
    client.post("/documents/text", json={"title": "kafka.md", "text": KAFKA_DOC})
    client.post("/documents/text", json={"title": "bread.txt", "text": BREAD_DOC})
    run_pipeline(client)

    body = client.get("/search", params={"q": "the"}).json()
    names = {f["filename"] for f in body["facets"]}
    assert {"kafka.md", "bread.txt"} <= names

    # selecting a filename narrows results but keeps the full facet list
    only_bread = client.get("/search", params={"q": "the", "filename": "bread.txt"}).json()
    assert only_bread["results"]
    assert all(r["filename"] == "bread.txt" for r in only_bread["results"])
    assert {"kafka.md", "bread.txt"} <= {f["filename"] for f in only_bread["facets"]}


def test_search_paginates_with_offset(client, monkeypatch):
    monkeypatch.setattr(config, "CHUNK_SIZE", 60)
    monkeypatch.setattr(config, "CHUNK_OVERLAP", 10)
    client.post("/documents/text", json={"title": "long.txt", "text": (KAFKA_DOC + " ") * 3})
    run_pipeline(client)

    page1 = client.get("/search", params={"q": "kafka", "limit": 2, "offset": 0}).json()
    assert page1["total"] > 2
    assert len(page1["results"]) == 2

    page2 = client.get("/search", params={"q": "kafka", "limit": 2, "offset": 2}).json()
    first = {(r["filename"], r["chunk_index"]) for r in page1["results"]}
    second = {(r["filename"], r["chunk_index"]) for r in page2["results"]}
    assert first.isdisjoint(second)


def test_delete_document_removes_chunks_and_vectors(client):
    r = client.post("/documents/text", json={"title": "kafka.md", "text": KAFKA_DOC})
    run_pipeline(client)
    doc_id = r.json()["doc_id"]
    assert asyncio.run(api.app.state.qdrant.count(config.COLLECTION)).count == 1

    assert client.delete(f"/documents/{doc_id}").status_code == 200
    assert client.get(f"/documents/{doc_id}").status_code == 404
    assert asyncio.run(api.app.state.qdrant.count(config.COLLECTION)).count == 0
    assert client.get("/documents").json()["count"] == 0

    assert client.delete("/documents/nope").status_code == 404


def test_stats_overview_reports_counts(client):
    client.post("/documents/text", json={"title": "kafka.md", "text": KAFKA_DOC})
    run_pipeline(client)

    ov = client.get("/stats/overview").json()
    assert ov["total_documents"] == 1
    assert ov["documents"]["indexed"] == 1
    assert ov["documents"]["failed"] == 0
    assert ov["total_chunks"] == 1
    assert ov["indexed_chunks"] == 1
    assert ov["embedder"] == "hash"
    assert ov["embedder_dim"] == 256
    assert ov["vectors"] == 1


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


def test_indexer_batch_matches_single_path(client):
    """The batch embedding/upsert path indexes the same chunks, idempotently."""
    client.post("/documents/text", json={"title": "kafka.md", "text": KAFKA_DOC})
    client.post("/documents/text", json={"title": "bread.txt", "text": BREAD_DOC})

    producer = api.app.state.producer
    embedder, qdrant = api.app.state.embedder, api.app.state.qdrant
    chunker_out = FakeProducer()
    for payload in [v for t, v, _ in producer.sent if t == config.TOPIC_DOCS]:
        asyncio.run(handle_document(payload, chunker_out))

    payloads = [v for t, v, _ in chunker_out.sent]
    assert payloads
    asyncio.run(handle_chunks(payloads, qdrant, embedder))
    asyncio.run(handle_chunks(payloads, qdrant, embedder))  # redelivery

    docs = client.get("/documents").json()["documents"]
    assert all(d["status"] == "indexed" for d in docs)
    assert all(d["indexed_chunks"] == d["total_chunks"] >= 1 for d in docs)
    stored = asyncio.run(qdrant.count(config.COLLECTION)).count
    assert stored == sum(d["total_chunks"] for d in docs)


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
