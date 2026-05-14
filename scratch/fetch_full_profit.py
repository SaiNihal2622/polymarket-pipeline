"""Fetch and analyze ALL trades from every Railway deployment."""
import json
import urllib.request
from collections import defaultdict

URLS = {
    "demo-runner": "https://demo-runner-production-3f90.up.railway.app/api/trades",
    "pipeline-prod": "https://polymarket-pipeline-production.up.railway.app/api/trades",
    "industrious": "https://industrious-blessing-production-b110.up.railway.app/api/trades",
}

all_trades = []

for name, url in URLS.items():
    print(f"\n{'='*60}")
    print(f"FETCHING: {name}")
    print(f"  URL: {url}")
    print(f"{'='*60}")
    try:
        resp = urllib.request.urlopen(url, timeout=15)
        data = json.loads(resp.read())
        
        # Handle different response formats
        if isinstance(data, list):
            trades = data
        elif isinstance(data, dict):
            trades = data.get('trades', data.get('data', []))
        else:
            trades = []
        
        print(f"  Status: OK | Trades: {len(trades)}")
        
        for t in trades:
            t['_source'] = name
            all_trades.append(t)
        
        # Show sample
        if trades:
            print(f"  Sample trade keys: {list(trades[0].keys())}")
            print(f"  Sample: {json.dumps(trades[0], indent=2)[:300]}")
            
    except Exception as e:
        print(f"  Error: {e}")

print(f"\n{'='*60}")
print(f"TOTAL TRADES ACROSS ALL SOURCES: {len(all_trades)}")
print(f"{'='*60}")

if not all_trades:
    print("No trades found from any source!")
    exit()

# Normalize and analyze
# Print all keys from first trade
print(f"\nTrade keys: {sorted(all_trades[0].keys())}")

# Find the right column names
sample = all_trades[0]
print(f"\nSample full trade:")
print(json.dumps(sample, indent=2, default=str)[:1000])

# Try to find resolved trades
resolved = []
wins = []
losses = []
voids = []
pending = []

for t in all_trades:
    result = t.get('result') or t.get('outcome') or t.get('status')
    if result in ('win', 'Win', 'WIN'):
        wins.append(t)
        resolved.append(t)
    elif result in ('loss', 'Loss', 'LOSS'):
        losses.append(t)
        resolved.append(t)
    elif result in ('void', 'Void', 'VOID', 'push', 'Push'):
        voids.append(t)
        resolved.append(t)
    else:
        pending.append(t)

print(f"\n{'='*60}")
print("TRADE STATUS BREAKDOWN")
print(f"{'='*60}")
print(f"  Wins:    {len(wins)}")
print(f"  Losses:  {len(losses)}")
print(f"  Voids:   {len(voids)}")
print(f"  Pending: {len(pending)}")
print(f"  Resolved total: {len(resolved)}")

# Calculate P&L
total_pnl = 0
total_wagered = 0
for t in all_trades:
    pnl = t.get('pnl', 0) or 0
    amount = t.get('amount_usd') or t.get('bet_amount') or 0
    total_pnl += pnl
    total_wagered += amount

print(f"\n  Total Wagered: ${total_wagered:.2f}")
print(f"  Total P&L:     ${total_pnl:.2f}")
if total_wagered > 0:
    print(f"  ROI:           {total_pnl/total_wagered*100:.1f}%")

decisive = len(wins) + len(losses)
if decisive > 0:
    print(f"  Win Rate:      {len(wins)/decisive*100:.1f}%")

# By strategy
print(f"\n{'='*60}")
print("BY STRATEGY")
print(f"{'='*60}")
strats = defaultdict(lambda: {'count': 0, 'wins': 0, 'losses': 0, 'pnl': 0, 'wagered': 0})
for t in all_trades:
    s = t.get('strategy') or 'unknown'
    strats[s]['count'] += 1
    strats[s]['pnl'] += t.get('pnl', 0) or 0
    strats[s]['wagered'] += t.get('amount_usd') or t.get('bet_amount') or 0
    result = t.get('result') or t.get('outcome') or ''
    if result.lower() == 'win':
        strats[s]['wins'] += 1
    elif result.lower() == 'loss':
        strats[s]['losses'] += 1

for s, d in sorted(strats.items(), key=lambda x: -x[1]['pnl']):
    dec = d['wins'] + d['losses']
    wr = f"{d['wins']/dec*100:.0f}%" if dec > 0 else "N/A"
    roi = f"{d['pnl']/d['wagered']*100:.1f}%" if d['wagered'] > 0 else "N/A"
    print(f"  {s:<20} {d['count']:>3} trades | {d['wins']}W/{d['losses']}L | WR:{wr:>5} | Wagered:${d['wagered']:.2f} | P&L:${d['pnl']:+.2f} | ROI:{roi}")

# By date
print(f"\n{'='*60}")
print("BY DATE")
print(f"{'='*60}")
dates = defaultdict(lambda: {'count': 0, 'wins': 0, 'losses': 0, 'pnl': 0})
for t in all_trades:
    d = (t.get('created_at') or '')[:10]
    dates[d]['count'] += 1
    dates[d]['pnl'] += t.get('pnl', 0) or 0
    result = (t.get('result') or t.get('outcome') or '').lower()
    if result == 'win':
        dates[d]['wins'] += 1
    elif result == 'loss':
        dates[d]['losses'] += 1

for d in sorted(dates.keys()):
    dd = dates[d]
    dec = dd['wins'] + dd['losses']
    wr = f"{dd['wins']/dec*100:.0f}%" if dec > 0 else "N/A"
    print(f"  {d}: {dd['count']:>3} trades | {dd['wins']}W/{dd['losses']}L | WR:{wr:>5} | P&L:${dd['pnl']:+.2f}")

# By source
print(f"\n{'='*60}")
print("BY SOURCE (Railway deployment)")
print(f"{'='*60}")
sources = defaultdict(lambda: {'count': 0, 'pnl': 0, 'resolved': 0})
for t in all_trades:
    s = t.get('_source', 'unknown')
    sources[s]['count'] += 1
    sources[s]['pnl'] += t.get('pnl', 0) or 0
    result = (t.get('result') or t.get('outcome') or '').lower()
    if result in ('win', 'loss'):
        sources[s]['resolved'] += 1

for s, d in sources.items():
    print(f"  {s}: {d['count']} trades | {d['resolved']} resolved | P&L:${d['pnl']:+.2f}")

# Print ALL resolved trades
print(f"\n{'='*60}")
print("ALL RESOLVED TRADES")
print(f"{'='*60}")
for t in sorted(resolved, key=lambda x: x.get('created_at', '')):
    q = (t.get('market_question') or t.get('question') or '')[:55]
    result = t.get('result') or t.get('outcome') or '?'
    side = t.get('side', '?')
    price = t.get('market_price') or t.get('entry_price') or 0
    amount = t.get('amount_usd') or t.get('bet_amount') or 0
    pnl = t.get('pnl', 0) or 0
    strategy = t.get('strategy', '')
    created = (t.get('created_at') or '')[:16]
    sym = "WIN" if result.lower() == 'win' else "LOSS" if result.lower() == 'loss' else result.upper()
    print(f"  [{created}] {sym:>4} | {side} @{price:.2f} | bet=${amount:.2f} | P&L=${pnl:+.2f} | {strategy} | {q}")

print(f"\nDone. Total trades: {len(all_trades)}")