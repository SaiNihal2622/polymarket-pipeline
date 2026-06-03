#!/usr/bin/env python3
"""Check markets via Polymarket CLOB API and Gamma with different approaches."""
import httpx
import json
import ssl

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"

# First, let's get the full trade data from Railway to see what identifiers we have
print("Fetching trades from Railway...")
r = httpx.get("https://industrious-blessing-production-b110.up.railway.app/api/trades", timeout=15, verify=False)
data = r.json()
trades = data.get("trades", [])

# Find the resolved ones
resolved = [t for t in trades if t.get("result") != "pending"]
print(f"\nResolved trades: {len(resolved)}")
for t in resolved:
    print(f"\n  Trade #{t['id']}: {t['market_question']}")
    print(f"  result={t['result']} | market_outcome={t['market_outcome']}")
    print(f"  market_slug={t.get('market_slug','')}")
    # Check if there's a condition_id or token_id stored
    print(f"  All keys: {list(t.keys())}")

# Now try to search Polymarket for Houston Dash and Team Falcons
print("\n\n=== Searching Polymarket ===")
search_terms = ["Houston Dash", "Team Falcons DreamLeague", "Falcons DreamLeague"]
for term in search_terms:
    print(f"\nSearching for: {term}")
    # Try Gamma search with different params
    for params in [
        {"_q": term, "limit": 5},
        {"_q": term, "limit": 5, "active": "false"},
        {"tag": term, "limit": 5},
    ]:
        try:
            r = httpx.get(f"{GAMMA_API}/markets", params=params, timeout=15, verify=False)
            if r.status_code == 200:
                data = r.json()
                items = data if isinstance(data, list) else data.get("data", [])
                for m in items[:2]:
                    print(f"  [{params}]: {m.get('question','')[:80]} | resolved={m.get('resolved')} | closed={m.get('closed')}")
        except Exception as e:
            print(f"  Error: {e}")

# Also try the events API
print("\n\n=== Trying events API ===")
for term in ["Houston Dash", "DreamLeague"]:
    try:
        r = httpx.get(f"{GAMMA_API}/events", params={"_q": term, "limit": 5, "closed": "true"}, timeout=15, verify=False)
        if r.status_code == 200:
            data = r.json()
            items = data if isinstance(data, list) else data.get("data", [])
            for e in items[:3]:
                print(f"  Event: {e.get('title','')[:80]} | markets: {len(e.get('markets', []))}")
                for m in e.get("markets", [])[:3]:
                    print(f"    Market: {m.get('question','')[:60]} | resolved={m.get('resolved')} | outcome={m.get('resolvedOutcome')}")
    except Exception as ex:
        print(f"  Error: {ex}")