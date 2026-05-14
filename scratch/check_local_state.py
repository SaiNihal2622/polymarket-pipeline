#!/usr/bin/env python3
import sqlite3, os, sys
from pathlib import Path

db_path = Path(__file__).parent.parent / "trades.db"
print(f"DB path: {db_path}")
print(f"Exists: {db_path.exists()}")

if db_path.exists():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print("Tables:", tables)
    
    for t in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t}: {count} rows")
    
    # Latest trades
    try:
        rows = conn.execute("SELECT id, market_question, side, status, edge, created_at FROM trades ORDER BY id DESC LIMIT 10").fetchall()
        print("\n--- Latest trades ---")
        for r in rows:
            print(f"  #{r['id']} | {r['market_question'][:50]} | side={r['side']} | status={r['status']} | edge={r['edge']} | {r['created_at']}")
    except Exception as e:
        print(f"Error reading trades: {e}")
    
    # Latest outcomes
    try:
        rows = conn.execute("SELECT * FROM outcomes ORDER BY id DESC LIMIT 10").fetchall()
        print("\n--- Latest outcomes ---")
        for r in rows:
            print(f"  {dict(r)}")
    except Exception as e:
        print(f"Error reading outcomes: {e}")
    
    conn.close()
else:
    # Try bot.db
    bot_db = Path(__file__).parent.parent / "bot.db"
    print(f"Trying bot.db: {bot_db}, exists: {bot_db.exists()}")
    if bot_db.exists():
        conn = sqlite3.connect(bot_db)
        conn.row_factory = sqlite3.Row
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        print("Tables:", tables)
        conn.close()