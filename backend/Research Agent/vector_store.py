"""
vector_store.py

Lightweight, dependency-minimal vector store used by the RAG pipeline.

Design notes:
- Uses `sentence-transformers` for embeddings if available, otherwise falls
  back to a deterministic hashing-based embedding so the module never hard
  fails in an environment without model downloads (useful for CI / offline
  dev). Swap `_embed` for a production embedding provider as needed.
- Stores vectors in-memory per collection (pdf / notes / textbook). For
  production scale, replace `InMemoryIndex` with a real ANN backend
  (FAISS, Qdrant, Chroma, pgvector, etc.) behind the same interface.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np

logger = logging.getLogger("vector_store")

# Try to load a real embedding model; fall back gracefully.
try:
    from sentence_transformers import SentenceTransformer

    _MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    _EMBED_DIM = _MODEL.get_sentence_embedding_dimension()
    _USE_REAL_MODEL = True
    logger.info("Loaded SentenceTransformer embedding model.")
except Exception as exc:  # pragma: no cover - fallback path
    logger.warning(
        "sentence-transformers unavailable (%s); using hashing fallback embeddings.",
        exc,
    )
    _MODEL = None
    _EMBED_DIM = 384
    _USE_REAL_MODEL = False


def _hashing_embed(text: str, dim: int = _EMBED_DIM) -> np.ndarray:
    """
    Deterministic fallback embedding using hashed token buckets.
    Not semantically rich, but keeps the pipeline functional without
    network access or model weights.
    """
    vec = np.zeros(dim, dtype=np.float32)
    for token in text.lower().split():
        h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
        vec[h % dim] += 1.0
    norm = np.linalg.norm(vec)
    return vec / norm if norm > 0 else vec


@dataclass
class Document:
    """A single retrievable chunk of content."""
    doc_id: str
    text: str
    source: str  # e.g. filename, URL, note title
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: np.ndarray | None = field(default=None, repr=False)


class InMemoryIndex:
    """
    Minimal in-memory vector index with cosine-similarity search.
    Thread/async-safe for the read-mostly access pattern used here via
    an internal lock around mutation.
    """

    def __init__(self, name: str):
        self.name = name
        self._docs: list[Document] = []
        self._lock = asyncio.Lock()

    async def add(self, documents: list[Document]) -> None:
        """Embed (if needed) and add documents to the index."""
        async with self._lock:
            for doc in documents:
                if doc.embedding is None:
                    doc.embedding = await _embed_async(doc.text)
                self._docs.append(doc)
        logger.info("Indexed %d document(s) into '%s'.", len(documents), self.name)

    async def search(self, query: str, top_k: int = 5) -> list[tuple[Document, float]]:
        """Return the top_k (document, similarity_score) pairs for a query."""
        if not self._docs:
            logger.warning("Index '%s' is empty; returning no results.", self.name)
            return []

        query_vec = await _embed_async(query)
        scores = []
        async with self._lock:
            for doc in self._docs:
                sim = _cosine_similarity(query_vec, doc.embedding)
                scores.append((doc, sim))

        scores.sort(key=lambda pair: pair[1], reverse=True)
        return scores[:top_k]

    def __len__(self) -> int:
        return len(self._docs)


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


async def _embed_async(text: str) -> np.ndarray:
    """Run embedding off the event loop thread to avoid blocking async callers."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _embed_sync, text)


def _embed_sync(text: str) -> np.ndarray:
    if _USE_REAL_MODEL:
        try:
            return _MODEL.encode(text, normalize_embeddings=True)
        except Exception as exc:  # pragma: no cover
            logger.error("Embedding model failed (%s); falling back to hashing.", exc)
    return _hashing_embed(text)


class VectorStore:
    """
    Facade managing multiple named collections (pdf, notes, textbook).
    This is the object injected into the retriever / MCP tool servers.
    """

    def __init__(self):
        self._indices: dict[str, InMemoryIndex] = {}
        self._lock = asyncio.Lock()

    async def get_or_create_index(self, collection: str) -> InMemoryIndex:
        async with self._lock:
            if collection not in self._indices:
                self._indices[collection] = InMemoryIndex(collection)
                logger.info("Created new collection index: '%s'.", collection)
            return self._indices[collection]

    async def add_documents(self, collection: str, documents: list[Document]) -> None:
        index = await self.get_or_create_index(collection)
        await index.add(documents)

    async def search(
        self, collection: str, query: str, top_k: int = 5
    ) -> list[tuple[Document, float]]:
        try:
            index = await self.get_or_create_index(collection)
            return await index.search(query, top_k=top_k)
        except Exception as exc:
            logger.error("Search failed on collection '%s': %s", collection, exc)
            return []
