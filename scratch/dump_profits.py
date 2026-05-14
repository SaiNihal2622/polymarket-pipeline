"""
Run this on Railway via: railway run python scratch/dump_profits.py
Or access the DB directly if SSH works.
"""
import sqlite3
import os
import json

db_path = "/data/bot.db"
if not os.path.exists(db_path):
    print(f"ERROR: {db_path} not found")
    exit(1)

conn = sqlite3.connect(db_path)

# Get all tables
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("=== TABLES ===")
for t in tables:
    cnt = conn.execute(f"SELECT COUNT(*) FROM [{t[0]}]").fetchone()[0]
    print(f"  {t[0]}: {cnt} rows")

# Find the trades table
trade_tables = [t[0] for t in tables if 'trade' in t[0].lower() or 'demo' in t[0].lower()]
print(f"\nTrade-related tables: {trade_tables}")

for tt in trade_tables:
    print(f"\n=== SCHEMA: {tt} ===")
    cols = conn.execute(f"PRAGMA table_info([{tt}])").fetchall()
    for c in cols:
        print(f"  {c[1]} ({c[2]})")
    
    print(f"\n=== STATS: {tt} ===")
    total = conn.execute(f"SELECT COUNT(*) FROM [{tt}]").fetchone()[0]
    print(f"Total: {total}")
    
    # Try to find result/status column
    col_names = [c[1] for c in cols]
    
    # Check for result column
    result_col = None
    for candidate in ['result', 'status', 'outcome', 'resolution']:
        if candidate in col_names:
            result_col = candidate
            break
    
    if result_col:
        print(f"\n=== {result_col.upper()} DISTRIBUTION ===")
        dist = conn.execute(f"SELECT [{result_col}], COUNT(*) FROM [{tt}] GROUP BY [{result_col}]").fetchall()
        for d in dist:
            print(f"  {d[0]}: {d[1]}")
    
    # Check for PnL column
    pnl_col = None
    for candidate in ['pnl', 'profit', 'profit_loss', 'net_pnl', 'gain']:
        if candidate in col_names:
            pnl_col = candidate
            break
    
    if pnl_col:
        total_pnl = conn.execute(f"SELECT SUM([{pnl_col}]) FROM [{tt}] WHERE [{pnl_col}] IS NOT NULL").fetchone()[0]
        print(f"\nTotal {pnl_col}: ${total_pnl or 0:+.2f}")
    
    # Show sample rows
    print(f"\n=== SAMPLE ROWS: {tt} (last 10) ===")
    rows = conn.execute(f"SELECT * FROM [{tt}] ORDER BY rowid DESC LIMIT 10").fetchall()
    for r in rows:
        print(r)

# Also check all tables for any that might contain financial data
print("\n=== ALL TABLES OVERVIEW ===")
for t in tables:
    tname = t[0]
    cols = conn.execute(f"PRAGMA table_info([{tname}])").fetchall()
    col_names = [c[1] for c in cols]
    cnt = conn.execute(f"SELECT COUNT(*) FROM [{tname}]").fetchone()[0]
    # Check for interesting columns
    financial = [c for c in col_names if any(k in c.lower() for k in ['pnl', 'profit', 'amount', 'bet', 'price', 'result', 'outcome', 'win', 'loss'])]
    if financial or 'trade' in tname.lower():
        print(f"\n  {tname} ({cnt} rows)")
        print(f"    Columns: {col_names}")
        if financial:
            print(f"    Financial columns: {financial}")

conn.close()
print("\n=== DONE ===")