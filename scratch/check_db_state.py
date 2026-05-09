#!/usr/bin/env python3
"""Check current DB state."""
import sqlite3, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pathlib import Path

DB = Path(__file__).parent.parent / "trades.db"
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

print("=== TRADE STATUS ===")
for r in conn.execute("SELECT status, count(*) as c FROM trades GROUP BY status").fetchall():
    print(f"  {r['status']}: {r['c']}")

print("\n=== OUTCOMES ===")
for r in conn.execute("SELECT o.result, count(*) as c, round(sum(o.pnl),2) as pnl FROM outcomes o GROUP BY o.result").fetchall():
    print(f"  {r['result']}: {r['c']} trades, PnL=${r['pnl']}")

print("\n=== ACCURACY ===")
r = conn.execute("""
    SELECT sum(case when result='win' then 1 else 0 end) as w,
           sum(case when result='loss' then 1 else 0 end) as l,
           count(*) as t
    FROM outcomes WHERE result IN ('win','loss')
""").fetchone()
w, l, t = r['w'] or 0, r['l'] or 0, r['t'] or 0
print(f"  {w}W/{l}L = {w/t*100:.1f}% accuracy" if t > 0 else "  No resolved trades")

print("\n=== PENDING (unresolved, not voided) ===")
r2 = conn.execute("""
    SELECT count(*) as c FROM trades t
    LEFT JOIN outcomes o ON t.id = o.trade_id
    WHERE t.status IN ('demo','dry_run') AND o.id IS NULL AND t.market_id != ''
""").fetchone()
print(f"  {r2['c']} pending trades")

print("\n=== RECENT TRADES (last 10) ===")
for r in conn.execute("""
    SELECT t.id, substr(t.market_question,1,60) as q, t.side, t.status, o.result, o.pnl
    FROM trades t LEFT JOIN outcomes o ON t.id = o.trade_id
    ORDER BY t.id DESC LIMIT 10
""").fetchall():
    res = r['result'] or 'pending'
    pnl = f"${r['pnl']:+.2f}" if r['pnl'] else ''
    print(f"  #{r['id']:3d} | {r['side']:3s} | {res:7s} {pnl:>8s} | {r['q']}")

print("\n=== STRATEGY BREAKDOWN ===")
for r in conn.execute("""
    SELECT coalesce(t.strategy,'baseline') as s,
           count(*) as t,
           sum(case when o.result='win' then 1 else 0 end) as w,
           sum(case when o.result='loss' then 1 else 0 end) as l
    FROM trades t JOIN outcomes o ON t.id=o.trade_id
    WHERE t.status IN ('demo','dry_run') AND o.result IN ('win','loss')
    GROUP BY s ORDER BY w*1.0/max(1,w+l) DESC
""").fetchall():
    w, l = r['w'] or 0, r['l'] or 0
    acc = w/(w+l)*100 if (w+l) > 0 else 0
    print(f"  {r['s']:15s}: {w}W/{l}L = {acc:.1f}% ({r['t']} trades)")

conn.close()