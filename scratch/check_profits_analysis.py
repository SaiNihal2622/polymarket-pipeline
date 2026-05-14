#!/usr/bin/env python3
"""Analyze all databases and log files for profit/loss data."""
import sqlite3
import os
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent.parent

# ---- 1. Check all .db files ----
print("=" * 70)
print("DATABASE ANALYSIS")
print("=" * 70)

for db_path in sorted(ROOT.glob("*.db")):
    print(f"\n--- {db_path.name} ---")
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
        print(f"  Tables: {tables}")
        
        for t in tables:
            if t == "sqlite_sequence":
                continue
            cur.execute(f"SELECT COUNT(*) FROM [{t}]")
            count = cur.fetchone()[0]
            print(f"  {t}: {count} rows")
            
            if count > 0:
                # Get schema
                cur.execute(f"PRAGMA table_info([{t}])")
                cols = [(r[1], r[2]) for r in cur.fetchall()]
                col_names = [c[0] for c in cols]
                print(f"    Columns: {col_names}")
                
                # Show sample rows
                cur.execute(f"SELECT * FROM [{t}] LIMIT 5")
                rows = cur.fetchall()
                for row in rows:
                    print(f"    Sample: {dict(row)}")
                
                # Look for profit/loss related data
                profit_cols = [c for c in col_names if any(kw in c.lower() for kw in ['profit', 'loss', 'pnl', 'p&l', 'return', 'amount', 'cost', 'revenue', 'win', 'outcome', 'status', 'resolved', 'settled', 'payout'])]
                if profit_cols:
                    print(f"    Profit-related columns: {profit_cols}")
                    for pc in profit_cols:
                        try:
                            cur.execute(f"SELECT [{pc}], COUNT(*) as cnt FROM [{t}] GROUP BY [{pc}] ORDER BY cnt DESC LIMIT 10")
                            vals = cur.fetchall()
                            print(f"    {pc} distribution: {[dict(v) for v in vals]}")
                        except:
                            pass
        conn.close()
    except Exception as e:
        print(f"  Error: {e}")

# ---- 2. Check for trades data across all DBs ----
print("\n" + "=" * 70)
print("TRADE-RELATED DATA SEARCH")
print("=" * 70)

for db_path in sorted(ROOT.glob("*.db")):
    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
        
        for t in tables:
            if t == "sqlite_sequence":
                continue
            # Check for trade/profit keywords in table name
            if any(kw in t.lower() for kw in ['trade', 'order', 'position', 'bet', 'profit', 'pnl', 'transaction', 'account', 'balance']):
                print(f"\n{db_path.name} -> {t}")
                cur.execute(f"SELECT COUNT(*) FROM [{t}]")
                count = cur.fetchone()[0]
                print(f"  Rows: {count}")
                if count > 0:
                    cur.execute(f"SELECT * FROM [{t}] LIMIT 3")
                    rows = cur.fetchall()
                    for row in rows:
                        print(f"  Row: {row}")
        conn.close()
    except Exception as e:
        print(f"  Error: {e}")

# ---- 3. Check log files for profit data ----
print("\n" + "=" * 70)
print("LOG FILE ANALYSIS")
print("=" * 70)

log_files = list(ROOT.glob("*.log")) + list(ROOT.glob("*.txt"))
for lf in log_files:
    if lf.name in ['requirements.txt', 'requirements-railway.txt', 'scan_log.txt']:
        continue
    try:
        content = lf.read_text(encoding='utf-8', errors='ignore')
        lines = content.split('\n')
        total = len(lines)
        profit_lines = [l for l in lines if any(kw in l.lower() for kw in ['profit', 'loss', 'pnl', 'p&l', 'earn', 'made', 'won', 'lost', 'revenue', 'payout', 'settle', 'resolv'])]
        if profit_lines:
            print(f"\n{lf.name} ({total} lines)")
            for pl in profit_lines[:30]:
                print(f"  {pl.strip()}")
    except Exception as e:
        print(f"  Error reading {lf.name}: {e}")

# ---- 4. Check config.py for profit-related config ----
print("\n" + "=" * 70)
print("CONFIG & CODE PROFIT REFERENCES")
print("=" * 70)

code_files = [ROOT / "config.py", ROOT / "bankroll.py", ROOT / "edge.py", ROOT / "executor.py", 
              ROOT / "resolve_trades.py", ROOT / "resolver.py", ROOT / "pipeline.py", 
              ROOT / "polymarket_bot.py", ROOT / "cleanup_trades.py", ROOT / "cleanup_losers.py"]

for cf in code_files:
    if cf.exists():
        try:
            content = cf.read_text(encoding='utf-8', errors='ignore')
            lines = content.split('\n')
            profit_lines = [(i+1, l) for i, l in enumerate(lines) if any(kw in l.lower() for kw in ['profit', 'loss', 'pnl', 'p&l', 'balance', 'bankroll', 'payout', 'winnings', 'roi', 'return'])]
            if profit_lines:
                print(f"\n{cf.name}:")
                for ln, l in profit_lines[:15]:
                    print(f"  L{ln}: {l.strip()}")
        except Exception as e:
            print(f"  Error: {e}")

# ---- 5. Check scratch analysis scripts ----
print("\n" + "=" * 70)
print("SCRATCH ANALYSIS SCRIPTS")
print("=" * 70)

for sf in sorted((ROOT / "scratch").glob("*profit*")) + sorted((ROOT / "scratch").glob("*analyze*")) + sorted((ROOT / "scratch").glob("*audit*")) + sorted((ROOT / "scratch").glob("*check*")):
    try:
        content = sf.read_text(encoding='utf-8', errors='ignore')
        print(f"\n{sf.name} ({len(content.split(chr(10)))} lines):")
        # Show first 20 lines
        for i, line in enumerate(content.split('\n')[:25]):
            print(f"  {i+1}: {line}")
        print("  ...")
    except:
        pass

# ---- 6. Check dashboard for profit display logic ----
print("\n" + "=" * 70)
print("DASHBOARD PROFIT LOGIC")
print("=" * 70)
for df in [ROOT / "dashboard.py", ROOT / "web_dashboard.py", ROOT / "dashboard_live.html"]:
    if df.exists():
        try:
            content = df.read_text(encoding='utf-8', errors='ignore')
            lines = content.split('\n')
            profit_lines = [(i+1, l) for i, l in enumerate(lines) if any(kw in l.lower() for kw in ['profit', 'pnl', 'p&l', 'total_earn', 'total_profit', 'net_profit', 'roi', 'return', 'balance'])]
            if profit_lines:
                print(f"\n{df.name}:")
                for ln, l in profit_lines[:20]:
                    print(f"  L{ln}: {l.strip()}")
        except:
            pass