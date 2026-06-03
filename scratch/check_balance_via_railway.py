#!/usr/bin/env python3
"""Check wallet balance via Railway's dashboard API."""
import httpx

# Check Railway pipeline status for wallet info
r = httpx.get("https://industrious-blessing-production-b110.up.railway.app/api/pipeline_status", timeout=15)
data = r.json()
print(f"Pipeline status: {data}")

# Check trades - look for successful orders
r2 = httpx.get("https://industrious-blessing-production-b110.up.railway.app/api/trades", timeout=15)
trades = r2.json().get("trades", [])
from collections import Counter
results = Counter(t.get("result", "?") for t in trades)
print(f"\nTrade results: {dict(results)}")

# Just look at newest trades
if len(trades) > 0:
    newest = trades[0]
    print(f"\nNewest trade:")
    print(f"  #{newest['id']} | {newest['result']}")
    print(f"  {newest['market_question'][:60]}")
    print(f"  side={newest['side']} ${newest['bet_amount']:.2f} @ {newest['entry_price']:.3f}")
    tid = newest.get("token_id", "")
    print(f"  token_id={tid[:25] if tid else 'EMPTY'}...")