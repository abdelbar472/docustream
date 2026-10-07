"""SQLite state for documents. Shared by the API and both workers via a volume.

Status flow: uploaded -> chunked -> indexed   (or failed at any point)
"""
import sqlite3
import uuid
from contextlib import contextmanager

from . import config


@contextmanager
def connect():
    conn = sqlite3.connect(config.SQLITE_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    try:
        with conn:  # commit / rollback
            yield conn
    finally:
        conn.close()


def init_db():
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'uploaded',
                total_chunks INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS indexed_chunks (
                doc_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                PRIMARY KEY (doc_id, chunk_index)
            );
            """
        )


def create_document(filename: str) -> str:
    doc_id = uuid.uuid4().hex
    with connect() as db:
        db.execute("INSERT INTO documents (id, filename) VALUES (?, ?)", (doc_id, filename))
    return doc_id


_SELECT = """
    SELECT d.id, d.filename, d.status, d.total_chunks, d.error, d.created_at, d.updated_at,
           (SELECT COUNT(*) FROM indexed_chunks c WHERE c.doc_id = d.id) AS indexed_chunks
    FROM documents d
"""


def get_document(doc_id: str):
    with connect() as db:
        row = db.execute(_SELECT + " WHERE d.id = ?", (doc_id,)).fetchone()
    return dict(row) if row else None


def list_documents(status: str | None = None, limit: int = 50):
    with connect() as db:
        if status:
            rows = db.execute(
                _SELECT + " WHERE d.status = ? ORDER BY d.created_at DESC, d.rowid DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = db.execute(
                _SELECT + " ORDER BY d.created_at DESC, d.rowid DESC LIMIT ?", (limit,)
            ).fetchall()
    return [dict(r) for r in rows]


def stats() -> dict:
    with connect() as db:
        rows = db.execute("SELECT status, COUNT(*) AS n FROM documents GROUP BY status").fetchall()
    return {r["status"]: r["n"] for r in rows}


def set_chunked(doc_id: str, total_chunks: int):
    """Called by the chunker BEFORE it publishes chunks, so the indexer can always
    compare indexed vs total. A re-delivered message never moves 'indexed' backwards."""
    with connect() as db:
        db.execute(
            """UPDATE documents
               SET total_chunks = ?,
                   status = CASE WHEN status = 'indexed' THEN status ELSE 'chunked' END,
                   error = NULL,
                   updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (total_chunks, doc_id),
        )


def mark_failed(doc_id: str, error: str):
    with connect() as db:
        db.execute(
            "UPDATE documents SET status = 'failed', error = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE id = ?",
            (error[:500], doc_id),
        )


def record_chunk_indexed(doc_id: str, chunk_index: int) -> tuple[int, int]:
    """Idempotent: recording the same chunk twice does not double count.
    Flips the document to 'indexed' once every chunk has been recorded.
    Returns (indexed_count, total_chunks)."""
    with connect() as db:
        db.execute(
            "INSERT OR IGNORE INTO indexed_chunks (doc_id, chunk_index) VALUES (?, ?)",
            (doc_id, chunk_index),
        )
        indexed = db.execute(
            "SELECT COUNT(*) FROM indexed_chunks WHERE doc_id = ?", (doc_id,)
        ).fetchone()[0]
        total = db.execute("SELECT total_chunks FROM documents WHERE id = ?", (doc_id,)).fetchone()
        total = total[0] if total else 0
        if total > 0 and indexed >= total:
            db.execute(
                "UPDATE documents SET status = 'indexed', error = NULL, "
                "updated_at = CURRENT_TIMESTAMP WHERE id = ? AND status IN ('chunked', 'uploaded')",
                (doc_id,),
            )
    return indexed, total
