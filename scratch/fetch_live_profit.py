#!/usr/bin/env python3
"""Fetch all trade data from the live Railway API and compute profit."""
import json
import urllib.request
from collections import defaultdict

BASE = "https://industrious-blessing-production-b110.up.railway.app"

def fetch_json(path):
    try:
        resp = urllib.request.urlopen(f"{BASE}{path}", timeout=15)
        return json.loads(resp.read())
    except Exception as e:
        print(f"  Error fetching {path}: {e}")
        return None

# Try multiple endpoints
print("=" * 70)
print("POLYMARKET PIPELINE — LIVE PROFIT ANALYSIS")
print("=" * 70)

# 1. Fetch all trades
print("\n--- Fetching /api/trades ---")
data = fetch_json("/api/trades")
if data:
    trades = data.get("trades", data if isinstance(data, list) else [])
    print(f"Total trades: {len(trades)}")
    
    if trades:
        # Result breakdown
        results = defaultdict(lambda: {"count": 0, "pnl": 0.0, "wagered": 0.0, "trades": []})
        total_pnl = 0.0
        total_wagered = 0.0
        wins = 0
        losses = 0
        pending = 0
        pushes = 0
        
        strategies = defaultdict(lambda: {"count": 0, "wins": 0, "losses": 0, "pnl": 0.0, "wagered": 0.0})
        
        for t in trades:
            result = t.get("result", "unknown")
            pnl = t.get("pnl", 0) or 0
            bet = t.get("bet_amount", 0) or 0
            strategy = t.get("strategy", "unknown")
            side = t.get("side", "?")
            entry = t.get("entry_price", 0)
            question = t.get("market_question", "?")[:60]
            created = t.get("created_at", "?")[:19]
            
            results[result]["count"] += 1
            results[result]["pnl"] += pnl
            results[result]["wagered"] += bet
            
            total_pnl += pnl
            total_wagered += bet
            
            if result == "win":
                wins += 1
            elif result == "loss":
                losses += 1
            elif result == "pending":
                pending += 1
            elif result == "push":
                pushes += 1
            
            strategies[strategy]["count"] += 1
            strategies[strategy]["pnl"] += pnl
            strategies[strategy]["wagered"] += bet
            if result == "win":
                strategies[strategy]["wins"] += 1
            elif result == "loss":
                strategies[strategy]["losses"] += 1
            
            sym = "WIN" if result == "win" else "LOSS" if result == "loss" else "PEND" if result == "pending" else "PUSH" if result == "push" else result.upper()
            print(f"  #{t.get('id',0):>3} [{sym:>4}] {side:>2} @{entry:.3f} ${bet:.0f} | PnL: ${pnl:+.2f} | {strategy} | {question}")
        
        decisive = wins + losses
        accuracy = (wins / decisive * 100) if decisive > 0 else 0
        roi = (total_pnl / total_wagered * 100) if total_wagered > 0 else 0
        
        print(f"\n{'=' * 70}")
        print(f"SUMMARY")
        print(f"{'=' * 70}")
        print(f"  Total trades placed:     {len(trades)}")
        print(f"  Wins:                    {wins}")
        print(f"  Losses:                  {losses}")
        print(f"  Pending:                 {pending}")
        print(f"  Pushes:                  {pushes}")
        print(f"  Accuracy (resolved):     {accuracy:.1f}%")
        print(f"  Total PnL:               ${total_pnl:+.2f}")
        print(f"  Total Wagered:           ${total_wagered:.2f}")
        print(f"  ROI:                     {roi:+.1f}%")
        print(f"  Starting Bankroll:       $50.00 (assumed from config)")
        print(f"  Current Balance:         ${50.00 + total_pnl:.2f}")
        
        print(f"\n--- By Result ---")
        for r, d in results.items():
            print(f"  {r:>10}: {d['count']} trades | Wagered: ${d['wagered']:.2f} | PnL: ${d['pnl']:+.2f}")
        
        print(f"\n--- By Strategy ---")
        for s, d in sorted(strategies.items(), key=lambda x: x[1]["pnl"], reverse=True):
            dec = d["wins"] + d["losses"]
            acc = (d["wins"] / dec * 100) if dec > 0 else 0
            print(f"  {s:>20}: {d['count']} trades ({d['wins']}W/{d['losses']}L = {acc:.0f}%) | Wagered: ${d['wagered']:.2f} | PnL: ${d['pnl']:+.2f}")
        
        # Pending trades expected profit
        pending_trades = [t for t in trades if t.get("result") == "pending"]
        if pending_trades:
            total_expected = sum(t.get("expected_profit", 0) or 0 for t in pending_trades)
            print(f"\n--- Pending Trades ({len(pending_trades)}) ---")
            print(f"  Total expected profit (if all win): ${total_expected:+.2f}")
            for t in pending_trades:
                print(f"    #{t.get('id',0)} | {t.get('side','?')} @{t.get('entry_price',0):.3f} ${t.get('bet_amount',0):.0f} | exp_profit=${t.get('expected_profit',0):.2f} | {t.get('market_question','?')[:60]}")

# 2. Try other API endpoints
for ep in ["/api/stats", "/api/summary", "/api/profit", "/api/dashboard"]:
    print(f"\n--- Trying {ep} ---")
    d = fetch_json(ep)
    if d:
        print(json.dumps(d, indent=2, default=str)[:1000])
    else:
        print("  Not available")