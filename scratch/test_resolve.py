#!/usr/bin/env python3
"""Quick test: why can't we resolve these 3 trades?"""
import httpx, json
urllib3_verify = False

GAMMA = "https://gamma-api.polymarket.com"

trades = [
    {"id": 833, "q": "Cavaliers vs. Pistons", "cid": "0x19b188fef4fd6dfe1f1fb0a4aa861208fd886e76c1533d5fc3b3bf97a3433c9e"},
    {"id": 834, "q": "Will Coinbase Global, Inc. (COIN) hit (LOW) $190 Week of May 4 2026?", "cid": ""},
    {"id": 835, "q": "Will Coinbase Global, Inc. (COIN) hit (LOW) $182.50 Week of May 4 2026?", "cid": "0x375a62b524251ddbfd4f74e6fd6fc8a8ac9acd279cc15dd0e1060d10f51cc575"},
]

for t in trades:
    print(f"\n=== Trade #{t['id']}: {t['q'][:60]} ===")
    
    # Try question search
    for closed_val in ["true", "false"]:
        r = httpx.get(f"{GAMMA}/markets", params={"question": t["q"][:100], "limit": 5, "closed": closed_val}, timeout=10, verify=False)
        data = r.json()
        items = data if isinstance(data, list) else data.get("data", [])
        print(f"  question search (closed={closed_val}): {len(items)} results")
        for m in items[:2]:
            print(f"    Q: {m.get('question','')[:80]}")
            print(f"    outcomePrices: {m.get('outcomePrices')}")
            print(f"    resolvedOutcome: {m.get('resolvedOutcome')}")
            print(f"    closed: {m.get('closed')} active: {m.get('active')}")
            print(f"    conditionId: {m.get('conditionId','')[:30]}...")
    
    # Try conditionId
    if t["cid"]:
        for param in ["conditionId", "condition_id"]:
            r = httpx.get(f"{GAMMA}/markets", params={param: t["cid"], "limit": 1}, timeout=10, verify=False)
            data = r.json()
            items = data if isinstance(data, list) else data.get("data", [])
            print(f"  {param} search: {len(items)} results")
            for m in items[:1]:
                print(f"    Q: {m.get('question','')[:80]}")
                print(f"    outcomePrices: {m.get('outcomePrices')}")
                print(f"    resolvedOutcome: {m.get('resolvedOutcome')}")
                print(f"    closed: {m.get('closed')} active: {m.get('active')}")

    # Try slug
    r = httpx.get(f"{GAMMA}/markets", params={"slug": t["q"].lower().replace(" ", "-")[:60], "limit": 3}, timeout=10, verify=False)
    data = r.json()
    items = data if isinstance(data, list) else data.get("data", [])
    print(f"  slug search: {len(items)} results")