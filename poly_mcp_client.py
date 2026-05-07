"""
Polymarket MCP Client - Direct Python integration with polymarket-mcp-server tools.

Instead of running the MCP server as a subprocess, this module imports and calls
the MCP server's internal functions directly for maximum performance.

Used by:
  - resolver.py: Market resolution via Gamma API
  - scanner.py: Market discovery (trending, closing soon, search)
  - scorer.py: Market analysis (orderbook, holders, price history)
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("poly_mcp")

# ── Gamma API (same as MCP server uses) ──────────────────────────────
GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"
DATA_API = "https://data-api.polymarket.com"


# ── Market Discovery (from MCP server's market_discovery.py) ─────────

async def search_markets(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Search markets by text query via Gamma API."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{GAMMA_API}/markets", params={
                "closed": "false",
                "limit": limit,
                "active": "true",
            })
            if resp.status_code != 200:
                return []
            markets = resp.json()
            # Text filter
            q = query.lower()
            return [m for m in markets if q in (m.get("question", "") + m.get("description", "")).lower()][:limit]
    except Exception as e:
        logger.warning(f"[mcp] search_markets error: {e}")
        return []


async def get_trending_markets(limit: int = 20) -> List[Dict[str, Any]]:
    """Get trending markets sorted by volume."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{GAMMA_API}/markets", params={
                "closed": "false",
                "limit": limit,
                "active": "true",
                "order": "volume24hr",
                "ascending": "false",
            })
            if resp.status_code != 200:
                return []
            return resp.json()
    except Exception as e:
        logger.warning(f"[mcp] get_trending error: {e}")
        return []


async def get_closing_soon_markets(hours: int = 48, limit: int = 20) -> List[Dict[str, Any]]:
    """Get markets closing within N hours."""
    try:
        from datetime import datetime, timedelta, timezone
        end_before = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{GAMMA_API}/markets", params={
                "closed": "false",
                "limit": limit,
                "active": "true",
                "end_date_min": datetime.now(timezone.utc).isoformat(),
                "end_date_max": end_before,
            })
            if resp.status_code != 200:
                return []
            return resp.json()
    except Exception as e:
        logger.warning(f"[mcp] get_closing_soon error: {e}")
        return []


# ── Market Analysis (from MCP server's market_analysis.py) ───────────

async def get_market_details(market_id: str) -> Optional[Dict[str, Any]]:
    """Get full market details from Gamma API."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{GAMMA_API}/markets/{market_id}")
            if resp.status_code == 200:
                return resp.json()
            # Try by slug
            resp2 = await client.get(f"{GAMMA_API}/markets", params={"slug": market_id})
            if resp2.status_code == 200:
                data = resp2.json()
                if data:
                    return data[0]
            return None
    except Exception as e:
        logger.warning(f"[mcp] get_market_details error: {e}")
        return None


async def get_market_by_slug(slug: str) -> Optional[Dict[str, Any]]:
    """Get market by slug from Gamma API."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{GAMMA_API}/markets", params={"slug": slug})
            if resp.status_code == 200:
                data = resp.json()
                return data[0] if data else None
            return None
    except Exception as e:
        logger.warning(f"[mcp] get_market_by_slug error: {e}")
        return None


async def get_orderbook(token_id: str) -> Optional[Dict[str, Any]]:
    """Get orderbook from CLOB API."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{CLOB_API}/book", params={"token_id": token_id})
            if resp.status_code == 200:
                return resp.json()
            return None
    except Exception as e:
        logger.warning(f"[mcp] get_orderbook error: {e}")
        return None


async def get_current_price(token_id: str) -> Optional[Dict[str, float]]:
    """Get current bid/ask/mid price from CLOB API."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{CLOB_API}/price", params={
                "token_id": token_id,
                "side": "buy"
            })
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "price": float(data.get("price", 0)),
                    "side": data.get("side", "buy"),
                }
            return None
    except Exception as e:
        logger.warning(f"[mcp] get_current_price error: {e}")
        return None


async def get_market_holders(token_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Get top holders for a market token."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{DATA_API}/holders", params={
                "tokenId": token_id,
                "limit": limit,
            })
            if resp.status_code == 200:
                return resp.json()
            return []
    except Exception as e:
        logger.warning(f"[mcp] get_market_holders error: {e}")
        return []


async def get_price_history(token_id: str, fidelity: int = 60) -> List[Dict[str, Any]]:
    """Get price history from CLOB API."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{CLOB_API}/prices-history", params={
                "market": token_id,
                "interval": "max",
                "fidelity": fidelity,
            })
            if resp.status_code == 200:
                return resp.json().get("history", [])
            return []
    except Exception as e:
        logger.warning(f"[mcp] get_price_history error: {e}")
        return []


# ── Resolution helpers (for resolver.py) ─────────────────────────────

async def check_market_resolution(market_id: str) -> Optional[Dict[str, Any]]:
    """
    Check if a market has resolved via Gamma API.
    Returns resolution info or None if not resolved.
    """
    try:
        details = await get_market_details(market_id)
        if not details:
            return None

        # Check if resolved
        resolved = details.get("resolved", False)
        if not resolved:
            # Also check by resolutionSource or endDate
            end_date = details.get("endDate", "")
            if end_date:
                from datetime import datetime, timezone
                try:
                    end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                    if end > datetime.now(timezone.utc):
                        return None  # Not yet ended
                except:
                    pass

        if not resolved:
            return None

        # Extract resolution outcome
        outcomes = details.get("outcomes", [])
        outcome_prices = details.get("outcomePrices", "")

        if isinstance(outcome_prices, str):
            import json
            try:
                outcome_prices = json.loads(outcome_prices)
            except:
                outcome_prices = []

        # Determine winner
        if outcome_prices and len(outcome_prices) >= 2:
            p0 = float(outcome_prices[0]) if outcome_prices[0] else 0
            p1 = float(outcome_prices[1]) if outcome_prices[1] else 0
            if p0 > 0.9:
                return {"outcome": "Yes", "price": p0, "market": details}
            elif p1 > 0.9:
                return {"outcome": "No", "price": p1, "market": details}

        # Check resolutionData
        resolution_data = details.get("resolutionData", {})
        if resolution_data:
            return {"outcome": str(resolution_data), "market": details}

        return None
    except Exception as e:
        logger.warning(f"[mcp] check_resolution error: {e}")
        return None


# ── Sync wrappers ────────────────────────────────────────────────────

def _run_async(coro):
    """Run an async function from sync code."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're inside an async context, use nest_asyncio or create new loop
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result(timeout=30)
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def search_markets_sync(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    return _run_async(search_markets(query, limit))


def get_trending_markets_sync(limit: int = 20) -> List[Dict[str, Any]]:
    return _run_async(get_trending_markets(limit))


def get_market_details_sync(market_id: str) -> Optional[Dict[str, Any]]:
    return _run_async(get_market_details(market_id))


def check_resolution_sync(market_id: str) -> Optional[Dict[str, Any]]:
    return _run_async(check_market_resolution(market_id))


def get_orderbook_sync(token_id: str) -> Optional[Dict[str, Any]]:
    return _run_async(get_orderbook(token_id))


def get_price_history_sync(token_id: str) -> List[Dict[str, Any]]:
    return _run_async(get_price_history(token_id))


# ── Quick test ───────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    async def _test():
        print("=== MCP Client Test ===")

        # Trending markets
        trending = await get_trending_markets(5)
        print(f"\nTrending markets: {len(trending)}")
        for m in trending[:3]:
            print(f"  - {m.get('question', 'N/A')[:60]}")

        # Search
        results = await search_markets("Trump", 3)
        print(f"\nTrump search: {len(results)} results")
        for m in results[:2]:
            print(f"  - {m.get('question', 'N/A')[:60]}")

        # Market details
        if trending:
            mid = trending[0].get("id", "")
            details = await get_market_details(mid)
            if details:
                print(f"\nMarket details: {details.get('question', 'N/A')[:60]}")
                print(f"  Resolved: {details.get('resolved')}")
                print(f"  Volume: {details.get('volume', 'N/A')}")

        print("\n=== Test Complete ===")

    asyncio.run(_test())