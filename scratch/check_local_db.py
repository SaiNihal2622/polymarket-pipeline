#!/usr/bin/env python3
"""Check local DB for trades and resolution status."""
import sqlite3
import json
import sys
sys.path.insert(0, ".")
from logger import DB_PATH

print(f"DB_PATH: {DB_PATH}")
print(f"EXISTS: {DB_PATH.exists()}")

conn = sqlite3.connect(str(DB_PATH))
conn.row_factory = sqlite3.Row

# Check tables
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print(f"Tables: {[t[0] for t in tables]}")

# Check trades table
try:
    rows = conn.execute("SELECT * FROM trades ORDER BY id DESC LIMIT 10").fetchall()
    print(f"\ntrades table: {len(rows)} rows")
    for r in rows:
        d = dict(r)
        print(f"  #{d['id']} | market={d.get('market_question','')[:60]} | side={d.get('side')} | status={d.get('status')} | result={d.get('result','pending')}")
except Exception as e:
    print(f"trades error: {e}")

# Check demo_trades table
try:
    rows2 = conn.execute("SELECT * FROM demo_trades ORDER BY id DESC LIMIT 10").fetchall()
    print(f"\ndemo_trades table: {len(rows2)} rows")
    for r in rows2:
        d = dict(r)
        print(f"  #{d['id']} | market={d.get('market_question','')[:60]} | side={d.get('side')} | result={d.get('result','pending')} | slug={d.get('market_slug','')[:50]}")
        print(f"    token_id={d.get('token_id','')[:50]} | created={d.get('created_at')} | resolved={d.get('resolved_at')}")
except Exception as e:
    print(f"demo_trades error: {e}")

# Check outcomes
try:
    rows3 = conn.execute("SELECT * FROM outcomes ORDER BY id DESC LIMIT 10").fetchall()
    print(f"\noutcomes table: {len(rows3)} rows")
    for r in rows3:
        d = dict(r)
        print(f"  trade_id={d.get('trade_id')} | result={d.get('result')} | pnl={d.get('pnl')} | resolved={d.get('resolved_at')}")
except Exception as e:
    print(f"outcomes error: {e}")

# Check recent trades with resolution info
try:
    rows4 = conn.execute("""
        SELECT d.id, d.market_question, d.market_slug, d.token_id, d.side, 
               d.entry_price, d.bet_amount, d.result, d.pnl, d.created_at, d.resolved_at,
               d.market_id
        FROM demo_trades d
        ORDER BY d.id DESC LIMIT 10
    """).fetchall()
    print(f"\n=== RECENT DEMO_TRADES (with details) ===")
    for r in rows4:
        d = dict(r)
        print(f"\n  Trade #{d['id']}:")
        print(f"    Question: {d['market_question'][:80]}")
        print(f"    Slug: {d.get('market_slug','')}")
        print(f"    Market ID: {d.get('market_id','')}")
        print(f"    Token ID: {d.get('token_id','')}")
        print(f"    Side: {d['side']} | Price: {d['entry_price']} | Bet: ${d['bet_amount']}")
        print(f"    Result: {d['result']} | PnL: {d.get('pnl',0)}")
        print(f"    Created: {d['created_at']} | Resolved: {d.get('resolved_at')}")
except Exception as e:
    print(f"detailed trades error: {e}")

conn.close()