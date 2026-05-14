#!/usr/bin/env python3
"""Dump all table schemas and row counts from trades.db."""
import sqlite3
from pathlib import Path

DB = Path(__file__).parent.parent / "trades.db"
conn = sqlite3.connect(str(DB))

tables = [r[0] for r in conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
).fetchall()]

for t in tables:
    cnt = conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
    cols = conn.execute(f"PRAGMA table_info([{t}])").fetchall()
    col_names = [c[1] for c in cols]
    print(f"\n=== {t} ({cnt} rows) ===")
    print(f"  Columns: {col_names}")

conn.close()