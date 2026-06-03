#!/usr/bin/env python3
import httpx
import json

BASE = "https://industrious-blessing-production-b110.up.railway.app"

# Check trades
print("=== Trades ===")
r = httpx.get(f"{BASE}/api/trades", timeout=15, verify=False)
data = r.json()
trades = data.get("trades", [])
resolved = [t for t in trades if t.get("result") not in ("pending", None, "", "?")]
pending = [t for t in trades if t.get("result") in ("pending", None, "", "?")]
print(f"Total: {len(trades)}, Resolved: {len(resolved)}, Pending: {len(pending)}")
print()

for t in resolved:
    tid = t.get("id", "?")
    result = t.get("result", "?")
    q = str(t.get("market_question", ""))[:70]
    side = t.get("side", "?")
    pnl = t.get("pnl", 0)
    print(f"  #{tid} | {result} | side={side} | pnl={pnl} | {q}")

# Check cashouts
print("\n=== Cashouts ===")
r2 = httpx.get(f"{BASE}/api/cashouts", timeout=15, verify=False)
if r2.status_code == 200:
    cashouts = r2.json().get("cashouts", [])
    print(f"Cashout events: {len(cashouts)}")
    for c in cashouts:
        print(f"  #{c.get('id')} | {c.get('result')} | pnl={c.get('pnl')} | {str(c.get('market_question',''))[:60]}")

# Pipeline status
print("\n=== Pipeline Status ===")
r3 = httpx.get(f"{BASE}/api/pipeline_status", timeout=15, verify=False)
if r3.status_code == 200:
    print(json.dumps(r3.json(), indent=2, default=str)[:1500])

# Summary
print("\n=== Summary ===")
r4 = httpx.get(f"{BASE}/api/summary", timeout=15, verify=False)
if r4.status_code == 200:
    print(json.dumps(r4.json(), indent=2, default=str)[:1000])