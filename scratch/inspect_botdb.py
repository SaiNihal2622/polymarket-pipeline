#!/usr/bin/env python3
"""Inspect local bot.db for recent demo_trades and resolution status."""
import sqlite3
from pathlib import Path
import os

DB_PATH = os.getenv("DB_PATH", str(Path(__file__).resolve().parent.parent / "bot.db"))
print(f"DB_PATH: {DB_PATH}")
print(f"Exists: {Path(DB_PATH).exists()}")

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print(f"Tables: {tables}")

if 'demo_trades' in tables:
    rows = conn.execute("SELECT id, market_question, side, entry_price, bet_amount, result, pnl, market_outcome, market_id, created_at FROM demo_trades ORDER BY id DESC LIMIT 20").fetchall()
    print(f"\nRecent demo_trades ({len(rows)}):")
    for r in rows:
        print(f"  #{r['id']} | result={r['result']} | {str(r['market_question'])[:70]} | side={r['side']} entry={r['entry_price']} pnl={r['pnl']} outcome={r['market_outcome']} cid={str(r['market_id'])[:40]}")

if 'trades' in tables:
    rows = conn.execute("SELECT id, market_question, side, entry_price, bet_amount, result, pnl, market_outcome, market_id, created_at FROM trades ORDER BY id DESC LIMIT 20").fetchall()
    print(f"\nRecent trades ({len(rows)}):")
    for r in rows:
        print(f"  #{r['id']} | result={r['result']} | {str(r['market_question'])[:70]} | side={r['side']} entry={r['entry_price']} pnl={r['pnl']} outcome={r['market_outcome']} cid={str(r['market_id'])[:40]}")

conn.close()