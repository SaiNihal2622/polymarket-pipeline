#!/usr/bin/env python3
"""Quick DB audit for Polymarket pipeline."""
import sqlite3
from pathlib import Path

db = Path(__file__).parent / "trades.db"
conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("SELECT COUNT(*) as c FROM trades")
trades = cur.fetchone()["c"]

cur.execute("SELECT COUNT(*) as c FROM outcomes")
outcomes = cur.fetchone()["c"]

cur.execute("SELECT COUNT(*) as c FROM trades WHERE status='voided'")
voided = cur.fetchone()["c"]

cur.execute("SELECT COUNT(*) as c FROM trades WHERE status IN ('demo','dry_run')")
demo = cur.fetchone()["c"]

cur.execute("""
    SELECT COUNT(*) as c FROM trades t
    JOIN outcomes o ON t.id = o.trade_id
    WHERE t.status IN ('demo','dry_run')
""")
resolved = cur.fetchone()["c"]

cur.execute("""
    SELECT t.id, t.strategy, o.result, o.pnl
    FROM trades t
    JOIN outcomes o ON t.id = o.trade_id
    WHERE t.status IN ('demo','dry_run')
    ORDER BY t.id DESC
    LIMIT 10
""")
recent = cur.fetchall()

print(f"DB: {db}")
print(f"Total trades: {trades}")
print(f"Demo/dry_run trades: {demo}")
print(f"Outcomes: {outcomes}")
print(f"Voided trades: {voided}")
print(f"Resolved demo trades: {resolved}")
print(f"\nLast 10 resolved trades:")
for r in recent:
    print(f"  #{r['id']} {r['strategy']} -> {r['result']} ${r['pnl']:+.2f}")

conn.close()
