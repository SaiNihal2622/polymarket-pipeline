import sqlite3
conn = sqlite3.connect("bot.db")
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("Tables:", [t[0] for t in tables])
for t in tables:
    cnt = conn.execute(f"SELECT COUNT(*) FROM [{t[0]}]").fetchone()[0]
    print(f"  {t[0]}: {cnt} rows")
# Check if demo_trades exists with different name
for t in tables:
    if "trade" in t[0].lower() or "demo" in t[0].lower():
        print(f"\n=== {t[0]} ===")
        cols = conn.execute(f"PRAGMA table_info([{t[0]}])").fetchall()
        print("Columns:", [c[1] for c in cols])
        rows = conn.execute(f"SELECT * FROM [{t[0]}] ORDER BY rowid DESC LIMIT 5").fetchall()
        for r in rows:
            print(r)
conn.close()