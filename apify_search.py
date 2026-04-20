"""
apify_search.py — Real-time web search for market research.
Primary: DuckDuckGo (free, instant, no key needed)
Fallback: Apify Google Search (when DDG fails)

Used by research_market() to give Groq live context when Gemini is rate-limited.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

log = logging.getLogger(__name__)

APIFY_TOKEN = os.getenv("APIFY_TOKEN", "")

# Cache: query -> (results, timestamp)
_search_cache: dict[str, tuple[list[str], float]] = {}
_CACHE_TTL = 300  # 5 minutes


def search_web(query: str, num_results: int = 5) -> list[str]:
    """
    Search the web and return top results as list of "title: snippet" strings.
    Tries DuckDuckGo first (instant), then Apify (slower but reliable).
    """
    cache_key = query.lower().strip()[:120]
    if cache_key in _search_cache:
        results, ts = _search_cache[cache_key]
        if time.time() - ts < _CACHE_TTL:
            return results

    # 1. DuckDuckGo (primary — free, instant, no rate limits per key)
    results = _ddg_search(query, num_results)
    if results:
        _search_cache[cache_key] = (results, time.time())
        return results

    # 2. Apify fallback
    if APIFY_TOKEN:
        results = _apify_search(query, num_results)
        if results:
            _search_cache[cache_key] = (results, time.time())
            return results

    return []


def _ddg_search(query: str, num_results: int) -> list[str]:
    """DuckDuckGo search — free, no key, instant."""
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            hits = list(ddgs.text(query, max_results=num_results, timelimit="m"))  # last month
        results = []
        for h in hits:
            title = h.get("title", "").strip()
            body  = h.get("body", "").strip()[:200]
            if title or body:
                results.append(f"{title}: {body}" if body else title)
        if results:
            log.info(f"[search/ddg] '{query[:50]}' → {len(results)} results")
        return results
    except Exception as e:
        log.debug(f"[search/ddg] failed: {e}")
        return []


def _apify_search(query: str, num_results: int) -> list[str]:
    """Apify Google Search Scraper fallback."""
    try:
        import httpx
        resp = httpx.post(
            "https://api.apify.com/v2/acts/apify~google-search-scraper/run-sync-get-dataset-items",
            params={"token": APIFY_TOKEN, "timeout": 25, "memory": 256},
            json={
                "queries": query,
                "maxPagesPerQuery": 1,
                "resultsPerPage": num_results,
                "languageCode": "en",
                "countryCode": "us",
            },
            timeout=35,
        )
        resp.raise_for_status()
        items = resp.json()
        results = []
        for item in items:
            for r in item.get("organicResults", [])[:num_results]:
                title   = r.get("title", "").strip()
                snippet = r.get("description", "").strip()
                if title or snippet:
                    results.append(f"{title}: {snippet}" if snippet else title)
        if results:
            log.info(f"[search/apify] '{query[:50]}' → {len(results)} results")
        return results
    except Exception as e:
        log.debug(f"[search/apify] failed: {e}")
        return []


def search_market(question: str, yes_price: float) -> list[str]:
    """
    Build a good search query from a market question and return live results.
    """
    q = question.strip().rstrip("?")

    # Remove common market boilerplate
    for suffix in [" on April 20", " on April 21", " on April 22",
                   " on 2026-04-20", " on 2026-04-21", " by April",
                   " ET?", " ET", " 2026", " 8AM", " 12PM", " 4PM"]:
        q = q.replace(suffix, "").strip()

    # For "Will X win?" → "X match result 2026"
    if q.lower().startswith("will ") and " win" in q.lower():
        q = q[5:]  # remove "will "

    # Add context year if not present
    if "2026" not in q:
        q += " 2026"

    return search_web(q, num_results=5)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Kevin Warsh Fed nomination 2026"
    print(f"Searching: {query}")
    results = search_web(query)
    for i, r in enumerate(results, 1):
        print(f"  {i}. {r[:150]}")
