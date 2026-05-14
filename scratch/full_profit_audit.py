#!/usr/bin/env python3
"""Full profit audit from live_trades.json + scratch DB files"""
import json
from pathlib import Path
from collections import defaultdict

# Load live_trades.json
lt_path = Path(__file__).parent / "live_trades.json"
if not lt_path.exists():
    print("live_trades.json not found!")
    exit(1)

with open(lt_path) as f:
    trades = json.load(f)

print(f"=== LIVE TRADES JSON: {len(trades)} trades ===")

# Basic stats
wins = [t for t in trades if t.get("result") == "win"]
losses = [t for t in trades if t.get("result") == "loss"]
pending = [t for t in trades if t.get("result") is None or t.get("result") == ""]
resolved = wins + losses

total_bet = sum(t.get("amount_usd", 0) for t in trades)
total_pnl = sum(t.get("pnl", 0) or 0 for t in trades if t.get("pnl") is not None)
win_pnl = sum(t.get("pnl", 0) or 0 for t in wins)
loss_pnl = sum(t.get("pnl", 0) or 0 for t in losses)

print(f"\n=== PROFIT SUMMARY (live_trades.json) ===")
print(f"Total trades: {len(trades)}")
print(f"Resolved: {len(resolved)} (Wins: {len(wins)}, Losses: {len(losses)})")
print(f"Pending: {len(pending)}")
if len(resolved) > 0:
    acc = len(wins) / len(resolved) * 100
    print(f"Accuracy: {acc:.1f}%")
print(f"Total bet (all): ${total_bet:.2f}")
print(f"Total PnL (resolved): ${total_pnl:.2f}")
print(f"  Win PnL: +${win_pnl:.2f}")
print(f"  Loss PnL: ${loss_pnl:.2f}")
if len(resolved) > 0:
    print(f"Avg PnL/trade: ${total_pnl/len(resolved):.2f}")
if total_bet > 0:
    print(f"ROI: {total_pnl/total_bet*100:.1f}%")

# Date range
dates = [t.get("created_at") for t in trades if t.get("created_at")]
if dates:
    print(f"\nDate range: {min(dates)} to {max(dates)}")

# Strategy breakdown
print(f"\n=== PnL by Strategy ===")
strat_stats = defaultdict(lambda: {"cnt": 0, "wins": 0, "losses": 0, "pnl": 0, "bet": 0})
for t in trades:
    s = t.get("strategy", "unknown")
    strat_stats[s]["cnt"] += 1
    strat_stats[s]["bet"] += t.get("amount_usd", 0)
    if t.get("result") == "win":
        strat_stats[s]["wins"] += 1
        strat_stats[s]["pnl"] += t.get("pnl", 0) or 0
    elif t.get("result") == "loss":
        strat_stats[s]["losses"] += 1
        strat_stats[s]["pnl"] += t.get("pnl", 0) or 0

for s, d in sorted(strat_stats.items(), key=lambda x: x[1]["pnl"], reverse=True):
    resolved_s = d["wins"] + d["losses"]
    acc_s = d["wins"] / resolved_s * 100 if resolved_s > 0 else 0
    print(f"  {s}: {d['cnt']} trades ({d['wins']}W/{d['losses']}L, {acc_s:.0f}%) "
          f"PnL=${d['pnl']:.2f} | Bet=${d['bet']:.2f}")

# Daily PnL
print(f"\n=== Daily PnL ===")
daily = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0, "bet": 0})
for t in trades:
    day = t.get("created_at", "unknown")[:10]
    daily[day]["bet"] += t.get("amount_usd", 0)
    if t.get("result") == "win":
        daily[day]["wins"] += 1
        daily[day]["pnl"] += t.get("pnl", 0) or 0
    elif t.get("result") == "loss":
        daily[day]["losses"] += 1
        daily[day]["pnl"] += t.get("pnl", 0) or 0

for day in sorted(daily.keys()):
    d = daily[day]
    resolved_d = d["wins"] + d["losses"]
    acc_d = d["wins"] / resolved_d * 100 if resolved_d > 0 else 0
    print(f"  {day}: {d['wins']+d['losses']} resolved ({d['wins']}W/{d['losses']}L, {acc_d:.0f}%) "
          f"PnL=${d['pnl']:.2f} | Bet=${d['bet']:.2f}")

# Market price analysis (entry prices)
print(f"\n=== Entry Price Distribution ===")
prices = [t.get("market_price", 0) for t in trades]
if prices:
    print(f"Avg entry price: ${sum(prices)/len(prices):.3f}")
    print(f"Min: ${min(prices):.3f}, Max: ${max(prices):.3f}")
    # Win vs loss entry prices
    win_prices = [t.get("market_price", 0) for t in wins]
    loss_prices = [t.get("market_price", 0) for t in losses]
    if win_prices:
        print(f"Avg win entry: ${sum(win_prices)/len(win_prices):.3f}")
    if loss_prices:
        print(f"Avg loss entry: ${sum(loss_prices)/len(loss_prices):.3f}")

# Top wins
print(f"\n=== Top 5 Wins ===")
for t in sorted(wins, key=lambda x: x.get("pnl", 0), reverse=True)[:5]:
    print(f"  +${t.get('pnl',0):.2f} | @{t.get('market_price',0)} | {t.get('strategy','')} | {t.get('market_question','')[:60]}")

# Top losses
print(f"\n=== Top 5 Losses ===")
for t in sorted(losses, key=lambda x: x.get("pnl", 0))[:5]:
    q = t.get('market_question','')[:60]
    print(f"  ${t.get('pnl',0):.2f} | @{t.get('market_price',0)} | {t.get('strategy','')} | {q}")

# Pending trades
if pending:
    print(f"\n=== Pending Trades ({len(pending)}) ===")
    for t in pending:
        print(f"  @{t.get('market_price',0)} | ${t.get('amount_usd',0)} | {t.get('strategy','')} | {t.get('market_question','')[:60]}")
    pending_bet = sum(t.get("amount_usd", 0) for t in pending)
    print(f"  Total pending bet: ${pending_bet:.2f}")

# Time to resolution
print(f"\n=== Resolution Time Analysis ===")
res_times = [t.get("resolution_duration", "") for t in resolved if t.get("resolution_duration")]
if res_times:
    print(f"Sample: {res_times[:5]}")