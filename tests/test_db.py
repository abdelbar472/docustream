from app import db


def test_document_lifecycle_reaches_indexed():
    doc_id = db.create_document("a.txt")
    assert db.get_document(doc_id)["status"] == "uploaded"

    db.set_chunked(doc_id, 3)
    assert db.get_document(doc_id)["status"] == "chunked"

    for i in range(3):
        db.record_chunk_indexed(doc_id, i)

    doc = db.get_document(doc_id)
    assert doc["status"] == "indexed"
    assert doc["indexed_chunks"] == 3 and doc["total_chunks"] == 3


def test_duplicate_chunk_delivery_does_not_double_count():
    doc_id = db.create_document("a.txt")
    db.set_chunked(doc_id, 2)

    db.record_chunk_indexed(doc_id, 0)
    indexed, total = db.record_chunk_indexed(doc_id, 0)  # redelivered
    assert (indexed, total) == (1, 2)
    assert db.get_document(doc_id)["status"] == "chunked"

    db.record_chunk_indexed(doc_id, 1)
    assert db.get_document(doc_id)["status"] == "indexed"


def test_out_of_order_chunks_still_complete():
    doc_id = db.create_document("a.txt")
    db.set_chunked(doc_id, 3)
    for i in (2, 0, 1):
        db.record_chunk_indexed(doc_id, i)
    assert db.get_document(doc_id)["status"] == "indexed"


def test_redelivered_document_does_not_move_indexed_backwards():
    doc_id = db.create_document("a.txt")
    db.set_chunked(doc_id, 1)
    db.record_chunk_indexed(doc_id, 0)
    db.set_chunked(doc_id, 1)  # chunker saw the same message again
    assert db.get_document(doc_id)["status"] == "indexed"


def test_mark_failed_and_filtering():
    ok = db.create_document("ok.txt")
    bad = db.create_document("bad.txt")
    db.mark_failed(bad, "chunker: no text")

    failed = db.list_documents(status="failed")
    assert [d["id"] for d in failed] == [bad]
    assert failed[0]["error"] == "chunker: no text"
    assert db.stats() == {"uploaded": 1, "failed": 1}
    assert ok in [d["id"] for d in db.list_documents()]
