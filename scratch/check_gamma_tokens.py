#!/usr/bin/env python3
"""Check what Gamma API returns for token IDs."""
import httpx, json

r = httpx.get("https://gamma-api.polymarket.com/markets", params={
    "limit": 3, "active": "true", "closed": "false",
    "order": "volume", "ascending": "false",
}, timeout=30, verify=False)

markets = r.json()
if isinstance(markets, dict):
    markets = markets.get("data", [])

for m in markets[:3]:
    print(f"Question: {m.get('question','')[:60]}")
    print(f"  conditionId: {m.get('conditionId','')[:30]}...")
    
    clob_ids = m.get("clobTokenIds", "")
    print(f"  clobTokenIds (raw): {repr(clob_ids)[:100]}")
    if isinstance(clob_ids, str):
        try:
            clob_ids = json.loads(clob_ids)
        except: pass
    print(f"  clobTokenIds (parsed): {clob_ids}")
    
    tokens = m.get("tokens", [])
    print(f"  tokens (raw): {repr(tokens)[:100]}")
    
    outcomes = m.get("outcomes", "")
    print(f"  outcomes: {outcomes}")
    
    prices = m.get("outcomePrices", "")
    print(f"  outcomePrices: {prices}")
    print()