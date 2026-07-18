"""
retriever.py

RAG retrieval layer sitting on top of vector_store.VectorStore.
Responsible for:
- Querying the pdf / notes / textbook collections concurrently.
- Normalizing results into a common schema.
- Computing a per-source and an overall confidence score.

This module does NOT talk to MCP directly — the MCP tool servers
(mcp/pdf_server.py, mcp/notes_server.py) import and call into this
module (or an equivalent VectorStore instance) so the retrieval logic
is reusable and independently testable.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from mcp_servers.vector_store import Document, VectorStore

logger = logging.getLogger("retriever")

# Minimum cosine similarity below which a result is discarded as noise.
SIMILARITY_FLOOR = 0.15


@dataclass
class RetrievedChunk:
    """Normalized retrieval result returned to callers / MCP tools."""
    text: str
    source: str
    collection: str
    score: float


class RAGRetriever:
    """Thin orchestration layer over one shared VectorStore instance."""

    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store

    async def retrieve_from_collection(
        self, collection: str, query: str, top_k: int = 5
    ) -> list[RetrievedChunk]:
        """Retrieve top_k chunks from a single named collection."""
        try:
            results = await self.vector_store.search(collection, query, top_k=top_k)
        except Exception as exc:
            logger.error("Retrieval error on '%s': %s", collection, exc)
            return []

        chunks = [
            RetrievedChunk(
                text=doc.text,
                source=doc.source,
                collection=collection,
                score=score,
            )
            for doc, score in results
            if score >= SIMILARITY_FLOOR
        ]
        logger.info(
            "Retrieved %d/%d usable chunk(s) from '%s' for query.",
            len(chunks), len(results), collection,
        )
        return chunks

    async def retrieve_from_many(
        self, collections: list[str], query: str, top_k: int = 5
    ) -> list[RetrievedChunk]:
        """Query multiple collections concurrently and merge results."""
        tasks = [
            self.retrieve_from_collection(name, query, top_k=top_k)
            for name in collections
        ]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        merged: list[RetrievedChunk] = []
        for chunk_list in results:
            merged.extend(chunk_list)
        merged.sort(key=lambda c: c.score, reverse=True)
        return merged

    async def index_documents(self, collection: str, documents: list[Document]) -> None:
        """Utility for ingesting new PDFs / notes / textbook chunks."""
        await self.vector_store.add_documents(collection, documents)


def compute_confidence(chunks: list[RetrievedChunk]) -> float:
    """
    Derive a single 0-1 confidence score for a set of retrieved chunks.

    Heuristic: average of the top 3 similarity scores, scaled down if
    very few chunks were retrieved (sparse evidence lowers confidence).
    """
    if not chunks:
        return 0.0

    top_scores = sorted((c.score for c in chunks), reverse=True)[:3]
    avg_top = sum(top_scores) / len(top_scores)

    coverage_penalty = min(len(chunks) / 3, 1.0)  # fewer than 3 chunks -> penalty
    confidence = avg_top * coverage_penalty
    return round(max(0.0, min(confidence, 1.0)), 4)
