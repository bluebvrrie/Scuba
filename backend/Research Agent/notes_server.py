"""
mcp/notes_server.py

MCP server exposing a single tool: `search_notes`.
Retrieves relevant chunks from the user's uploaded personal notes
(the "notes" vector store collection).

Run standalone for local testing:
    python mcp/notes_server.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from mcp.server.fastmcp import FastMCP

from retriever import RAGRetriever
from vector_store import VectorStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp.notes_server")

_vector_store = VectorStore()
_retriever = RAGRetriever(_vector_store)

mcp = FastMCP("notes-retrieval-server")


@mcp.tool()
async def search_notes(query: str, top_k: int = 5) -> dict:
    """
    Search the user's uploaded notes for content relevant to `query`.

    Args:
        query: The user's research question or search phrase.
        top_k: Maximum number of chunks to return.

    Returns:
        dict with keys:
            - results: list of {text, source, collection, score}
            - error: present only if retrieval failed
    """
    logger.info("search_notes called | query=%r top_k=%d", query, top_k)
    try:
        chunks = await _retriever.retrieve_from_collection(
            collection="notes", query=query, top_k=top_k
        )
        return {
            "results": [
                {
                    "text": c.text,
                    "source": c.source,
                    "collection": c.collection,
                    "score": c.score,
                }
                for c in chunks
            ]
        }
    except Exception as exc:
        logger.error("search_notes failed: %s", exc, exc_info=True)
        return {"results": [], "error": str(exc)}


if __name__ == "__main__":
    mcp.run(transport="stdio")
