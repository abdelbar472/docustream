"""Embedders. The pipeline only needs .dim and .embed(list[str]) -> list[list[float]].

- HashEmbedder (default): hashed bag-of-words. Deterministic, no model download, but it only
  matches on shared words (lexical), not meaning.
- FastEmbedder (EMBEDDER=fastembed): real semantic embeddings via the optional astembed package.
- LCEmbeddings (EMBEDDER=langchain or lc): LangChain-based embeddings.
"""
import hashlib
import math
import re
from functools import lru_cache

from . import config

_TOKEN = re.compile(r"[a-z0-9]+")


class HashEmbedder:
    dim = 256

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in _TOKEN.findall(text.lower()):
            h = int.from_bytes(hashlib.blake2b(tok.encode(), digest_size=8).digest(), "big")
            sign = 1.0 if (h >> 40) & 1 else -1.0
            vec[h % self.dim] += sign
        norm = math.sqrt(sum(v * v for v in vec))
        return [v / norm for v in vec] if norm else vec


class FastEmbedder:
    dim = 384

    def __init__(self):
        from fastembed import TextEmbedding  # optional dependency

        self._model = TextEmbedding("BAAI/bge-small-en-v1.5")

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._model.embed(texts)]


class LCEmbeddings:
    """LangChain embeddings wrapper."""
    def __init__(self):
        try:
            from langchain_huggingface import HuggingFaceEmbeddings
            self._embeddings = HuggingFaceEmbeddings(
                model_name="sentence-transformers/all-MiniLM-L6-v2"
            )
        except Exception:
            try:
                from langchain_community.embeddings import HuggingFaceEmbeddings
                self._embeddings = HuggingFaceEmbeddings(
                    model_name="sentence-transformers/all-MiniLM-L6-v2"
                )
            except Exception:
                raise
        sample = self._embeddings.embed_query("test")
        self.dim = len(sample) if hasattr(sample, "__len__") else 384

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embeddings.embed_query(t) for t in texts]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        try:
            return self._embeddings.embed_documents(texts)
        except Exception:
            return self.embed(texts)

    def embed_query(self, text: str) -> list[float]:
        try:
            return self._embeddings.embed_query(text)
        except Exception:
            return self.embed([text])[0]


# Alias for compatibility
LangChainEmbedder = LCEmbeddings


@lru_cache(maxsize=1)
def get_embedder():
    if config.EMBEDDER == "fastembed":
        return FastEmbedder()
    elif config.EMBEDDER in ("langchain", "lc", "langchain-huggingface"):
        return LCEmbeddings()
    return HashEmbedder()
