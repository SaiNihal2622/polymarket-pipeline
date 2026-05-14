import sqlite3
from pathlib import Path

for db_name in ["trades.db", "bot.db"]:
    p = Path(db_name)
    if not p.exists():
        print(f"{db_name}: NOT FOUND")
        continue
    conn = sqlite3.connect(db_name)
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print(f"\n{db_name}: {tables}")
    for t in tables:
        cnt = conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
        print(f"  {t}: {cnt} rows")
    conn.close()