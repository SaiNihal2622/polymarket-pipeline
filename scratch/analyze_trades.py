#!/usr/bin/env python3
"""Fetch trades from live API and analyze real-money P&L math."""
import urllib.request
import json

url = "https://polymarket-pipeline-production.up.railway.app/api/trades"
resp = urllib.request.urlopen(url)
data = json.loads(resp.read())
trades = data.get("trades", [])

print(f"{'='*80}")
print(f"POLYMARKET PIPELINE - TRADE P&L ANALYSIS (REAL MONEY MATH)")
print(f"{'='*80}")
print(f"Total trades in DB: {len(trades)}")
print()

# Separate by status
resolved = [t for t in trades if t.get("status") == "resolved"]
active = [t for t in trades if t.get("status") == "active"]
other = [t for t in trades if t.get("status") not in ("resolved", "active")]

print(f"Resolved: {len(resolved)} | Active: {len(active)} | Other: {len(other)}")
print()

# Analyze resolved trades
total_invested = 0
total_pnl = 0
wins = 0
losses = 0

print(f"{'='*80}")
print(f"RESOLVED TRADES - DETAILED BREAKDOWN")
print(f"{'='*80}")

for t in resolved:
    tid = t.get("id", "?")
    q = t.get("market_question", "?")[:70]
    price = float(t.get("market_price", 0))
    side = t.get("side", "YES")
    amount = float(t.get("amount_usd", 0))
    pnl = float(t.get("pnl", 0))
    outcome = t.get("outcome", "?")
    strategy = t.get("strategy", "?")
    
    # Calculate buy price based on side
    if side == "YES":
        buy_price = price
    else:
        buy_price = 1.0 - price
    
    # Shares = amount / buy_price
    shares = amount / buy_price if buy_price > 0 else 0
    
    # If we won: payout = shares * $1.00, profit = payout - amount
    # If we lost: payout = $0, loss = -amount
    if pnl > 0:
        wins += 1
        actual_pnl = pnl
    else:
        losses += 1
        actual_pnl = pnl
    
    total_invested += amount
    total_pnl += actual_pnl
    
    print(f"\n#{tid}: {q}")
    print(f"  Side: {side} @ {buy_price:.3f} | Bet: ${amount:.2f}")
    print(f"  Shares: {shares:.2f} | Outcome: {outcome}")
    print(f"  P&L: ${pnl:+.2f} | Strategy: {strategy}")

print(f"\n{'='*80}")
print(f"SUMMARY - RESOLVED TRADES")
print(f"{'='*80}")
print(f"Total invested:  ${total_invested:.2f}")
print(f"Total P&L:       ${total_pnl:+.2f}")
print(f"Wins: {wins} | Losses: {losses}")
if (wins + losses) > 0:
    print(f"Win Rate: {wins/(wins+losses)*100:.1f}%")
if total_invested > 0:
    print(f"ROI: {total_pnl/total_invested*100:+.1f}%")
    print(f"Return on capital: ${total_invested + total_pnl:.2f} from ${total_invested:.2f}")

# Active trades
print(f"\n{'='*80}")
print(f"ACTIVE TRADES (OPEN POSITIONS)")
print(f"{'='*80}")
active_total = 0
for t in active:
    tid = t.get("id", "?")
    q = t.get("market_question", "?")[:70]
    price = float(t.get("market_price", 0))
    side = t.get("side", "YES")
    amount = float(t.get("amount_usd", 0))
    active_total += amount
    
    if side == "YES":
        buy_price = price
    else:
        buy_price = 1.0 - price
    shares = amount / buy_price if buy_price > 0 else 0
    
    print(f"  #{tid}: {q}")
    print(f"    {side} @ {buy_price:.3f} | ${amount:.2f} | {shares:.1f} shares")

print(f"\n  Total active capital: ${active_total:.2f}")

# What-if analysis
print(f"\n{'='*80}")
print(f"WHAT IF: $1000 REAL MONEY DEPLOYED")
print(f"{'='*80}")
if total_invested > 0 and (wins + losses) > 0:
    scale = 1000 / total_invested
    scaled_pnl = total_pnl * scale
    print(f"If you bet $1000 proportionally across these same trades:")
    print(f"  Invested: $1000.00")
    print(f"  P&L:      ${scaled_pnl:+.2f}")
    print(f"  Final:    ${1000 + scaled_pnl:.2f}")
    print(f"  ROI:      {scaled_pnl/1000*100:+.1f}%")