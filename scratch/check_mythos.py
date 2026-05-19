#!/usr/bin/env python3
"""Check Mythos trades and all recent trades for early-loss issues."""
import sqlite3
import os

db_path = "trades.db"
if not os.path.exists(db_path):
    db_path = "/data/trades.db"

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Check trade columns first
cols = [c[1] for c in conn.execute("PRAGMA table_info(trades)").fetchall()]
print("Trade columns:", cols)

print("\n=== MYTHOS TRADES ===")
rows = conn.execute("SELECT * FROM trades WHERE LOWER(market_question) LIKE '%mythos%' ORDER BY id").fetchall()
for r in rows:
    d = dict(r)
    print(f"  #{d['id']} | {d['market_question'][:60]} | side={d['side']} | price={d.get('market_price','?')} | edge={d.get('edge','?')} | status={d['status']}")
    print(f"    created: {d.get('created_at','?')} | token: {str(d.get('token_id',''))[:20]}")

    # Check outcomes
    o = conn.execute("SELECT * FROM outcomes WHERE trade_id=?", (r["id"],)).fetchone()
    if o:
        od = dict(o)
        print(f"    OUTCOME: result={od.get('result')} | pnl={od.get('pnl')} | resolved={od.get('resolved_at')}")
    else:
        print(f"    NO OUTCOME YET")

print("\n=== ALL RESOLVED TRADES WITH EARLY LOSS (resolved < 48h after creation) ===")
early = conn.execute("""
    SELECT t.id, t.market_question, t.side, t.market_price, t.edge, t.amount_usd,
           t.created_at, o.resolved_at, o.result, o.pnl,
           CAST((julianday(o.resolved_at) - julianday(t.created_at)) * 24 AS REAL) as hours_to_resolve
    FROM trades t
    JOIN outcomes o ON t.id = o.trade_id
    WHERE o.result = 'loss'
    ORDER BY hours_to_resolve ASC
    LIMIT 20
""").fetchall()
for r in early:
    d = dict(r)
    print(f"  #{d['id']} | {d['hours_to_resolve']:.1f}h | {d['market_question'][:50]} | side={d['side']} price={d['market_price']} | pnl={d['pnl']}")

print("\n=== TRADES WITH NO END DATE STORED ===")
no_end = conn.execute("""
    SELECT id, market_question, end_date_iso
    FROM trades 
    WHERE (end_date_iso IS NULL OR end_date_iso = '')
    ORDER BY id DESC
    LIMIT 10
""").fetchall()
print(f"  {len(no_end)} trades missing end dates")

print("\n=== RECENT TRADES (last 20) ===")
recent = conn.execute("SELECT id, market_question, side, market_price, edge, status, amount_usd, created_at FROM trades ORDER BY id DESC LIMIT 20").fetchall()
for r in recent:
    d = dict(r)
    print(f"  #{d['id']} | {d['market_question'][:55]} | {d['side']} @ {d.get('market_price','?')} | edge={d.get('edge','?')} | ${d['amount_usd']} | {d['status']}")

print("\n=== OVERALL STATS ===")
stats = conn.execute("""
    SELECT 
        COUNT(*) as total,
        SUM(CASE WHEN status='demo' THEN 1 ELSE 0 END) as demo,
        SUM(CASE WHEN status='dry_run' THEN 1 ELSE 0 END) as dry_run,
        SUM(CASE WHEN status='executed' THEN 1 ELSE 0 END) as live,
        SUM(CASE WHEN status='voided' THEN 1 ELSE 0 END) as voided
    FROM trades
""").fetchone()
print(f"  Total: {stats['total']} | demo: {stats['demo']} | dry_run: {stats['dry_run']} | live: {stats['live']} | voided: {stats['voided']}")

outcome_stats = conn.execute("""
    SELECT 
        COUNT(*) as resolved,
        SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins,
        SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) as losses,
        SUM(CASE WHEN result='push' THEN 1 ELSE 0 END) as pushes,
        SUM(pnl) as total_pnl
    FROM outcomes
""").fetchone()
print(f"  Resolved: {outcome_stats['resolved']} | Wins: {outcome_stats['wins']} | Losses: {outcome_stats['losses']} | PnL: {outcome_stats['total_pnl']}")

conn.close()