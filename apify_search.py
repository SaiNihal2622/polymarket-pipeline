"""
apify_search.py — Real-time web search via Apify Google Search Scraper.
Replaces Gemini search grounding when Gemini is rate-limited (429).

Usage:
    from apify_search import search_web
    results = search_web("Crystal Palace vs West Ham 2026 preview")
    # returns list of "title: snippet" strings
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

import httpx

log = logging.getLogger(__name__)

APIFY_TOKEN = os.getenv("APIFY_TOKEN", "APIFY_PLACEHOLDER")

# Cache: query -> (results, timestamp)
_search_cache: dict[str, tuple[list[str], float]] = {}
_CACHE_TTL = 300  # 5 minutes

# Rate limiting
_last_call = 0.0
_MIN_INTERVAL = 2.0  # 2s between calls


def search_web(query: str, num_results: int = 5) -> list[str]:
    """
    Search Google via Apify and return top results as list of strings.
    Each string: "Title: snippet"
    Returns empty list on failure.
    """
    global _last_call

    # Cache hit
    cache_key = query.lower().strip()[:100]
    if cache_key in _search_cache:
        results, ts = _search_cache[cache_key]
        if time.time() - ts < _CACHE_TTL:
            return results

    # Rate limit
    elapsed = time.time() - _last_call
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)

    try:
        _last_call = time.time()
        resp = httpx.post(
            "https://api.apify.com/v2/acts/apify~google-search-scraper/run-sync-get-dataset-items",
            params={"token": APIFY_TOKEN, "timeout": 25, "memory": 256},
            json={
                "queries": query,
                "maxPagesPerQuery": 1,
                "resultsPerPage": num_results,
                "languageCode": "en",
                "countryCode": "us",
                "mobileResults": False,
            },
            timeout=35,
        )
        resp.raise_for_status()
        items = resp.json()

        results = []
        for item in items:
            for r in item.get("organicResults", [])[:num_results]:
                title = r.get("title", "").strip()
                snippet = r.get("description", "").strip()
                if title or snippet:
                    results.append(f"{title}: {snippet}" if snippet else title)

        log.info(f"[apify] '{query[:50]}' → {len(results)} results")
        _search_cache[cache_key] = (results, time.time())
        return results

    except Exception as e:
        log.warning(f"[apify] Search failed for '{query[:40]}': {e}")
        return []


def search_market(question: str, yes_price: float) -> list[str]:
    """
    Build a good search query from a market question and return results.
    Automatically strips prediction market boilerplate.
    """
    # Clean up the question for search
    q = question.strip()
    # Remove common market suffixes
    for suffix in [" on April", " on May", " on 2026", " by April", " by May",
                   " on 2026-04", " ET?", " ET", "?"]:
        if q.endswith(suffix):
            q = q[:-len(suffix)].strip()

    # For "Will X win?" → search "X match result"
    if q.lower().startswith("will ") and " win" in q.lower():
        q = q[5:]  # remove "will "

    # Add "2026" if not present
    if "2026" not in q and "2025" not in q:
        q = q + " 2026"

    return search_web(q, num_results=5)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Crystal Palace vs West Ham 2026"
    results = search_web(query)
    print(f"\nQuery: {query}")
    print(f"Results ({len(results)}):")
    for i, r in enumerate(results, 1):
        print(f"  {i}. {r[:120]}")
