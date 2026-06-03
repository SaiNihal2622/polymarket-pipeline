#!/usr/bin/env python3
"""Quick check: fetch live trades from Railway and check Gamma API for resolution."""
import urllib.request
import json
import sys

# 1. Fetch trades from live server
print("=" * 80)
print("FETCHING TRADES FROM LIVE SERVER...")
print("=" * 80)
try:
    req = urllib.request.Request("https://polymarket-pipeline-production.up.railway.app/api/trades")
    req.add_header("User-Agent", "Mozilla/5.0")
    resp = urllib.request.urlopen(req, timeout=20)
    data = json.loads(resp.read())
    trades = data if isinstance(data, list) else data.get("trades", [])
    print(f"Total trades on live server: {len(trades)}")
    for t in trades:
        print(f"  #{t.get('id','?')} | result={t.get('result','?')} | {str(t.get('market_question',''))[:70]}")
        print(f"       side={t.get('side','?')} entry={t.get('entry_price',t.get('market_price','?'))} pnl={t.get('pnl','?')}")
        print(f"       cid={t.get('market_id','?')[:60]}")
        print(f"       resolved_at={t.get('resolved_at','pending')}")
        print()
except Exception as e:
    print(f"ERROR fetching live trades: {e}")

# 2. Now check Gamma API for recent closed/resolved markets
print("=" * 80)
print("CHECKING GAMMA API FOR RECENTLY RESOLVED MARKETS...")
print("=" * 80)
try:
    gamma_url = "https://gamma-api.polymarket.com/markets?closed=true&limit=50&order=endDate&ascending=false"
    req2 = urllib.request.Request(gamma_url)
    req2.add_header("User-Agent", "Mozilla/5.0")
    resp2 = urllib.request.urlopen(req2, timeout=20)
    markets = json.loads(resp2.read())
    items = markets if isinstance(markets, list) else markets.get("data", [])
    
    # Also check each trade's condition ID against Gamma
    if trades:
        for t in trades:
            cid = t.get("market_id", "")
            if not cid:
                continue
            print(f"\n--- Checking trade #{t.get('id')} against Gamma API ---")
            print(f"    Question: {str(t.get('market_question',''))[:80]}")
            print(f"    Condition ID: {cid[:60]}")
            
            # Try slug-based lookup
            slug = t.get("market_slug", "")
            if slug:
                try:
                    slug_url = f"https://gamma-api.polymarket.com/markets?slug={slug}"
                    req3 = urllib.request.Request(slug_url)
                    req3.add_header("User-Agent", "Mozilla/5.0")
                    resp3 = urllib.request.urlopen(req3, timeout=10)
                    mdata = json.loads(resp3.read())
                    mitems = mdata if isinstance(mdata, list) else mdata.get("data", [])
                    for m in mitems:
                        print(f"    GAMMA RESULT: resolved={m.get('resolved')} closed={m.get('closed')} outcome={m.get('outcome')}")
                        print(f"    endDate={m.get('endDate')} active={m.get('active')}")
                except Exception as e:
                    print(f"    Slug lookup error: {e}")
            
            # Try condition ID lookup in the closed markets list
            for m in items:
                mcid = m.get("conditionId", "") or m.get("condition_id", "")
                if cid and mcid and (cid in mcid or mcid in cid):
                    print(f"    MATCH IN CLOSED LIST: resolved={m.get('resolved')} outcome={m.get('outcome')}")
    else:
        print("No trades found on live server!")
        
except Exception as e:
    print(f"ERROR checking Gamma: {e}")

print("\n" + "=" * 80)
print("DONE")
print("=" * 80)