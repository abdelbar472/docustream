import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

from . import config, db, vectorstore
from .embedder import get_embedder
from .kafka_utils import make_producer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(db.init_db)
    app.state.embedder = get_embedder()
    app.state.qdrant = vectorstore.make_client()
    await vectorstore.ensure_collection(app.state.qdrant, app.state.embedder.dim)
    app.state.producer = await make_producer("api")
    try:
        yield
    finally:
        await app.state.producer.stop()
        await app.state.qdrant.close()


app = FastAPI(title="Real-time document ingestion (RAG)", lifespan=lifespan)


class TextDocument(BaseModel):
    title: str = "untitled.txt"
    text: str


async def _ingest(filename: str, text: str) -> dict:
    if not text.strip():
        raise HTTPException(status_code=400, detail="Document is empty")
    doc_id = await asyncio.to_thread(db.create_document, filename)
    try:
        await app.state.producer.send_and_wait(
            config.TOPIC_DOCS,
            {"doc_id": doc_id, "filename": filename, "text": text},
            key=doc_id.encode(),
        )
    except Exception as e:
        await asyncio.to_thread(db.mark_failed, doc_id, f"publish failed: {e}")
        raise HTTPException(status_code=503, detail=f"Kafka error: {e}")
    return {"doc_id": doc_id, "filename": filename, "status": "uploaded"}


@app.get("/health")
async def health():
    return {"status": "ok", "bootstrap": config.BOOTSTRAP, "embedder": config.EMBEDDER}


@app.post("/documents", status_code=202)
async def upload_file(file: UploadFile = File(...)):
    """Upload a .txt / .md file. Returns immediately; processing happens via Kafka."""
    data = await file.read()
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File larger than {config.MAX_UPLOAD_BYTES} bytes")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 text (.txt / .md)")
    return await _ingest(file.filename or "upload.txt", text)


@app.post("/documents/text", status_code=202)
async def upload_text(doc: TextDocument):
    """Same as /documents, but with the text in a JSON body."""
    if len(doc.text.encode("utf-8")) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"Text larger than {config.MAX_UPLOAD_BYTES} bytes")
    return await _ingest(doc.title, doc.text)


@app.get("/documents")
async def list_documents(status: str | None = None, limit: int = 50):
    """List documents. Try ?status=failed to see what ended up in the dead-letter flow."""
    docs = await asyncio.to_thread(db.list_documents, status, limit)
    return {"count": len(docs), "documents": docs}


@app.get("/documents/{doc_id}")
async def get_document(doc_id: str):
    doc = await asyncio.to_thread(db.get_document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@app.get("/stats")
async def stats():
    return await asyncio.to_thread(db.stats)


@app.get("/search")
async def search(q: str, limit: int = 5):
    """Embed the query and return the closest chunks from Qdrant."""
    if not q.strip():
        raise HTTPException(status_code=400, detail="Query is empty")
    vector = (await asyncio.to_thread(app.state.embedder.embed, [q]))[0]
    if not any(vector):
        raise HTTPException(status_code=400, detail="Query has no searchable words")
    results = await vectorstore.search(app.state.qdrant, vector, limit)
    return {"query": q, "count": len(results), "results": results}
