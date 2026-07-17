"""
mcp/search_server.py

MCP server exposing a single tool: `search_web`.
Searches trusted online educational resources only — results are
filtered against an allowlist of reputable domains before being
returned, so the agent never cites unvetted sources.

Requires a search API key set as the SEARCH_API_KEY environment
variable (e.g. Bing Web Search, SerpAPI, Brave Search). Swap
`_call_search_api` for whichever provider you use in production.

Run standalone for local testing:
    python mcp/search_server.py
"""

from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

import httpx
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp.search_server")

mcp = FastMCP("web-search-server")

# Allowlist of trusted educational / reference domains.
# Extend as needed for the specific curriculum being supported.
TRUSTED_DOMAINS: set[str] = {
    "khanacademy.org",
    "coursera.org",
    "edx.org",
    "mit.edu",
    "stanford.edu",
    "ocw.mit.edu",
    "wikipedia.org",
    "britannica.com",
    "nist.gov",
    "ieee.org",
    "acm.org",
    "arxiv.org",
    "nature.com",
    "sciencedirect.com",
    "khanacademy.org",
    "openstax.org",
}

SEARCH_API_URL = "https://api.bing.microsoft.com/v7.0/search"
SEARCH_API_KEY = os.environ.get("SEARCH_API_KEY", "")
REQUEST_TIMEOUT_SECONDS = 10.0


def _is_trusted(url: str) -> bool:
    """Return True if the URL's registrable domain is in TRUSTED_DOMAINS."""
    try:
        netloc = urlparse(url).netloc.lower()
        return any(netloc == d or netloc.endswith(f".{d}") for d in TRUSTED_DOMAINS)
    except Exception:
        return False


async def _call_search_api(query: str, count: int) -> list[dict]:
    """
    Call the underlying search API and return raw results as
    [{"title": ..., "url": ..., "snippet": ...}, ...].
    Isolated so the provider can be swapped without touching tool logic.
    """
    if not SEARCH_API_KEY:
        logger.warning("SEARCH_API_KEY not set; web search will return no results.")
        return []

    headers = {"Ocp-Apim-Subscription-Key": SEARCH_API_KEY}
    params = {"q": query, "count": count}

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        response = await client.get(SEARCH_API_URL, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()

    web_pages = data.get("webPages", {}).get("value", [])
    return [
        {
            "title": item.get("name", ""),
            "url": item.get("url", ""),
            "snippet": item.get("snippet", ""),
        }
        for item in web_pages
    ]


@mcp.tool()
async def search_web(query: str, top_k: int = 5) -> dict:
    """
    Search trusted online educational resources for content relevant
    to `query`. Non-trusted domains are filtered out before results
    are returned.

    Args:
        query: The user's research question or search phrase.
        top_k: Maximum number of trusted results to return.

    Returns:
        dict with keys:
            - results: list of {text, source, collection, score}
            - error: present only if the search call failed
    """
    logger.info("search_web called | query=%r top_k=%d", query, top_k)
    try:
        # Over-fetch slightly since some results will be filtered out.
        raw_results = await _call_search_api(query, count=max(top_k * 3, 10))

        trusted = [r for r in raw_results if _is_trusted(r["url"])][:top_k]
        logger.info(
            "search_web: %d raw result(s), %d trusted result(s).",
            len(raw_results), len(trusted),
        )

        return {
            "results": [
                {
                    "text": r["snippet"],
                    "source": r["url"],
                    "collection": "web",
                    # Search engines don't provide a similarity score; use a
                    "score": None,
                }
                for r in trusted
            ]
        }
    except httpx.HTTPStatusError as exc:
        logger.error("search_web HTTP error: %s", exc)
        return {"results": [], "error": f"HTTP error: {exc}"}
    except Exception as exc:
        logger.error("search_web failed: %s", exc, exc_info=True)
        return {"results": [], "error": str(exc)}


if __name__ == "__main__":
    mcp.run(transport="stdio")
