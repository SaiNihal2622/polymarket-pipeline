#!/usr/bin/env python3
import sqlite3
from pathlib import Path

db = Path(__file__).parent / "trades.db"
conn = sqlite3.connect(db)
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print("Tables:", tables)

for t in tables:
    cur.execute(f"SELECT COUNT(*) FROM {t}")
    count = cur.fetchone()[0]
    print(f"  {t}: {count} rows")

conn.close()
