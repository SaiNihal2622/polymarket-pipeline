"""Comprehensive audit of live Railway trades - fetches all data and analyzes."""
import json, urllib.request
from datetime import datetime, timezone

API = "https://demo-runner-production-3f90.up.railway.app"

def fetch(endpoint):
    resp = urllib.request.urlopen(f"{API}{endpoint}", timeout=20)
    return json.loads(resp.read())

# Fetch everything
trades = fetch("/api/trades")
summary = fetch("/api/summary")
config = fetch("/api/config")

s = summary["summary"]
strats = summary["strategies"]
signals = summary["signals"]

print("=" * 70)
print(f"DEMO RUN AUDIT — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
print("=" * 70)

# Config
print(f"\n[CONFIG]")
print(f"  Bankroll: ${config['bankroll_usd']}")
print(f"  Mode: {config['mode']}")
print(f"  Edge threshold: {config['edge_threshold']:.0%}")
print(f"  Materiality: {config['materiality_threshold']:.0%}")
print(f"  Max bet: ${config['max_bet_usd']}")
print(f"  Scan interval: {config['scan_interval_min']}min")
print(f"  Resolve interval: {config['resolve_interval_min']}min")
print(f"  Window: {config['demo_hours_window']}h")

# Summary
print(f"\n[SUMMARY]")
print(f"  Total trades: {s['total_trades']}")
print(f"  Resolved: {s['resolved']}")
print(f"  Pending: {s['pending']}")
print(f"  Wins: {s['wins']}")
print(f"  Losses: {s['losses']}")
print(f"  Accuracy: {s['accuracy_pct']:.1f}%")
print(f"  Bankroll: ${s['bankroll']:.2f}")
print(f"  PnL today: ${s['todays_pnl']:.2f}")
print(f"  Total PnL: ${s['total_pnl']:.2f}")
print(f"  Go-live remaining: {s['go_live_remaining']} trades")
print(f"  Trade allowed: {s['trades_today_allowed']}")

# Per-trade breakdown
print(f"\n[ALL TRADES - {len(trades)} total]")
wins_list = []
losses_list = []
pending_list = []

for t in trades:
    q = str(t.get('market_question', ''))[:60]
    side = t.get('side', '?')
    score = t.get('claude_score', 0)
    edge = t.get('edge', 0)
    ev = t.get('expected_profit', 0)
    result = t.get('result', 'pending')
    strategy = t.get('strategy', '?')
    market_price = t.get('market_price', 0)
    entry_price = t.get('entry_price', 0)
    settle_price = t.get('settle_price', None)
    resolution = t.get('resolution', None)
    pnl = t.get('pnl', None)
    materiality = t.get('materiality', None)
    
    result_icon = "✅" if result == 'WIN' else ("❌" if result == 'LOSS' else "⏳")
    
    print(f"\n  {result_icon} ID={t['id']} | {q}")
    print(f"    Side={side} | Strategy={strategy}")
    print(f"    Score={score} | Edge={edge:.3f} | EV=${ev:.2f}")
    print(f"    Market price={market_price} | Entry={entry_price}")
    if settle_price is not None:
        print(f"    Settle price={settle_price} | Resolution={resolution}")
    if pnl is not None:
        print(f"    PnL=${pnl:.2f}")
    if materiality is not None:
        print(f"    Materiality={materiality}")
    
    if result == 'WIN':
        wins_list.append(t)
    elif result == 'LOSS':
        losses_list.append(t)
    else:
        pending_list.append(t)

# Win/Loss analysis
print(f"\n{'=' * 70}")
print(f"[WIN/LOSS ANALYSIS]")
if wins_list:
    print(f"\n  WINS ({len(wins_list)}):")
    for t in wins_list:
        print(f"    ID={t['id']}: {str(t.get('market_question',''))[:50]} | edge={t.get('edge',0):.3f} | pnl=${t.get('pnl',0):.2f}")
if losses_list:
    print(f"\n  LOSSES ({len(losses_list)}):")
    for t in losses_list:
        print(f"    ID={t['id']}: {str(t.get('market_question',''))[:50]} | edge={t.get('edge',0):.3f} | pnl=${t.get('pnl',0):.2f}")

# Strategy breakdown
print(f"\n[STRATEGIES]")
for st in strats:
    print(f"  {st['strategy']}: {st['trades']} trades, {st['wins']}W/{st['losses']}L, "
          f"acc={st['accuracy_pct']:.1f}%, pnl=${st['pnl']:.2f}")

# Signal breakdown
print(f"\n[SIGNALS]")
for sig_name, sig in signals.items():
    print(f"  {sig['label']}: {sig['trades']} trades, {sig['wins']}W/{sig['losses']}L, "
          f"acc={sig['accuracy_pct']:.1f}%, avg_conf={sig['avg_conf']:.3f}")

# Edge/EV stats
edges = [t.get('edge', 0) for t in trades if t.get('edge')]
evs = [t.get('expected_profit', 0) for t in trades if t.get('expected_profit')]
scores = [t.get('claude_score', 0) for t in trades if t.get('claude_score')]

if edges:
    print(f"\n[EDGE/EV STATS]")
    print(f"  Avg edge: {sum(edges)/len(edges):.3f}")
    print(f"  Max edge: {max(edges):.3f}")
    print(f"  Min edge: {min(edges):.3f}")
    print(f"  Avg EV: ${sum(evs)/len(evs):.2f}")
    print(f"  Max EV: ${max(evs):.2f}")
    print(f"  Avg score: {sum(scores)/len(scores):.3f}")

# Pending trades - what to expect
print(f"\n[PENDING TRADES - {len(pending_list)} awaiting resolution]")
for t in pending_list:
    q = str(t.get('market_question', ''))[:55]
    edge = t.get('edge', 0)
    ev = t.get('expected_profit', 0)
    side = t.get('side', '?')
    mp = t.get('market_price', 0)
    print(f"  ID={t['id']}: {q}")
    print(f"    Side={side} | Price={mp} | Edge={edge:.3f} | EV=${ev:.2f}")

# Improvement suggestions
print(f"\n{'=' * 70}")
print(f"[IMPROVEMENT SUGGESTIONS]")
print(f"  (analysis below based on current data)")