import sqlite3
conn = sqlite3.connect("bot.db")
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("Tables:", tables)
for (t,) in tables:
    if t.startswith("sqlite"):
        continue
    cnt = conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
    print(f"  {t}: {cnt} rows")
    cols = conn.execute(f"PRAGMA table_info([{t}])").fetchall()
    col_names = [c[1] for c in cols]
    print(f"    Columns: {col_names}")
    if cnt > 0:
        row = conn.execute(f"SELECT * FROM [{t}] LIMIT 1").fetchone()
        print(f"    Sample: {dict(zip(col_names, row))}")
conn.close()