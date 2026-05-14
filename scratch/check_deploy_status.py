import json, urllib.request

url = "https://demo-runner-production-3f90.up.railway.app/api/trades"
resp = urllib.request.urlopen(url, timeout=15)
trades = json.loads(resp.read())

print(f"Total trades in DB: {len(trades)}")
pending = [t for t in trades if t.get('result') in (None, 'PENDING', 'pending')]
resolved = [t for t in trades if t.get('result') in ('WIN', 'LOSS', 'win', 'loss')]
wins = [t for t in resolved if t['result'].upper() == 'WIN']
losses = [t for t in resolved if t['result'].upper() == 'LOSS']
print(f"Pending: {len(pending)}, Resolved: {len(resolved)} (Wins: {len(wins)}, Losses: {len(losses)})")
if resolved:
    print(f"Accuracy: {len(wins)/len(resolved)*100:.1f}%")
print()
for t in trades:
    q = str(t.get('market_question', ''))[:55]
    side = t.get('side', '?')
    score = t.get('claude_score', '?')
    edge = t.get('edge', '?')
    ev = t.get('expected_profit', '?')
    status = t.get('status', '?')
    result = t.get('result', 'pending')
    print(f"ID={t['id']}: {q} | {side} | score={score} | edge={edge} | ev={ev} | status={status} | result={result}")

# Now get summary
url2 = "https://demo-runner-production-3f90.up.railway.app/api/summary"
resp2 = urllib.request.urlopen(url2, timeout=15)
summary = json.loads(resp2.read())
s = summary['summary']
print(f"\n=== SUMMARY ===")
print(f"Total trades: {s['total_trades']}")
print(f"Resolved: {s['resolved']}")
print(f"Pending: {s['pending']}")
print(f"Accuracy: {s['accuracy_pct']}%")
print(f"Bankroll: ${s['bankroll']}")
print(f"PnL today: ${s['todays_pnl']}")
print(f"Total PnL: ${s['total_pnl']}")
print(f"Go-live remaining: {s['go_live_remaining']} trades")
print(f"Trade allowed: {s['trades_today_allowed']}")
print(f"Block reason: {s['trade_block_reason']}")

# Projection
print(f"\n=== 24H PROJECTION (based on scan_interval=5min) ===")
scans_per_24h = 24 * 60 / 5
print(f"Scans per 24h: {scans_per_24h:.0f}")
# Historical trade rate
if len(trades) > 0:
    trades_per_scan = len(trades) / max(s['total_trades'], 1)
    # Estimate: ~0.5-2 trades per scan based on current pipeline
    # With 7 pending out of 9 total, we know ~1.5 trades/scan is happening
    print(f"Current rate: {len(trades)} total trades so far")
    print(f"Resolved so far: {s['resolved']} (need 18 more for go-live)")
    print(f"If current pace: ~{s['resolved']} resolved in ~{s['total_trades']} total")
    if s['resolved'] > 0:
        win_rate = s['wins'] / s['resolved']
        avg_edge = 0.15  # minimum edge threshold
        avg_bet = 1.0  # max_bet_usd
        est_trades_24h = scans_per_24h * 0.3  # conservative: 30% of scans produce a trade
        est_resolved_24h = est_trades_24h * 0.5  # about half resolve within 24h
        est_ev_per_trade = avg_edge * avg_bet
        est_pnl_24h = est_resolved_24h * (win_rate - (1 - win_rate)) * avg_edge * avg_bet
        print(f"\nEstimated 24h trades: ~{est_trades_24h:.0f} new positions")
        print(f"Estimated 24h resolved: ~{est_resolved_24h:.0f}")
        print(f"Estimated 24h PnL: ${est_pnl_24h:.2f}")
    else:
        print("\nNot enough resolved trades to project accurately.")
        print("Still in dry-run learning phase (need 18 more resolved for go-live)")
        est_trades_24h = scans_per_24h * 0.3
        print(f"Estimated 24h new trades: ~{est_trades_24h:.0f}")
        print(f"Estimated accuracy: 55-65% (calibrator baseline)")
        print(f"Estimated PnL at $1 bet: ${est_trades_24h * 0.55 * 0.15:.2f} (conservative)")