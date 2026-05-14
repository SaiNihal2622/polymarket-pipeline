"""Full profit report from live_trades.json and any DB data."""
import json, os, sqlite3
from datetime import datetime
from collections import defaultdict

print("=" * 70)
print("  POLYMARKET PIPELINE - FULL PROFIT REPORT")
print("=" * 70)

# Load live trades
with open("scratch/live_trades.json") as f:
    trades = json.load(f)

print(f"\nTotal trades loaded: {len(trades)}")

# Parse trades
resolved = [t for t in trades if t.get('result') is not None]
unresolved = [t for t in trades if t.get('result') is None]
wins = [t for t in resolved if t['result'] == 'win']
losses = [t for t in resolved if t['result'] == 'loss']
voids = [t for t in resolved if t['result'] == 'void']

print(f"  Resolved:   {len(resolved)}")
print(f"  Unresolved: {len(unresolved)}")
print(f"  Wins:       {len(wins)}")
print(f"  Losses:     {len(losses)}")
print(f"  Voids:      {len(voids)}")

# PnL
total_pnl = sum(t.get('pnl', 0) or 0 for t in resolved)
total_wagered = sum(t.get('amount_usd', 0) or 0 for t in resolved)
total_win_pnl = sum(t.get('pnl', 0) or 0 for t in wins)
total_loss_pnl = sum(t.get('pnl', 0) or 0 for t in losses)

print(f"\n{'='*70}")
print(f"  OVERALL P&L")
print(f"{'='*70}")
print(f"  Total wagered:      ${total_wagered:.2f}")
print(f"  Total P&L:          ${total_pnl:.2f}")
print(f"  Win P&L:            ${total_win_pnl:.2f}")
print(f"  Loss P&L:           ${total_loss_pnl:.2f}")
if total_wagered > 0:
    print(f"  ROI:                {(total_pnl / total_wagered) * 100:.1f}%")
if len(resolved) > 0:
    print(f"  Win rate:           {len(wins)/len(resolved)*100:.1f}%")
    print(f"  Avg trade size:     ${total_wagered/len(resolved):.2f}")

# By strategy
print(f"\n{'='*70}")
print(f"  BY STRATEGY")
print(f"{'='*70}")
strats = defaultdict(lambda: {'count': 0, 'wins': 0, 'losses': 0, 'pnl': 0, 'wagered': 0})
for t in resolved:
    s = t.get('strategy', 'unknown')
    strats[s]['count'] += 1
    strats[s]['wagered'] += t.get('amount_usd', 0) or 0
    strats[s]['pnl'] += t.get('pnl', 0) or 0
    if t['result'] == 'win':
        strats[s]['wins'] += 1
    elif t['result'] == 'loss':
        strats[s]['losses'] += 1

for s, d in sorted(strats.items()):
    wr = d['wins']/d['count']*100 if d['count'] > 0 else 0
    roi = d['pnl']/d['wagered']*100 if d['wagered'] > 0 else 0
    print(f"\n  {s}:")
    print(f"    Trades: {d['count']} (W:{d['wins']} L:{d['losses']})")
    print(f"    Win Rate: {wr:.1f}%")
    print(f"    Wagered: ${d['wagered']:.2f} | P&L: ${d['pnl']:.2f} | ROI: {roi:.1f}%")

# By side (YES vs NO)
print(f"\n{'='*70}")
print(f"  BY SIDE")
print(f"{'='*70}")
for side in ['YES', 'NO']:
    side_trades = [t for t in resolved if t.get('side') == side]
    side_wins = [t for t in side_trades if t['result'] == 'win']
    side_pnl = sum(t.get('pnl', 0) or 0 for t in side_trades)
    side_wagered = sum(t.get('amount_usd', 0) or 0 for t in side_trades)
    wr = len(side_wins)/len(side_trades)*100 if side_trades else 0
    print(f"  {side}: {len(side_trades)} trades | Win Rate: {wr:.1f}% | P&L: ${side_pnl:.2f} | Wagered: ${side_wagered:.2f}")

# By classification
print(f"\n{'='*70}")
print(f"  BY CLASSIFICATION (AI signal direction)")
print(f"{'='*70}")
for cls in ['bullish', 'bearish']:
    cls_trades = [t for t in resolved if t.get('classification') == cls]
    cls_wins = [t for t in cls_trades if t['result'] == 'win']
    cls_pnl = sum(t.get('pnl', 0) or 0 for t in cls_trades)
    wr = len(cls_wins)/len(cls_trades)*100 if cls_trades else 0
    print(f"  {cls}: {len(cls_trades)} trades | Win Rate: {wr:.1f}% | P&L: ${cls_pnl:.2f}")

# By market type
print(f"\n{'='*70}")
print(f"  BY MARKET CATEGORY")
print(f"{'='*70}")
categories = defaultdict(lambda: {'count': 0, 'wins': 0, 'pnl': 0})
for t in resolved:
    q = t.get('market_question', '').lower()
    if any(k in q for k in ['fight', 'ko', 'tko', 'boxing', 'mma', 'ufc']):
        cat = 'Combat Sports'
    elif any(k in q for k in ['goalscorer', 'goal', 'score', 'football', 'soccer', 'match']):
        cat = 'Football/Soccer'
    elif any(k in q for k in ['trump', 'president', 'biden', 'white house', 'epstein', 'political']):
        cat = 'Politics'
    elif any(k in q for k in ['price of', 'bitcoin', 'ethereum', 'crypto', 'btc', 'eth']):
        cat = 'Crypto'
    elif any(k in q for k in ['idol', 'celebrity', 'tv show', 'reality']):
        cat = 'Entertainment'
    elif any(k in q for k in ['american idol', 'oscar', 'grammy', 'award']):
        cat = 'Awards'
    elif any(k in q for k in ['cricket', 'ipl', 'wicket', 'run']):
        cat = 'Cricket'
    else:
        cat = 'Other'
    categories[cat]['count'] += 1
    categories[cat]['pnl'] += t.get('pnl', 0) or 0
    if t['result'] == 'win':
        categories[cat]['wins'] += 1

for cat, d in sorted(categories.items(), key=lambda x: x[1]['pnl']):
    wr = d['wins']/d['count']*100 if d['count'] > 0 else 0
    print(f"  {cat:20s}: {d['count']:3d} trades | Win Rate: {wr:5.1f}% | P&L: ${d['pnl']:8.2f}")

# Unresolved trades
if unresolved:
    print(f"\n{'='*70}")
    print(f"  UNRESOLVED TRADES ({len(unresolved)})")
    print(f"{'='*70}")
    pending_wagered = sum(t.get('amount_usd', 0) or 0 for t in unresolved)
    for t in unresolved:
        print(f"  ID {t['id']}: {t['market_question'][:60]} | ${t.get('amount_usd',0):.2f} | {t.get('side')} @ {t.get('market_price')}")
    print(f"\n  Total pending wager: ${pending_wagered:.2f}")

# Time analysis
print(f"\n{'='*70}")
print(f"  TIME ANALYSIS")
print(f"{'='*70}")
if trades:
    dates = defaultdict(lambda: {'count': 0, 'pnl': 0, 'wins': 0})
    for t in resolved:
        d = t.get('created_at', '')[:10]
        dates[d]['count'] += 1
        dates[d]['pnl'] += t.get('pnl', 0) or 0
        if t['result'] == 'win':
            dates[d]['wins'] += 1
    
    for d in sorted(dates.keys()):
        dd = dates[d]
        wr = dd['wins']/dd['count']*100 if dd['count'] > 0 else 0
        print(f"  {d}: {dd['count']:3d} trades | Win Rate: {wr:5.1f}% | P&L: ${dd['pnl']:8.2f}")

# Worst trades
print(f"\n{'='*70}")
print(f"  WORST TRADES (by P&L)")
print(f"{'='*70}")
worst = sorted(resolved, key=lambda t: t.get('pnl', 0) or 0)[:5]
for t in worst:
    print(f"  ID {t['id']}: {t['market_question'][:50]} | P&L: ${t.get('pnl',0):.2f} | {t['result']}")

# Best trades
print(f"\n{'='*70}")
print(f"  BEST TRADES (by P&L)")
print(f"{'='*70}")
best = sorted(resolved, key=lambda t: t.get('pnl', 0) or 0, reverse=True)[:5]
for t in best:
    print(f"  ID {t['id']}: {t['market_question'][:50]} | P&L: ${t.get('pnl',0):.2f} | {t['result']}")

# Signal quality analysis
print(f"\n{'='*70}")
print(f"  SIGNAL QUALITY ANALYSIS")
print(f"{'='*70}")
for t in resolved[:3]:
    sp = t.get('signals_parsed', {})
    print(f"\n  Trade {t['id']} ({t['result']}):")
    print(f"    Question: {t['market_question'][:50]}")
    print(f"    Market Price: {t.get('market_price')} | Side: {t.get('side')}")
    print(f"    RRF: {sp.get('rrf', 'N/A')} | AI: {sp.get('ai', 'N/A')}")
    print(f"    Consensus: {sp.get('consensus', 'N/A')} | Materiality: {t.get('materiality')}")
    print(f"    Edge: {t.get('edge')} | Claude Score: {t.get('claude_score')}")
    print(f"    P&L: ${t.get('pnl', 0):.2f}")

print(f"\n{'='*70}")
print(f"  SUMMARY")
print(f"{'='*70}")
print(f"  Total Resolved Trades: {len(resolved)}")
print(f"  Win Rate: {len(wins)/len(resolved)*100:.1f}%" if resolved else "  N/A")
print(f"  Total P&L: ${total_pnl:.2f}")
print(f"  Total Wagered: ${total_wagered:.2f}")
print(f"  ROI: {(total_pnl / total_wagered) * 100:.1f}%" if total_wagered > 0 else "  N/A")
print(f"  Pending Trades: {len(unresolved)} (${sum(t.get('amount_usd',0) or 0 for t in unresolved):.2f})")
print(f"\n{'='*70}")