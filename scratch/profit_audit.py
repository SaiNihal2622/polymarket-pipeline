#!/usr/bin/env python3
"""Audit all databases for profit data."""
import sqlite3, os, json

DBS = ['trades.db', 'bot.db']
for db in DBS:
    if not os.path.exists(db):
        print(f"[SKIP] {db} not found")
        continue
    
    print(f"\n{'='*80}")
    print(f"DATABASE: {db} ({os.path.getsize(db)/1024:.1f} KB)")
    print('='*80)
    
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print(f"Tables: {tables}")
    
    for tbl in tables:
        n = con.execute(f"SELECT COUNT(*) FROM [{tbl}]").fetchone()[0]
        if n == 0:
            print(f"\n  [{tbl}] EMPTY")
            continue
            
        cols = [c[1] for c in con.execute(f"PRAGMA table_info([{tbl}])").fetchall()]
        print(f"\n  [{tbl}] {n} rows | Columns: {cols}")
        
        # Show first 3 rows
        rows = con.execute(f"SELECT * FROM [{tbl}] LIMIT 3").fetchall()
        for r in rows:
            print(f"    {dict(r)}")
    
    con.close()

# Also check scratch/live_trades.json
if os.path.exists('scratch/live_trades.json'):
    print(f"\n{'='*80}")
    print("scratch/live_trades.json")
    print('='*80)
    with open('scratch/live_trades.json') as f:
        data = json.load(f)
    if isinstance(data, list):
        print(f"  {len(data)} trades")
        for t in data[:3]:
            print(f"    {t}")
    elif isinstance(data, dict):
        print(f"  Keys: {list(data.keys())}")
        print(json.dumps(data, indent=2, default=str)[:2000])