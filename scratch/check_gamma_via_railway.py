#!/usr/bin/env python3
"""Check Gamma API token IDs via Railway (bypasses India geo-block)."""
import httpx

# Hit Railway's /api/markets endpoint which fetches from Gamma
r = httpx.get("https://industrious-blessing-production-b110.up.railway.app/api/market_maker", timeout=15)
print(f"Status: {r.status_code}")
data = r.json()
print(f"Keys: {list(data.keys())[:10]}")
print()

# Also check a specific Gamma field via trades
r2 = httpx.get("https://industrious-blessing-production-b110.up.railway.app/api/trades", timeout=15)
trades = r2.json().get("trades", [])
for t in trades[:3]:
    print(f"#{t['id']} token_id='{t.get('token_id','')}' market_id='{t.get('market_id','')}'")
    print(f"  signals_json: {t.get('signals_json','')[:80]}")
    print()