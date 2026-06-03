#!/usr/bin/env python3
"""Check Railway live trades and diagnose errors."""
import httpx

r = httpx.get("https://industrious-blessing-production-b110.up.railway.app/api/trades", timeout=15)
trades = r.json().get("trades", [])

print(f"Total trades on Railway: {len(trades)}")
print()

for t in trades:
    print(f"#{t['id']} | {t['result']:20s} | {t['side']:3s} ${t['bet_amount']:.2f} @ {t['entry_price']:.3f} | {t['market_question'][:55]}")
    print(f"   strategy={t.get('strategy','')} edge={t.get('edge',0):.3f}")
    print()

# Check the error details
from collections import Counter
results = Counter(t.get("result", "?") for t in trades)
print("Result breakdown:")
for k, v in results.items():
    print(f"  {k}: {v}")