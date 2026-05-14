#!/usr/bin/env python3
"""Fetch live trades from Railway deployment and analyze profits."""
import urllib.request
import json
import sys

# Try both URLs
URLS = [
    "https://polymarket-pipeline-production.up.railway.app/api/trades",
    "https://demo-runner-production-3f90.up.railway.app/api/trades",
]

for url in URLS:
    print(f"\n{'='*70}")
    print(f"Trying: {url}")
    print('='*70)
    try:
        data = json.loads(urllib.request.urlopen(url, timeout=15).read())
        trades = data.get("trades", data if isinstance(data, list) else [])
        print(f"Total trades: {len(trades)}")
        if trades:
            # Show all keys in first trade
            print(f"\nTrade keys: {list(trades[0].keys())}")
            print(f"\nFirst trade sample: {json.dumps(trades[0], indent=2)[:1000]}")
            
            # Status distribution
            statuses = {}
            for t in trades:
                s = t.get("status", "unknown")
                statuses[s] = statuses.get(s, 0) + 1
            print(f"\nStatus distribution: {statuses}")
            
            # Profit analysis
            total_profit = 0
            profit_trades = []
            for t in trades:
                p = t.get("profit", t.get("pnl", t.get("net_profit", None)))
                if p is not None:
                    try:
                        total_profit += float(p)
                        profit_trades.append(t)
                    except:
                        pass
            
            if profit_trades:
                print(f"\nTrades with profit data: {len(profit_trades)}")
                print(f"Total profit: ${total_profit:.2f}")
            else:
                print("\nNo profit field found. Checking other fields...")
            
            # Show last 10 trades
            print(f"\n--- Last 10 Trades ---")
            for t in trades[-10:]:
                print(f"  #{t.get('id','?')} {str(t.get('market_question','?'))[:70]}")
                print(f"    status={t.get('status','?')} side={t.get('side','?')} price={t.get('market_price','?')} amount={t.get('amount','?')}")
                # Show all profit-related fields
                for k, v in t.items():
                    if any(kw in k.lower() for kw in ['profit', 'loss', 'pnl', 'outcome', 'result', 'payout', 'roi']):
                        print(f"    {k}={v}")
                print()
        else:
            print(f"Response data: {json.dumps(data, indent=2)[:500]}")
    except Exception as e:
        print(f"Error: {e}")

# Also try /api/stats or /api/dashboard endpoints
print("\n" + "="*70)
print("CHECKING OTHER API ENDPOINTS")
print("="*70)

base = "https://polymarket-pipeline-production.up.railway.app"
endpoints = ["/api/stats", "/api/dashboard", "/api/profits", "/api/pnl", "/api/summary", "/api/resolved", "/"]

for ep in endpoints:
    try:
        url = base + ep
        data = urllib.request.urlopen(url, timeout=10).read().decode('utf-8', errors='ignore')
        print(f"\n{ep}: {data[:500]}")
    except Exception as e:
        print(f"\n{ep}: {e}")