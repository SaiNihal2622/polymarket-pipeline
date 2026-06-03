#!/usr/bin/env python3
"""Check what token_ids are being used on Railway."""
import httpx

r = httpx.get("https://industrious-blessing-production-b110.up.railway.app/api/trades", timeout=15)
trades = r.json().get("trades", [])

print("Trade token_ids:")
for t in trades:
    tid = t.get("token_id", "")
    print(f"  #{t['id']} token_id='{tid}' len={len(tid) if tid else 0} result={t['result']}")
    print(f"    market_id={t.get('market_id','')[:30]}")