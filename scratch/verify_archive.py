#!/usr/bin/env python3
import sqlite3
conn = sqlite3.connect("/data/trades.db")
tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print(f"Tables: {tables}")
if "demo_trades" in tables:
    n = conn.execute("SELECT COUNT(*) FROM demo_trades").fetchone()[0]
    print(f"demo_trades: {n} rows")
if "demo_trades_archive" in tables:
    n = conn.execute("SELECT COUNT(*) FROM demo_trades_archive").fetchone()[0]
    print(f"demo_trades_archive: {n} rows")
conn.close()