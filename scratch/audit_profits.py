"""Full profit audit of the polymarket pipeline."""
import sqlite3, os, json
from datetime import datetime, timezone

DB = "bot.db"
print(f"Database: {DB} | Size: {os.path.getsize(DB)} bytes")

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row

# 1. List all tables
tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print(f"\nTables ({len(tables)}): {tables}")

if not tables:
    print("\n*** DATABASE IS EMPTY - no trades recorded yet ***")
    con.close()
    exit()

# 2. For each table, show schema + row count
for t in tables:
    cols = [r[1] for r in con.execute(f"PRAGMA table_info({t})").fetchall()]
    cnt = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"\n  {t}: {cnt} rows | columns: {cols}")

# 3. Look for trade-related tables
trade_tables = [t for t in tables if 'trade' in t.lower() or 'position' in t.lower() or 'order' in t.lower() or 'bet' in t.lower()]
print(f"\nTrade-related tables: {trade_tables}")

# 4. Deep dive into each trade table
for tt in trade_tables:
    print(f"\n{'='*60}")
    print(f"TABLE: {tt}")
    print(f"{'='*60}")
    cols = [r[1] for r in con.execute(f"PRAGMA table_info({tt})").fetchall()]
    rows = con.execute(f"SELECT * FROM {tt} ORDER BY rowid DESC LIMIT 50").fetchall()
    print(f"Columns: {cols}")
    print(f"Total rows: {con.execute(f'SELECT COUNT(*) FROM {tt}').fetchone()[0]}")
    
    for r in rows:
        print(dict(r))

# 5. Check for profit/PnL columns across all tables
print(f"\n{'='*60}")
print("PROFIT/PNL ANALYSIS")
print(f"{'='*60}")

for t in tables:
    cols = [r[1].lower() for r in con.execute(f"PRAGMA table_info({t})").fetchall()]
    profit_cols = [c for c in cols if any(k in c for k in ['profit', 'pnl', 'p&l', 'return', 'outcome', 'won', 'lost', 'resolved', 'status', 'net'])]
    if profit_cols:
        print(f"\n  {t} has profit-relevant columns: {profit_cols}")
        for pc in profit_cols:
            vals = con.execute(f"SELECT DISTINCT [{pc}] FROM {t} LIMIT 20").fetchall()
            print(f"    {pc} values: {[v[0] for v in vals]}")

# 6. Look at resolve_trades.py for how profits are calculated
con.close()
print("\n\nDone. Check resolve_trades.py and db_tables.py for schema details.")