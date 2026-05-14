#!/usr/bin/env python3
"""Fetch and analyze profits from Railway deployment."""
import urllib.request
import json

URL = "https://polymarket-pipeline-production.up.railway.app/api/trades"

print("Fetching trades from Railway...")
try:
    resp = urllib.request.urlopen(URL, timeout=15)
    data = json.loads(resp.read())
except Exception as e:
    print(f"ERROR: {e}")
    exit(1)

trades = data.get("trades", [])
print(f"Total trades from API: {len(trades)}")

if not trades:
    print("No trades found!")
    exit(0)

# Show first trade structure
print(f"\n=== Sample Trade Keys ===")
print(list(trades[0].keys()))

# Find result/pnl columns
result_col = None
pnl_col = None
amount_col = None
for key in trades[0].keys():
    if key in ("result", "outcome"):
        result_col = key
    if key in ("pnl", "profit", "profit_usd", "net_pnl"):
        pnl_col = key
    if key in ("bet_amount", "amount_usd", "stake", "amount"):
        amount_col = key

print(f"Result col: {result_col}")
print(f"PnL col: {pnl_col}")
print(f"Amount col: {amount_col}")

# Overall stats
result_counts = {}
pnl_total = 0
bet_total = 0
for t in trades:
    r = t.get(result_col, "unknown") if result_col else "unknown"
    result_counts[r] = result_counts.get(r, 0) + 1
    if pnl_col and t.get(pnl_col) is not None:
        pnl_total += float(t[pnl_col])
    if amount_col and t.get(amount_col) is not None:
        bet_total += float(t[amount_col])

print(f"\n=== Overall Stats ===")
for r, c in sorted(result_counts.items()):
    print(f"  {r}: {c}")
wins = result_counts.get("win", 0)
losses = result_counts.get("loss", 0)
resolved = wins + losses
print(f"  Resolved: {resolved}")
if resolved > 0:
    print(f"  Win Rate: {wins/resolved*100:.1f}%")
print(f"  Total PnL: ${pnl_total:.2f}")
print(f"  Total Bet: ${bet_total:.2f}")
if bet_total > 0:
    print(f"  ROI: {pnl_total/bet_total*100:.2f}%")

# By result
if pnl_col:
    print(f"\n=== PnL by Result ===")
    by_result = {}
    for t in trades:
        r = t.get(result_col, "unknown") if result_col else "unknown"
        if r not in by_result:
            by_result[r] = {"count": 0, "pnl": 0, "bet": 0}
        by_result[r]["count"] += 1
        if t.get(pnl_col) is not None:
            by_result[r]["pnl"] += float(t[pnl_col])
        if amount_col and t.get(amount_col) is not None:
            by_result[r]["bet"] += float(t[amount_col])
    for r, d in sorted(by_result.items()):
        print(f"  {r}: {d['count']} trades, PnL=${d['pnl']:.2f}, Bet=${d['bet']:.2f}")

# By strategy
if "strategy" in trades[0]:
    print(f"\n=== By Strategy ===")
    by_strat = {}
    for t in trades:
        s = t.get("strategy", "none") or "none"
        if s not in by_strat:
            by_strat[s] = {"count": 0, "pnl": 0, "wins": 0}
        by_strat[s]["count"] += 1
        if pnl_col and t.get(pnl_col) is not None:
            by_strat[s]["pnl"] += float(t[pnl_col])
        if t.get(result_col) == "win":
            by_strat[s]["wins"] += 1
    for s, d in sorted(by_strat.items()):
        wr = f"{d['wins']/d['count']*100:.0f}%" if d['count'] > 0 else "N/A"
        print(f"  {s}: {d['count']} trades, PnL=${d['pnl']:.2f}, WinRate={wr}")

# By side
if "side" in trades[0]:
    print(f"\n=== By Side ===")
    by_side = {}
    for t in trades:
        s = t.get("side", "?")
        if s not in by_side:
            by_side[s] = {"count": 0, "pnl": 0, "wins": 0}
        by_side[s]["count"] += 1
        if pnl_col and t.get(pnl_col) is not None:
            by_side[s]["pnl"] += float(t[pnl_col])
        if t.get(result_col) == "win":
            by_side[s]["wins"] += 1
    for s, d in sorted(by_side.items()):
        wr = f"{d['wins']/d['count']*100:.0f}%" if d['count'] > 0 else "N/A"
        print(f"  {s}: {d['count']} trades, PnL=${d['pnl']:.2f}, WinRate={wr}")

# Top wins
if pnl_col and result_col:
    wins_list = [t for t in trades if t.get(result_col) == "win" and t.get(pnl_col) is not None]
    wins_list.sort(key=lambda x: float(x[pnl_col]), reverse=True)
    print(f"\n=== Top 10 Wins ===")
    for t in wins_list[:10]:
        q = str(t.get("market_question", "?"))[:60]
        print(f"  #{t.get('id','?')} ${float(t[pnl_col]):+.2f} | {q}")

    losses_list = [t for t in trades if t.get(result_col) == "loss" and t.get(pnl_col) is not None]
    losses_list.sort(key=lambda x: float(x[pnl_col]))
    print(f"\n=== Top 10 Losses ===")
    for t in losses_list[:10]:
        q = str(t.get("market_question", "?"))[:60]
        print(f"  #{t.get('id','?')} ${float(t[pnl_col]):+.2f} | {q}")

# Recent 20
print(f"\n=== Recent 20 Trades ===")
for t in trades[:20]:
    r = t.get(result_col, "?") if result_col else "?"
    pnl = f"${float(t[pnl_col]):+.2f}" if pnl_col and t.get(pnl_col) is not None else "---"
    amt = f"${float(t[amount_col]):.2f}" if amount_col and t.get(amount_col) is not None else "---"
    q = str(t.get("market_question", "?"))[:50]
    side = t.get("side", "?")
    print(f"  #{t.get('id','?'):>4} [{str(r):>7}] {side:>3} {pnl:>8} {amt:>8} | {q}")

print("\nDone!")