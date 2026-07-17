"""
research_agent.py

Research Agent for the Multi-Agent AI Learning Assistant.

Responsibilities:
- Accept a user question.
- Fan out to three MCP tool servers (PDF/textbook, notes, trusted web
  search) as independent stdio subprocesses.
- Merge the retrieved chunks into a single context block.
- Compute an overall confidence score.
- Return retrieved_context, source list, and confidence score.

This agent performs RETRIEVAL ONLY — it does not generate explanations,
summaries, or answers. That is left to a downstream synthesis/answer
agent in the wider multi-agent system.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("research_agent")

PROJECT_ROOT = Path(__file__).resolve().parent
MCP_DIR = PROJECT_ROOT / "mcp_servers"

# Default number of chunks requested per tool.
DEFAULT_TOP_K = 5

# Per-tool timeout so one slow/hanging MCP server can't stall the agent.
TOOL_CALL_TIMEOUT_SECONDS = 15.0


@dataclass
class RetrievalResult:
    """Normalized output of a single MCP tool call."""
    tool_name: str
    chunks: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


@dataclass
class ResearchResponse:
    """Final structured response returned by the Research Agent."""
    retrieved_context: str
    sources: list[str]
    confidence_score: float


class ResearchAgent:
    """
    Orchestrates PDF, notes, and trusted-web MCP tool servers to answer
    a research query with retrieved context only (no generation).
    """

    def __init__(self, top_k: int = DEFAULT_TOP_K):
        self.top_k = top_k
        self._exit_stack = AsyncExitStack()
        self._sessions: dict[str, ClientSession] = {}

    async def __aenter__(self) -> "ResearchAgent":
        await self._connect_all_servers()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self._exit_stack.aclose()

    # ------------------------------------------------------------------
    # Server lifecycle
    # ------------------------------------------------------------------

    async def _connect_server(self, name: str, script_path: Path) -> None:
        """Launch an MCP server subprocess and register its session."""
        try:
            server_params = StdioServerParameters(
                command=sys.executable,
                args=[str(script_path)],
            )
            read, write = await self._exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            session = await self._exit_stack.enter_async_context(
                ClientSession(read, write)
            )
            await session.initialize()
            self._sessions[name] = session
            logger.info("Connected to MCP server '%s' (%s).", name, script_path.name)
        except Exception as exc:
            # A single failed server should not prevent the others from
            # working; the agent degrades gracefully instead of crashing.
            logger.error("Failed to connect to MCP server '%s': %s", name, exc)

    async def _connect_all_servers(self) -> None:
        # NOTE: connections are established sequentially (not via
        # asyncio.gather) and all inside __aenter__'s task. All three
        # stdio_client/ClientSession context managers are pushed onto the
        # same AsyncExitStack, and anyio's cancel scopes require that a
        # context manager be entered and exited from the *same* asyncio
        # task. Running the connects concurrently under gather would enter
        # them from separate child tasks while __aexit__ later closes the
        # stack from the parent task, raising
        # "Attempted to exit cancel scope in a different task than it was
        # entered in". Sequential connection keeps everything in one task.
        await self._connect_server("pdf", MCP_DIR / "pdf_server.py")
        await self._connect_server("notes", MCP_DIR / "notes_server.py")
        await self._connect_server("web", MCP_DIR / "search_server.py")
        # NOTE: this local package directory is named `mcp_servers/` rather
        # than `mcp/` deliberately — naming it `mcp` would shadow the
        # installed `mcp` SDK package (the one providing ClientSession,
        # FastMCP, etc.) since the project root sits on sys.path.
        if not self._sessions:
            logger.warning("No MCP servers connected; retrieval will return nothing.")

    # ------------------------------------------------------------------
    # Tool invocation
    # ------------------------------------------------------------------

    async def _call_tool(
        self, server_name: str, tool_name: str, query: str
    ) -> RetrievalResult:
        """Call a single MCP tool with a timeout and structured error handling."""
        session = self._sessions.get(server_name)
        if session is None:
            return RetrievalResult(
                tool_name=tool_name,
                error=f"'{server_name}' server is not connected.",
            )

        try:
            result = await asyncio.wait_for(
                session.call_tool(
                    tool_name, arguments={"query": query, "top_k": self.top_k}
                ),
                timeout=TOOL_CALL_TIMEOUT_SECONDS,
            )
            payload = _extract_tool_payload(result)
            if "error" in payload and payload["error"]:
                logger.warning("Tool '%s' returned an error: %s", tool_name, payload["error"])
                return RetrievalResult(tool_name=tool_name, error=payload["error"])

            chunks = payload.get("results", [])
            logger.info("Tool '%s' returned %d chunk(s).", tool_name, len(chunks))
            return RetrievalResult(tool_name=tool_name, chunks=chunks)

        except asyncio.TimeoutError:
            logger.error("Tool '%s' timed out after %.1fs.", tool_name, TOOL_CALL_TIMEOUT_SECONDS)
            return RetrievalResult(tool_name=tool_name, error="timeout")
        except Exception as exc:
            logger.error("Tool '%s' raised an exception: %s", tool_name, exc, exc_info=True)
            return RetrievalResult(tool_name=tool_name, error=str(exc))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def answer_question(self, question: str) -> ResearchResponse:
        """
        Run PDF, notes, and web retrieval concurrently for `question`,
        merge results, and return structured retrieval output.
        """
        if not question or not question.strip():
            logger.warning("Empty question received; returning empty response.")
            return ResearchResponse(retrieved_context="", sources=[], confidence_score=0.0)

        logger.info("Answering question: %r", question)

        results = await asyncio.gather(
            self._call_tool("pdf", "search_pdfs", question),
            self._call_tool("notes", "search_notes", question),
            self._call_tool("web", "search_web", question),
        )

        all_chunks: list[dict[str, Any]] = []
        for r in results:
            if r.error:
                logger.info("Skipping '%s' due to error: %s", r.tool_name, r.error)
                continue
            all_chunks.extend(r.chunks)

        # Rank by score where available; web results (score=None) are kept
        # but sorted after scored PDF/notes chunks.
        all_chunks.sort(key=lambda c: (c.get("score") is not None, c.get("score") or 0), reverse=True)

        context = _build_context_block(all_chunks)
        sources = _dedupe_sources(all_chunks)
        confidence = _compute_overall_confidence(all_chunks)

        return ResearchResponse(
            retrieved_context=context,
            sources=sources,
            confidence_score=confidence,
        )


# ----------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------

def _extract_tool_payload(call_tool_result: Any) -> dict[str, Any]:
    """
    MCP tool results arrive as a list of content blocks. This extracts
    the structured dict payload our tools return (they return dicts,
    which FastMCP serializes as a single JSON text content block).
    """
    import json

    try:
        content = call_tool_result.content
        if not content:
            return {"results": []}
        first_block = content[0]
        text = getattr(first_block, "text", None)
        if text is None:
            return {"results": []}
        return json.loads(text)
    except Exception as exc:
        logger.error("Failed to parse tool payload: %s", exc)
        return {"results": [], "error": "malformed tool response"}


def _build_context_block(chunks: list[dict[str, Any]]) -> str:
    """Concatenate retrieved chunks into a single labeled context string."""
    if not chunks:
        return ""

    lines = []
    for chunk in chunks:
        source = chunk.get("source", "unknown")
        text = chunk.get("text", "").strip()
        if text:
            lines.append(f"[Source: {source}]\n{text}")
    return "\n\n".join(lines)


def _dedupe_sources(chunks: list[dict[str, Any]]) -> list[str]:
    """Return a de-duplicated, order-preserving list of sources."""
    seen: set[str] = set()
    ordered: list[str] = []
    for chunk in chunks:
        source = chunk.get("source")
        if source and source not in seen:
            seen.add(source)
            ordered.append(source)
    return ordered


def _compute_overall_confidence(chunks: list[dict[str, Any]]) -> float:
    """
    Combine per-collection retrieval into one confidence score.
    Scored (PDF/notes) chunks drive the score; unscored web results
    provide a smaller flat contribution capped so search noise can't
    inflate confidence.
    """
    scored = [c["score"] for c in chunks if isinstance(c.get("score"), (int, float))]
    web_hits = sum(1 for c in chunks if c.get("collection") == "web")

    if not scored and web_hits == 0:
        return 0.0

    base = 0.0
    if scored:
        top = sorted(scored, reverse=True)[:3]
        base = sum(top) / len(top)

    web_bonus = min(web_hits * 0.03, 0.1)  # small, capped contribution
    return round(min(base + web_bonus, 1.0), 4)


# ----------------------------------------------------------------------
# Example entry point
# ----------------------------------------------------------------------

async def main() -> None:
    """
    Example usage. In the wider multi-agent system this class would be
    instantiated and called by an orchestrator/router agent instead.
    """
    question = "Explain the Barkhausen criterion for oscillators."
    async with ResearchAgent(top_k=5) as agent:
        response = await agent.answer_question(question)
        logger.info("retrieved_context: %s", response.retrieved_context[:500])
        logger.info("sources: %s", response.sources)
        logger.info("confidence_score: %s", response.confidence_score)


if __name__ == "__main__":
    asyncio.run(main())
