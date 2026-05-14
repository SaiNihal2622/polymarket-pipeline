#!/usr/bin/env python3
"""Check all local .db files for trade data."""
import sqlite3
from pathlib import Path

project = Path(__file__).parent.parent
for db_file in sorted(project.glob("*.db")):
    conn = sqlite3.connect(str(db_file))
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    total = 0
    details = []
    for t in tables:
        cnt = conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
        total += cnt
        if cnt > 0:
            details.append(f"  {t}: {cnt} rows")
    print(f"\n{db_file.name} ({db_file.stat().st_size/1024:.1f} KB) — {len(tables)} tables, {total} total rows")
    for d in details:
        print(d)
    conn.close()

# Also check /data/trades.db if exists
data_db = Path("/data/trades.db")
if data_db.exists():
    print(f"\n/data/trades.db exists ({data_db.stat().st_size/1024:.1f} KB)")
else:
    print("\n/data/trades.db does not exist locally (expected — it's on Railway)")