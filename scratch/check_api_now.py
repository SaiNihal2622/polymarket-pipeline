#!/usr/bin/env python3
"""Quick check of Railway API and trade count."""
import urllib.request
import json

url = "https://industrious-blessing-production-b110.up.railway.app/api/trades"
try:
    r = urllib.request.urlopen(url, timeout=15)
    d = json.loads(r.read())
    trades = d.get("trades", [])
    print(f"Total trades: {len(trades)}")
    for t in trades[:15]:
        q = t.get("market_question", "")[:60]
        side = t.get("side", "?")
        entry = t.get("entry_price", "?")
        result = t.get("result", "?")
        print(f"  ID={t['id']} | {result} | {side} @ {entry} | {q}")
except Exception as e:
    print(f"API ERROR: {e}")