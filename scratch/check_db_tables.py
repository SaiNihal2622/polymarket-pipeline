#!/usr/bin/env python3
"""Check what tables exist in trades.db and row counts."""
import sqlite3, os

db = "trades.db"
print(f"DB exists: {os.path.exists(db)}")
print(f"DB size: {os.path.getsize(db) if os.path.exists(db) else 0} bytes")

con = sqlite3.connect(db)
tables = con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print(f"\nTables: {[t[0] for t in tables]}")

for t in tables:
    name = t[0]
    count = con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
    print(f"  {name}: {count} rows")
    if count > 0 and count < 5:
        cols = [d[1] for d in con.execute(f"PRAGMA table_info({name})").fetchall()]
        print(f"    Columns: {cols}")

con.close()