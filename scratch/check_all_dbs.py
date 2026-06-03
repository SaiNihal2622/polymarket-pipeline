#!/usr/bin/env python3
"""Check all .db files for trade data."""
import sqlite3, os

dbs = [
    "trades.db",
    "bot.db",
    ".claude/worktrees/serene-wu/trades.db",
]

for db_path in dbs:
    if not os.path.exists(db_path):
        print(f"\n{'='*60}")
        print(f"  {db_path} — NOT FOUND")
        continue
    
    print(f"\n{'='*60}")
    print(f"  {db_path} — {os.path.getsize(db_path)} bytes")
    print(f"{'='*60}")
    
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    
    tables = con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    for t in tables:
        name = t[0]
        count = con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        if count > 0:
            print(f"  {name}: {count} rows")
    
    # Check demo_trades
    try:
        r = con.execute("""
            SELECT result, COUNT(*) as cnt
            FROM demo_trades
            GROUP BY result
        """).fetchall()
        if r:
            print(f"\n  demo_trades breakdown:")
            for row in r:
                print(f"    {row['result']}: {row['cnt']}")
            
            # Accuracy
            wins = sum(row['cnt'] for row in r if row['result'] == 'win')
            losses = sum(row['cnt'] for row in r if row['result'] == 'loss')
            total = wins + losses
            if total > 0:
                print(f"  ACCURACY: {wins}/{total} = {wins/total*100:.1f}%")
    except Exception:
        pass
    
    # Check trades table
    try:
        r = con.execute("""
            SELECT status, COUNT(*) as cnt
            FROM trades
            GROUP BY status
        """).fetchall()
        if r:
            print(f"\n  trades breakdown:")
            for row in r:
                print(f"    {row['status']}: {row['cnt']}")
    except Exception:
        pass
    
    # Check outcomes
    try:
        r = con.execute("""
            SELECT outcome, COUNT(*) as cnt, SUM(pnl) as total_pnl
            FROM outcomes
            GROUP BY outcome
        """).fetchall()
        if r:
            print(f"\n  outcomes breakdown:")
            for row in r:
                print(f"    {row['outcome']}: {row['cnt']} (PnL: ${row['total_pnl']:.2f})")
    except Exception:
        pass
    
    con.close()

# Check for WALLET_BACKUP or other credential files
print(f"\n{'='*60}")
print("  CREDENTIAL FILES")
print(f"{'='*60}")
for f in ["WALLET_BACKUP.txt", "WALLET_BACKUP", ".env.local", ".env.production"]:
    if os.path.exists(f):
        print(f"  Found: {f} ({os.path.getsize(f)} bytes)")