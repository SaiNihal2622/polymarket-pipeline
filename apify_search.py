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


def search_mimo_web(query: str, num_results: int = 5) -> list[str]:
    """
    Use MiMo's tool-calling flow for web search.
    1. Send query to MiMo with web_search tool
    2. Execute actual search via DuckDuckGo
    3. Feed results back to MiMo for synthesis
    4. Return synthesized search results
    """
    import config as _cfg
    if not getattr(_cfg, "MIMO_API_KEY", ""):
        return []

    try:
        import httpx
        import json as _json

        base_url = (getattr(_cfg, "MIMO_BASE_URL", "") or "https://api.xiaomimimo.com/v1").rstrip("/")
        headers = {
            "Authorization": f"Bearer {_cfg.MIMO_API_KEY}",
            "Content-Type": "application/json",
        }

        # Define web_search tool for MiMo's tool-calling
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the web for real-time information, news, prices, and current events",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "The search query"}
                        },
                        "required": ["query"]
                    }
                }
            }
        ]

        # Turn 1: Ask MiMo to search
        resp1 = httpx.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json={
                "model": getattr(_cfg, "MIMO_MODEL", "mimo-v2.5-pro") or "mimo-v2.5-pro",
                "messages": [{"role": "user", "content": f"Search the web for: {query}"}],
                "tools": tools,
                "tool_choice": "auto",
                "max_tokens": 300,
            },
            timeout=15,
        )

        if resp1.status_code != 200:
            return []

        data1 = resp1.json()
        msg1 = data1.get("choices", [{}])[0].get("message", {})
        tool_calls = msg1.get("tool_calls")

        if not tool_calls:
            # MiMo didn't call the tool, fall back to DuckDuckGo directly
            return _ddg_search(query, num_results)

        # Turn 2: Execute actual search via DuckDuckGo
        search_query = _json.loads(tool_calls[0]["function"]["arguments"]).get("query", query)
        raw_results = _ddg_search(search_query, num_results)

        if not raw_results:
            return []

        # Turn 3: Feed results back to MiMo for synthesis
        search_context = "\n".join([f"- {r}" for r in raw_results])
        messages = [
            {"role": "user", "content": f"Search the web for: {query}"},
            msg1,
            {
                "role": "tool",
                "tool_call_id": tool_calls[0]["id"],
                "content": search_context,
            }
        ]

        resp2 = httpx.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json={
                "model": getattr(_cfg, "MIMO_MODEL", "mimo-v2.5-pro") or "mimo-v2.5-pro",
                "messages": messages,
                "max_tokens": 500,
            },
            timeout=15,
        )

        if resp2.status_code == 200:
            synthesized = resp2.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            if synthesized:
                log.info(f"[search/mimo-web] '{query[:40]}...' → synthesized {len(synthesized)} chars")
                return [f"MiMo Web Search: {synthesized[:500]}"]

        # Fall back to raw results if synthesis fails
        return raw_results

    except Exception as e:
        log.debug(f"[search/mimo-web] failed: {e}")
        return []


def search_web(query: str, num_results: int = 5) -> list[str]:
    """
    Search the web and return top results as list of "title: snippet" strings.
    Provider priority: MiMo Web Search > DuckDuckGo > Apify > Gemini Grounding
    """
    cache_key = query.lower().strip()[:120]
    if cache_key in _search_cache:
        results, ts = _search_cache[cache_key]
        if time.time() - ts < _CACHE_TTL:
            return results

    # 1. MiMo Web Search (AI-powered synthesis with tool-calling)
    results = search_mimo_web(query, num_results)
    if results:
        _search_cache[cache_key] = (results, time.time())
        return results

    # 2. DuckDuckGo (free, instant, no rate limits per key)
    results = _ddg_search(query, num_results)
    if results:
        _search_cache[cache_key] = (results, time.time())
        return results

    # 3. Apify fallback
    if APIFY_TOKEN:
        results = _apify_search(query, num_results)
        if results:
            _search_cache[cache_key] = (results, time.time())
            return results

    # 4. Gemini grounding fallback (when all else fails)
    results = _gemini_grounding_search(query)
    if results:
        _search_cache[cache_key] = (results, time.time())
        return results

    return []


def _ddg_search(query: str, num_results: int) -> list[str]:
    """DuckDuckGo search — free, no key, instant."""
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        # Use simple text search without strict time limits to ensure results
        with DDGS() as ddgs:
            hits = list(ddgs.text(query, max_results=num_results))
        results = []
        for h in hits:
            title = h.get("title", "").strip()
            body  = h.get("body", "").strip()[:200]
            if title or body:
                results.append(f"{title}: {body}" if body else title)
        if results:
            log.info(f"[search/ddg] '{query[:40]}...' → {len(results)} results")
        return results
    except Exception as e:
        log.debug(f"[search/ddg] failed: {e}")
        return []


def _apify_search(query: str, num_results: int) -> list[str]:
    """Apify Google Search Scraper fallback."""
    if not APIFY_TOKEN:
        return []
    try:
        import httpx
        # Using run-sync-get-dataset-items for speed
        resp = httpx.post(
            "https://api.apify.com/v2/acts/apify~google-search-scraper/run-sync-get-dataset-items",
            params={"token": APIFY_TOKEN, "timeout": 20, "memory": 256},
            json={
                "queries": query,
                "maxPagesPerQuery": 1,
                "resultsPerPage": num_results,
                "mobileResults": False,
                "languageCode": "en",
            },
            timeout=30,
        )
        
        if resp.status_code == 402:
            log.warning(f"[search/apify] 402 Payment Required (Account has balance but actor may be restricted). Falling back.")
            return []
            
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
            log.info(f"[search/apify] '{query[:40]}...' → {len(results)} results")
        return results
    except Exception as e:
        log.debug(f"[search/apify] failed: {e}")
        return []


def _gemini_grounding_search(query: str) -> list[str]:
    """
    Use Gemini's built-in Google Search grounding as a last-resort search.
    Returns search results as list of strings when DDG and Apify both fail.
    """
    try:
        from google import genai
        from google.genai import types as _gtypes
        import config as _cfg

        client = genai.Client(api_key=_cfg.GEMINI_API_KEY)
        prompt = (
            f"Search the web for: {query}\n\n"
            f"Return the top 5 most relevant and recent results. "
            f"For each result, provide: title and a 1-2 sentence summary.\n"
            f"Format: one result per line as 'Title: Summary'"
        )
        gen_config = {
            "temperature": 0.1,
            "max_output_tokens": 500,
            "tools": [_gtypes.Tool(google_search=_gtypes.GoogleSearch())],
        }
        response = client.models.generate_content(
            model=_cfg.GEMINI_MODEL,
            contents=prompt,
            config=gen_config,
        )
        text = response.text.strip()
        # Parse lines into results
        results = []
        for line in text.split("\n"):
            line = line.strip().lstrip("0123456789.-*) ")
            if ":" in line and len(line) > 20:
                results.append(line[:300])
        if results:
            log.info(f"[search/gemini-grounding] '{query[:40]}...' → {len(results)} results")
        return results[:5]
    except Exception as e:
        log.debug(f"[search/gemini-grounding] failed: {e}")
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
