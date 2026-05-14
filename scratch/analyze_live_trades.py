#!/usr/bin/env python3
"""Analyze the live trades JSON from Railway."""
import json

with open('scratch/live_trades.json') as f:
    trades = json.load(f)

print(f"Total trades in JSON: {len(trades)}")
print("=" * 90)

# Basic stats
wins = [t for t in trades if t.get('result') == 'win']
losses = [t for t in trades if t.get('result') == 'loss']
pending = [t for t in trades if t.get('result') == 'pending']

total_wagered = sum((t.get('amount_usd') or 0) for t in trades)
total_pnl = sum((t.get('pnl') or 0) for t in trades)
win_pnl = sum((t.get('pnl') or 0) for t in wins)
loss_pnl = sum((t.get('pnl') or 0) for t in losses)

decisive = len(wins) + len(losses)
accuracy = (len(wins) / decisive * 100) if decisive > 0 else 0

print(f"Wins:    {len(wins)}")
print(f"Losses:  {len(losses)}")
print(f"Pending: {len(pending)}")
print(f"Accuracy: {accuracy:.1f}%")
print(f"Total Wagered: ${total_wagered:.2f}")
print(f"Total PnL:     ${total_pnl:+.2f}")
print(f"Win PnL:       ${win_pnl:+.2f}")
print(f"Loss PnL:      ${loss_pnl:+.2f}")
print()

# By strategy
strategies = {}
for t in trades:
    s = t.get('strategy', 'unknown')
    if s not in strategies:
        strategies[s] = {'wins': 0, 'losses': 0, 'pnl': 0, 'total': 0, 'wagered': 0}
    strategies[s]['total'] += 1
    strategies[s]['wagered'] += (t.get('amount_usd') or 0)
    if t.get('result') == 'win':
        strategies[s]['wins'] += 1
        strategies[s]['pnl'] += (t.get('pnl') or 0)
    elif t.get('result') == 'loss':
        strategies[s]['losses'] += 1
        strategies[s]['pnl'] += (t.get('pnl') or 0)

print("BY STRATEGY:")
print("-" * 90)
for s, v in sorted(strategies.items(), key=lambda x: x[1]['pnl'], reverse=True):
    dec = v['wins'] + v['losses']
    acc = (v['wins'] / dec * 100) if dec > 0 else 0
    print(f"  {s:<25} {v['total']:>3} trades | {v['wins']}W/{v['losses']}L | "
          f"{acc:>5.1f}% acc | PnL: ${v['pnl']:>+7.2f} | Wagered: ${v['wagered']:.2f}")

# Each trade detail
print()
print("ALL TRADES:")
print("-" * 90)
for t in sorted(trades, key=lambda x: x.get('created_at', '')):
    result_emoji = '✅' if t.get('result') == 'win' else '❌' if t.get('result') == 'loss' else '⏳'
    pnl = t.get('pnl') or 0
    edge = t.get('edge') or 0
    mat = t.get('materiality') or 0
    price = t.get('market_price') or 0
    amt = t.get('amount_usd') or 0
    resolved = t.get('resolved_at') or 'N/A'
    print(f"  {result_emoji} #{t.get('id', '?'):>4} | ${pnl:>+6.2f} | "
          f"{t.get('side', '?'):<4} @{price:.2f} | "
          f"${amt:.2f} | {t.get('strategy', '?'):<20} | "
          f"{t.get('market_question', '')[:50]}")
    print(f"     Created: {t.get('created_at', '?')} | Edge: {edge:.3f} | "
          f"Mat: {mat:.3f} | Resolved: {resolved[:19]} | "
          f"Duration: {t.get('time_to_resolve', '?')}")

# Expected profit analysis
exp_profit = sum(t.get('expected_profit', 0) for t in trades)
print(f"\nExpected Profit (pre-trade estimate): ${exp_profit:+.2f}")
print(f"Actual Profit:                        ${total_pnl:+.2f}")

# Edge analysis
avg_edge = sum(t.get('edge', 0) for t in trades) / len(trades)
avg_mat = sum(t.get('materiality', 0) for t in trades) / len(trades)
print(f"\nAvg Edge:        {avg_edge:.3f}")
print(f"Avg Materiality: {avg_mat:.3f}")

# Entry price analysis
print("\nENTRY PRICE DISTRIBUTION:")
for t in trades:
    price = t.get('market_price', 0)
    r = t.get('result', '?')
    pnl_val = t.get('pnl') or 0
    price_val = t.get('market_price') or 0
    print(f"  {(t.get('result') or '?'):>7} @ {price_val:.3f} -> PnL ${pnl_val:+.2f}")
