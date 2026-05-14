"""Analyze the live_trades.json snapshot for full profit report."""
import json
from collections import defaultdict

data = json.load(open('scratch/live_trades.json'))
print(f"Total trades in snapshot: {len(data)}")

# Show all keys
if data:
    print(f"Keys: {sorted(data[0].keys())}")

# Categorize
resolved = []
wins = []
losses = []
voids = []
pending = []

for t in data:
    result = (t.get('result') or '').lower()
    if result == 'win':
        wins.append(t)
        resolved.append(t)
    elif result == 'loss':
        losses.append(t)
        resolved.append(t)
    elif result in ('void', 'push'):
        voids.append(t)
        resolved.append(t)
    else:
        pending.append(t)

total_pnl = sum((t.get('pnl') or 0) for t in resolved)
total_wagered = sum((t.get('bet_amount') or t.get('amount_usd') or 0) for t in data)
win_pnl = sum((t.get('pnl') or 0) for t in wins)
loss_pnl = sum((t.get('pnl') or 0) for t in losses)

print(f"\n{'='*60}")
print("SNAPSHOT PROFIT REPORT")
print(f"{'='*60}")
print(f"  Total trades:  {len(data)}")
print(f"  Wins:          {len(wins)}")
print(f"  Losses:        {len(losses)}")
print(f"  Voids:         {len(voids)}")
print(f"  Pending:       {len(pending)}")
print(f"  Resolved:      {len(resolved)}")
print(f"  Total Wagered: ${total_wagered:.2f}")
print(f"  Total P&L:     ${total_pnl:+.2f}")
print(f"  Win P&L:       ${win_pnl:+.2f}")
print(f"  Loss P&L:      ${loss_pnl:+.2f}")
if total_wagered > 0:
    print(f"  ROI:           {total_pnl/total_wagered*100:+.1f}%")
decisive = len(wins) + len(losses)
if decisive > 0:
    print(f"  Win Rate:      {len(wins)/decisive*100:.1f}%")

# By strategy
print(f"\n{'='*60}")
print("BY STRATEGY")
print(f"{'='*60}")
strats = defaultdict(lambda: {'count': 0, 'wins': 0, 'losses': 0, 'pnl': 0, 'wagered': 0})
for t in data:
    s = t.get('strategy') or 'unknown'
    strats[s]['count'] += 1
    strats[s]['pnl'] += t.get('pnl') or 0
    strats[s]['wagered'] += t.get('bet_amount') or t.get('amount_usd') or 0
    result = (t.get('result') or '').lower()
    if result == 'win':
        strats[s]['wins'] += 1
    elif result == 'loss':
        strats[s]['losses'] += 1

for s, d in sorted(strats.items(), key=lambda x: -x[1]['pnl']):
    dec = d['wins'] + d['losses']
    wr = f"{d['wins']/dec*100:.0f}%" if dec > 0 else "N/A"
    roi = f"{d['pnl']/d['wagered']*100:+.1f}%" if d['wagered'] > 0 else "N/A"
    print(f"  {s:<20} {d['count']:>3} trades | {d['wins']}W/{d['losses']}L | WR:{wr:>5} | Wagered:${d['wagered']:.2f} | P&L:${d['pnl']:+.2f} | ROI:{roi}")

# By date
print(f"\n{'='*60}")
print("BY DATE")
print(f"{'='*60}")
dates = defaultdict(lambda: {'count': 0, 'wins': 0, 'losses': 0, 'pnl': 0})
for t in data:
    d = (t.get('created_at') or '')[:10]
    dates[d]['count'] += 1
    dates[d]['pnl'] += t.get('pnl') or 0
    result = (t.get('result') or '').lower()
    if result == 'win':
        dates[d]['wins'] += 1
    elif result == 'loss':
        dates[d]['losses'] += 1

for d in sorted(dates.keys()):
    dd = dates[d]
    dec = dd['wins'] + dd['losses']
    wr = f"{dd['wins']/dec*100:.0f}%" if dec > 0 else "N/A"
    print(f"  {d}: {dd['count']:>3} trades | {dd['wins']}W/{dd['losses']}L | WR:{wr:>5} | P&L:${dd['pnl']:+.2f}")

# All resolved trades detail
print(f"\n{'='*60}")
print("ALL RESOLVED TRADES")
print(f"{'='*60}")
for t in sorted(resolved, key=lambda x: x.get('created_at', '')):
    q = (t.get('market_question') or '')[:55]
    result = t.get('result') or '?'
    side = t.get('side', '?')
    price = t.get('entry_price') or t.get('market_price') or 0
    amount = t.get('bet_amount') or t.get('amount_usd') or 0
    pnl = t.get('pnl') or 0
    strategy = t.get('strategy', '')
    created = (t.get('created_at') or '')[:16]
    sym = "WIN" if result == 'win' else "LOSS" if result == 'loss' else result.upper()
    print(f"  [{created}] {sym:>4} | {side} @{price:.3f} | bet=${amount:.2f} | P&L=${pnl:+.2f} | {strategy} | {q}")

# Pending trades
print(f"\n{'='*60}")
print("PENDING TRADES")
print(f"{'='*60}")
for t in sorted(pending, key=lambda x: x.get('created_at', '')):
    q = (t.get('market_question') or '')[:55]
    side = t.get('side', '?')
    price = t.get('entry_price') or t.get('market_price') or 0
    amount = t.get('bet_amount') or t.get('amount_usd') or 0
    strategy = t.get('strategy', '')
    created = (t.get('created_at') or '')[:16]
    print(f"  [{created}] PEND | {side} @{price:.3f} | bet=${amount:.2f} | {strategy} | {q}")

print(f"\nDone.")