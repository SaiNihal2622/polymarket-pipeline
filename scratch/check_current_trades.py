#!/usr/bin/env python3
"""Quick check of all trades in the local DB."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logger import DB_PATH
import sqlite3

print(f"DB_PATH: {DB_PATH}")

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

# List tables
tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print(f"TABLES: {tables}")

# Check if outcomes table exists
has_outcomes = "outcomes" in tables

# Get all trades
rows = conn.execute("SELECT * FROM trades ORDER BY id DESC LIMIT 10").fetchall()
print(f"\n=== TRADES ({len(rows)} rows) ===")
for r in rows:
    d = dict(r)
    print(f"\n#{d.get('id')} | status={d.get('status')} | side={d.get('side')}")
    print(f"  market_question: {d.get('market_question','')[:80]}")
    print(f"  market_id: {d.get('market_id','')[:60]}")
    print(f"  result: {d.get('result')} | pnl: {d.get('pnl')} | market_outcome: {d.get('market_outcome')}")
    print(f"  created: {d.get('created_at')} | resolved: {d.get('resolved_at')}")
    print(f"  close_time: {d.get('close_time', 'N/A')}")

# Check outcomes table
if has_outcomes:
    ocols = [r[1] for r in conn.execute("PRAGMA table_info(outcomes)").fetchall()]
    print(f"\n=== OUTCOMES table columns: {ocols} ===")
    orows = conn.execute("SELECT * FROM outcomes ORDER BY id DESC LIMIT 10").fetchall()
    for r in orows:
        d = dict(r)
        print(f"  {d}")

# Also check demo_trades if exists
if "demo_trades" in tables:
    drows = conn.execute("SELECT id, market_question, side, result, pnl, market_outcome, resolved_at FROM demo_trades ORDER BY id DESC LIMIT 5").fetchall()
    print(f"\n=== DEMO_TRADES ({len(drows)} rows) ===")
    for r in drows:
        print(dict(r))

conn.close()