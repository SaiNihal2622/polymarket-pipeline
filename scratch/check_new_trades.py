#!/usr/bin/env python3
"""Check Railway trades after the fix deployment."""
import httpx

r = httpx.get("https://industrious-blessing-production-b110.up.railway.app/api/trades", timeout=15)
trades = r.json().get("trades", [])

print(f"Total trades: {len(trades)}")
print()

from collections import Counter
results = Counter(t.get("result", "?") for t in trades)
print("Result breakdown:")
for k, v in results.items():
    print(f"  {k}: {v}")

# Show newest trades (should have token_ids now)
print(f"\nNewest 5 trades:")
for t in trades[:5]:
    tid = t.get("token_id", "")
    print(f"  #{t['id']} result={t['result']} token_id={tid[:20] if tid else 'EMPTY'}... side={t['side']} ${t['bet_amount']:.2f} @ {t['entry_price']:.3f}")
    print(f"    {t['market_question'][:60]}")

# Check for any "executed" or "error_no_token_id" (new error type)
executed = [t for t in trades if t.get("result") == "executed"]
no_token = [t for t in trades if "no_token" in str(t.get("result", ""))]
print(f"\nExecuted orders: {len(executed)}")
print(f"No-token errors: {len(no_token)}")