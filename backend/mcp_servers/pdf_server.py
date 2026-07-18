"""
mcp/pdf_server.py

MCP server exposing a single tool: `search_pdfs`.
Retrieves relevant chunks from uploaded PDF documents (including
textbook PDFs) that have been previously ingested into the
"pdf" and "textbook" vector store collections.

Run standalone for local testing:
    python mcp/pdf_server.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Allow running this file directly AND as a subprocess from any cwd.
_THIS_DIR = str(Path(__file__).resolve().parent)
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from mcp.server.fastmcp import FastMCP  # Anthropic MCP Python SDK

from retriever import RAGRetriever
from vector_store import VectorStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp.pdf_server")

# Shared store for this server process. In production this would be
# backed by a persistent vector DB rather than an in-memory instance.
_vector_store = VectorStore()
_retriever = RAGRetriever(_vector_store)

mcp = FastMCP("pdf-retrieval-server")


@mcp.tool()
async def search_pdfs(query: str, top_k: int = 5) -> dict:
    """
    Search uploaded PDF documents and textbook PDFs for content
    relevant to `query`.

    Args:
        query: The user's research question or search phrase.
        top_k: Maximum number of chunks to return per collection.

    Returns:
        dict with keys:
            - results: list of {text, source, collection, score}
            - error: present only if retrieval failed
    """
    logger.info("search_pdfs called | query=%r top_k=%d", query, top_k)
    try:
        chunks = await _retriever.retrieve_from_many(
            collections=["pdf", "textbook"], query=query, top_k=top_k
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
        # Never let the tool crash the MCP server; report the error instead.
        logger.error("search_pdfs failed: %s", exc, exc_info=True)
        return {"results": [], "error": str(exc)}


if __name__ == "__main__":
    # Runs the server over stdio for MCP client connections.
    mcp.run(transport="stdio")
