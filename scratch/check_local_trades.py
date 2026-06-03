#!/usr/bin/env python3
"""Check local trades.db for trade data and resolution status."""
import sqlite3
import json
import urllib.request

DB = "trades.db"
GAMMA = "https://gamma-api.polymarket.com"

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row

# Check tables
tables = con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("Tables:", [t["name"] for t in tables])

# Check trades
try:
    rows = con.execute("SELECT * FROM trades ORDER BY id DESC LIMIT 10").fetchall()
    print(f"\n=== TRADES ({len(rows)} recent) ===")
    for r in rows:
        print(f'#{r["id"]} | {r["market_question"][:60]} | side={r["side"]} | entry={r.get("entry_price", r.get("market_price","?"))} | status={r["status"]}')
        print(f'   market_id={r["market_id"]} | token_id={str(r.get("token_id",""))[:30]}... | end={r.get("end_date_iso","")}')
except Exception as e:
    print(f"trades table error: {e}")

# Check outcomes
try:
    rows = con.execute("SELECT * FROM outcomes ORDER BY id DESC LIMIT 10").fetchall()
    print(f"\n=== OUTCOMES ({len(rows)} recent) ===")
    for r in rows:
        print(f'outcome #{r["trade_id"]} | result={r["result"]} | pnl={r.get("pnl",0)} | method={r.get("method","")}')
except Exception as e:
    print(f"outcomes table error: {e}")

# Check demo_trades
try:
    rows = con.execute("SELECT * FROM demo_trades ORDER BY id DESC LIMIT 10").fetchall()
    print(f"\n=== DEMO TRADES ({len(rows)} recent) ===")
    for r in rows:
        print(f'demo #{r["id"]} | {r["market_question"][:60]} | result={r.get("result","?")} | entry={r.get("entry_price","?")} | side={r.get("side","?")}')
except Exception as e:
    print(f"demo_trades table error: {e}")

con.close()