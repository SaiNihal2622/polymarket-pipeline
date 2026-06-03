#!/usr/bin/env python3
import httpx
import json
import sys

# Updated URL based on previous discovery
BASE_URL = "https://industrious-blessing-production-b110.up.railway.app"

def check_endpoint(endpoint, name):
    try:
        print(f"\nChecking {name}...")
        r = httpx.get(f"{BASE_URL}{endpoint}", timeout=15, verify=False)
        print(f"  Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            if name == "trades":
                trades = data.get("trades", [])
                print(f"  Total trades: {len(trades)}")
                if trades:
                    for t in trades[:3]:
                        print(f"    #{t.get('id')} | {t.get('side')} | {t.get('status')} | {t.get('result')} | ${t.get('amount_usd',0)}")
                    if len(trades) > 3:
                        print(f"    ... and {len(trades)-3} more")
                else:
                    print("  ✅ No trades yet (clean slate)")
            elif name == "pipeline_status":
                print(f"  Last run: {data.get('last_run', {}).get('started_at', 'Never')}")
                print(f"  Last resolve: {data.get('last_resolve', {}).get('resolved_at', 'Never')}")
            elif name == "positions":
                positions = data.get("positions", [])
                print(f"  Open positions: {len(positions)}")
                if positions:
                    for p in positions[:3]:
                        print(f"    #{p.get('id')} | {p.get('side')} | ${p.get('amount_usd',0)} | P&L: ${p.get('unrealized_pnl',0)}")
            elif name == "summary":
                print(f"  Bankroll: ${data.get('bankroll', 0)}")
                print(f"  Total PnL: ${data.get('total_pnl', 0)}")
                print(f"  Accuracy: {data.get('accuracy_pct', 0)}%")
                print(f"  Total trades: {data.get('total_trades', 0)}")
            return data
        else:
            print(f"  Error: {r.text[:200]}")
            return None
    except Exception as e:
        print(f"  Exception: {e}")
        return None

if __name__ == "__main__":
    print("=== LIVE MODE STATUS CHECK ===")
    
    # Check key endpoints
    check_endpoint("/api/trades", "trades")
    check_endpoint("/api/positions", "positions")
    check_endpoint("/api/pipeline_status", "pipeline_status")
    check_endpoint("/api/summary", "summary")
    
    # Check if we can see recent activity in logs via API
    try:
        print("\nChecking recent activity...")
        r = httpx.get(f"{BASE_URL}/api/logs", timeout=15, verify=False)
        if r.status_code == 200:
            logs = r.json().get("logs", [])
            print(f"  Recent log entries: {len(logs)}")
            if logs:
                for log in logs[-5:]:
                    print(f"    {log[:100]}")
        else:
            print(f"  Logs endpoint: {r.status_code}")
    except Exception as e:
        print(f"  Logs check failed: {e}")
    
    print("\n=== CHECK COMPLETE ===")