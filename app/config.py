import os

BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")

TOPIC_DOCS = "documents.uploaded"
TOPIC_CHUNKS = "chunks.created"
TOPIC_DLQ = "documents.dlq"

SQLITE_PATH = os.getenv("SQLITE_PATH", "rag.db")

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION = os.getenv("QDRANT_COLLECTION", "chunks")

# "hash" (default, no downloads, lexical) or "fastembed" (semantic, downloads a model)
EMBEDDER = os.getenv("EMBEDDER", "hash")

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "800"))        # characters
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "100"))  # characters

MAX_ATTEMPTS = int(os.getenv("MAX_ATTEMPTS", "3"))
RETRY_BACKOFF = float(os.getenv("RETRY_BACKOFF", "1.0"))  # seconds, doubles each attempt

# Kafka's default max message size is ~1 MB; stay well below it.
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", "500000"))
