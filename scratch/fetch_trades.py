#!/usr/bin/env python3
"""Fetch and analyze trades from the live dashboard."""
import urllib.request
import json

URL = "https://demo-runner-production-3f90.up.railway.app/api/trades"

try:
    resp = urllib.request.urlopen(URL, timeout=15)
    data = json.loads(resp.read())
    # API may return list directly or dict with "trades" key
    if isinstance(data, list):
        trades = data
    else:
        trades = data.get("trades", [])
    print(f"Total trades: {len(trades)}\n")
    
    total_bet = 0
    total_payout = 0
    wins = 0
    losses = 0
    pending = 0
    
    for t in trades:
        tid = t.get("id", "?")
        q = t.get("market_question", "?")[:70]
        price = t.get("market_price", 0) or 0
        side = t.get("side", "?")
        amount = t.get("amount_usd", 0) or 0
        status = t.get("status", "?")
        strategy = t.get("strategy", "?")
        outcome = t.get("outcome", None)
        
        # Calculate buy price
        if side == "YES":
            buy_price = price
        else:
            buy_price = 1.0 - price
        
        if buy_price > 0:
            shares = amount / buy_price
            payout_if_win = shares * 1.0
            profit_if_win = payout_if_win - amount
            roi = (profit_if_win / amount) * 100 if amount > 0 else 0
        else:
            shares = 0
            payout_if_win = 0
            profit_if_win = 0
            roi = 0
        
        total_bet += amount
        
        if status == "won":
            wins += 1
            total_payout += payout_if_win
        elif status == "lost":
            losses += 1
        elif status in ("pending", "open", "filled"):
            pending += 1
            total_payout += payout_if_win  # potential
        
        print(f"#{tid} | {q}")
        print(f"   price={price:.3f} side={side} bet=${amount:.2f} status={status} strat={strategy}")
        print(f"   buy={buy_price:.3f} shares={shares:.1f} payout=${payout_if_win:.2f} profit=${profit_if_win:.2f} ROI={roi:.0f}%")
        if outcome is not None:
            print(f"   outcome={outcome}")
        print()
    
    resolved = wins + losses
    acc = (wins / resolved * 100) if resolved > 0 else 0
    total_profit = total_payout - total_bet
    
    print("=" * 60)
    print(f"SUMMARY:")
    print(f"  Total bet: ${total_bet:.2f}")
    print(f"  Resolved: {resolved} (W:{wins} L:{losses})")
    print(f"  Pending: {pending}")
    print(f"  Accuracy: {acc:.1f}%")
    print(f"  Potential payout: ${total_payout:.2f}")
    print(f"  Potential profit: ${total_profit:.2f}")
    if total_bet > 0:
        print(f"  Portfolio ROI: {total_profit/total_bet*100:.1f}%")
    
except Exception as e:
    print(f"Error: {e}")