#!/usr/bin/env python3
import httpx
import json

# Try both URLs
urls = [
    "https://industrious-blessing-production-b110.up.railway.app/api/trades",
    "https://polymarket-pipeline-production.up.railway.app/api/trades",
]

for url in urls:
    print(f"\n=== Trying: {url} ===")
    try:
        r = httpx.get(url, timeout=15, verify=False)
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            trades = data.get("trades", [])
            print(f"Total trades: {len(trades)}")
            for t in trades:
                tid = t.get("id", "?")
                side = t.get("side", "?")
                status = t.get("status", "?")
                result = t.get("result", "?")
                q = str(t.get("market_question", ""))[:80]
                mid = t.get("market_id", "")[:60]
                amount = t.get("amount_usd", 0)
                price = t.get("market_price", 0)
                strategy = t.get("strategy", "")
                created = t.get("created_at", "")
                print(f"  #{tid} | side={side} | status={status} | result={result}")
                print(f"    q={q}")
                print(f"    market_id={mid}")
                print(f"    amount=${amount} price={price} strategy={strategy}")
                print(f"    created={created}")
                print()
        else:
            print(f"Response: {r.text[:300]}")
    except Exception as e:
        print(f"Error: {e}")

# Also check positions
print("\n=== Checking positions ===")
for url in urls:
    pos_url = url.replace("/trades", "/positions")
    try:
        r = httpx.get(pos_url, timeout=15, verify=False)
        print(f"\n{pos_url}")
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            print(json.dumps(data, indent=2, default=str)[:3000])
    except Exception as e:
        print(f"Error: {e}")

# Check pipeline status
print("\n=== Checking pipeline status ===")
for url in urls:
    status_url = url.replace("/trades", "/pipeline_status")
    try:
        r = httpx.get(status_url, timeout=15, verify=False)
        print(f"\n{status_url}")
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            print(json.dumps(data, indent=2, default=str)[:2000])
    except Exception as e:
        print(f"Error: {e}")