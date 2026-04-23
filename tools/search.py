"""
Web search tool — wraps the Tavily Search API.
Returns a ranked list of results with title, URL, snippet, and relevance score.
"""

import logging

import httpx

from config import TAVILY_API_KEY

logger = logging.getLogger(__name__)

TAVILY_SEARCH_URL = "https://api.tavily.com/search"


def search_web(query: str, max_results: int = 5) -> dict:
    """Call the Tavily Search API and return a clean list of results."""
    if not TAVILY_API_KEY:
        return {"error": "Tavily API key not configured. Set TAVILY_API_KEY in .env."}

    if not query or not query.strip():
        return {"error": "'query' must be a non-empty string."}

    max_results = max(1, min(max_results, 10))  # clamp to Tavily's sensible range

    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query.strip(),
        "max_results": max_results,
    }

    try:
        response = httpx.post(TAVILY_SEARCH_URL, json=payload, timeout=15)
    except httpx.RequestError as e:
        return {"error": f"Network error while calling Tavily: {e}"}

    if response.status_code == 401:
        return {"error": "Invalid Tavily API key."}
    if response.status_code == 429:
        return {"error": "Tavily rate limit exceeded. Try again shortly."}
    if response.status_code != 200:
        return {"error": f"Tavily API error (status {response.status_code}): {response.text}"}

    data = response.json()
    raw_results = data.get("results") or []

    if not raw_results:
        return {"query": query, "results": [], "message": "No results found."}

    results = [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "content": r.get("content", ""),
            "score": r.get("score"),
        }
        for r in raw_results
    ]

    return {"query": query, "results": results, "count": len(results)}


SEARCH_TOOL_SCHEMA = {
    "name": "search_web",
    "description": (
        "Search the web for up-to-date information using the Tavily search engine. "
        "Use this whenever the user asks about current events, recent news, facts you may not know, "
        "or anything that benefits from a live web search. "
        "Returns a ranked list of results with titles, URLs, and text snippets."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query to look up on the web.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return (1–10). Defaults to 5.",
            },
        },
        "required": ["query"],
    },
}
