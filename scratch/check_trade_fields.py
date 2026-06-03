#!/usr/bin/env python3
"""Check what fields are available in trades API."""
import httpx
import json

RAILWAY_URL = "https://industrious-blessing-production-b110.up.railway.app"
client = httpx.Client(verify=False, timeout=15)

resp = client.get(f"{RAILWAY_URL}/api/trades")
data = resp.json()
trades = data.get('trades', [])

if trades:
    print("=== FIRST TRADE ALL KEYS ===")
    print(json.dumps(trades[0], indent=2, default=str))
    
    print("\n=== RESOLVED TRADES ===")
    for t in trades:
        if t.get('result') in ('win', 'loss'):
            print(json.dumps(t, indent=2, default=str))

client.close()