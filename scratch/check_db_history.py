#!/usr/bin/env python3
"""Check database history and profit data."""
import sqlite3
import os

# Check sqlite_sequence for historical counts
con = sqlite3.connect("trades.db")
con.row_factory = sqlite3.Row

try:
    rows = con.execute("SELECT * FROM sqlite_sequence").fetchall()
    print("sqlite_sequence (auto-increment counters):")
    for r in rows:
        name = r["name"]
        seq = r["seq"]
        print(f"  {name}: last seq = {seq}")
except Exception as e:
    print(f"No sqlite_sequence: {e}")

con.close()

# Check bot.db
print("\n--- bot.db ---")
if os.path.exists("bot.db"):
    con2 = sqlite3.connect("bot.db")
    con2.row_factory = sqlite3.Row
    try:
        tables = con2.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        for t in tables:
            name = t["name"]
            cnt = con2.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]
            print(f"  {name}: {cnt} rows")
            if cnt > 0 and name != "sqlite_sequence":
                schema = con2.execute(f"PRAGMA table_info([{name}])").fetchall()
                cols = [r["name"] for r in schema]
                print(f"    Columns: {cols}")
                sample = con2.execute(f"SELECT * FROM [{name}] LIMIT 3").fetchall()
                for s in sample:
                    print(f"    Sample: {dict(s)}")
    except Exception as e:
        print(f"  Error: {e}")
    con2.close()
else:
    print("  bot.db not found")

# Check db file sizes
print("\n--- DB file sizes ---")
for ext in ["", "-wal", "-shm"]:
    for name in ["trades.db", "bot.db"]:
        p = name + ext
        if os.path.exists(p):
            print(f"  {p}: {os.path.getsize(p)} bytes")