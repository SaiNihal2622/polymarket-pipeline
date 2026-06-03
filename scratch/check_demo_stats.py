#!/usr/bin/env python3
"""Check demo trade accuracy stats."""
import sqlite3

con = sqlite3.connect("trades.db")
con.row_factory = sqlite3.Row

# Result breakdown
rows = con.execute("SELECT result, COUNT(*) as cnt FROM demo_trades GROUP BY result").fetchall()
print("=== DEMO TRADE RESULTS ===")
for r in rows:
    print(f"  {r['result']}: {r['cnt']}")

# Wins/Losses accuracy
r2 = con.execute("""
    SELECT COUNT(*) as total,
           SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins,
           SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) as losses,
           SUM(CASE WHEN result='push' THEN 1 ELSE 0 END) as pushes,
           SUM(pnl) as total_pnl
    FROM demo_trades
    WHERE result IN ('win','loss','push')
""").fetchone()

total = r2['total'] or 0
wins = r2['wins'] or 0
losses = r2['losses'] or 0
pushes = r2['pushes'] or 0
pnl = r2['total_pnl'] or 0.0

print(f"\n=== ACCURACY ===")
print(f"Total resolved: {total}")
print(f"Wins: {wins}")
print(f"Losses: {losses}")
print(f"Pushes: {pushes}")
if (wins + losses) > 0:
    print(f"Accuracy: {wins/(wins+losses)*100:.1f}%")
print(f"Total virtual PnL: ${pnl:.2f}")

# Strategy breakdown
print(f"\n=== BY STRATEGY ===")
strats = con.execute("""
    SELECT strategy,
           COUNT(*) as total,
           SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins,
           SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) as losses,
           SUM(pnl) as pnl
    FROM demo_trades
    WHERE result IN ('win','loss')
    GROUP BY strategy
    ORDER BY wins - losses DESC
""").fetchall()
for s in strats:
    w = s['wins'] or 0
    l = s['losses'] or 0
    acc = w/(w+l)*100 if (w+l) > 0 else 0
    print(f"  {s['strategy']}: {w}W/{l}L ({acc:.0f}%) PnL=${s['pnl']:.2f}")

# Recent trades
print(f"\n=== LAST 10 RESOLVED ===")
recent = con.execute("""
    SELECT id, market_question, side, entry_price, bet_amount, result, pnl, strategy, created_at
    FROM demo_trades
    WHERE result IN ('win','loss')
    ORDER BY resolved_at DESC
    LIMIT 10
""").fetchall()
for t in recent:
    sym = "WIN" if t['result'] == 'win' else "LOSS"
    print(f"  #{t['id']} [{sym}] {t['side']} ${t['bet_amount']:.2f} @ {t['entry_price']:.2f} | {t['market_question'][:50]} | {t['strategy']} | PnL=${t['pnl']:.2f}")

con.close()