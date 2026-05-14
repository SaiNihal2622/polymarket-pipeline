import sqlite3
import os

db_path = "/data/bot.db"
if not os.path.exists(db_path):
    print(f"ERROR: {db_path} not found. Trying bot.db...")
    db_path = "bot.db"

conn = sqlite3.connect(db_path)
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("=== TABLES ===")
for t in tables:
    cnt = conn.execute("SELECT COUNT(*) FROM " + t[0]).fetchone()[0]
    print(f"  {t[0]}: {cnt} rows")

trade_tables = [t[0] for t in tables if 'trade' in t[0].lower() or 'demo' in t[0].lower()]
print(f"\nTrade-related tables: {trade_tables}")

for tt in trade_tables:
    print(f"\n=== SCHEMA: {tt} ===")
    cols = conn.execute(f"PRAGMA table_info({tt})").fetchall()
    col_names = [c[1] for c in cols]
    for c in cols:
        print(f"  {c[1]} ({c[2]})")
    
    total = conn.execute(f"SELECT COUNT(*) FROM {tt}").fetchone()[0]
    print(f"\nTotal rows: {total}")
    
    for candidate in ['result', 'status', 'outcome']:
        if candidate in col_names:
            print(f"\n=== {candidate.upper()} DISTRIBUTION ===")
            dist = conn.execute(f"SELECT {candidate}, COUNT(*) FROM {tt} GROUP BY {candidate}").fetchall()
            for d in dist:
                print(f"  {d[0]}: {d[1]}")
    
    for candidate in ['pnl', 'profit', 'profit_loss', 'net_pnl']:
        if candidate in col_names:
            val = conn.execute(f"SELECT SUM({candidate}) FROM {tt} WHERE {candidate} IS NOT NULL").fetchone()[0]
            print(f"\nTotal {candidate}: ${val or 0:+.2f}")
    
    print(f"\n=== LAST 20 TRADES ===")
    rows = conn.execute(f"SELECT * FROM {tt} ORDER BY rowid DESC LIMIT 20").fetchall()
    for r in rows:
        print(r)

print("\n=== ALL TABLES WITH FINANCIAL COLUMNS ===")
for t in tables:
    tname = t[0]
    cols = conn.execute(f"PRAGMA table_info({tname})").fetchall()
    col_names = [c[1] for c in cols]
    cnt = conn.execute(f"SELECT COUNT(*) FROM {tname}").fetchone()[0]
    financial = [c for c in col_names if any(k in c.lower() for k in ['pnl', 'profit', 'amount', 'bet', 'price', 'result', 'outcome', 'win', 'loss'])]
    if financial or 'trade' in tname.lower():
        print(f"\n  {tname} ({cnt} rows)")
        print(f"    Columns: {col_names}")
        if financial:
            print(f"    Financial: {financial}")

conn.close()
print("\n=== DONE ===")