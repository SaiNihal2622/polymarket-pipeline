"""Comprehensive profit analysis of the Polymarket pipeline."""
import sqlite3
import json
from datetime import datetime

DB = "bot.db"

def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 1. List all tables
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur.fetchall()]
    print("=" * 70)
    print("TABLES IN DB:", tables)
    print("=" * 70)

    # 2. Schema + row counts for each table
    for t in tables:
        cur.execute(f"PRAGMA table_info({t})")
        cols = [r[1] for r in cur.fetchall()]
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        cnt = cur.fetchone()[0]
        print(f"\n--- {t} ({cnt} rows) ---")
        print("Columns:", cols)

    # 3. Look for trades table
    trade_table = None
    for candidate in ["trades", "positions", "bets", "orders"]:
        if candidate in tables:
            trade_table = candidate
            break

    if trade_table:
        print(f"\n{'=' * 70}")
        print(f"ANALYZING TABLE: {trade_table}")
        print(f"{'=' * 70}")
        
        cur.execute(f"SELECT * FROM {trade_table} LIMIT 5")
        for row in cur.fetchall():
            print(json.dumps(dict(row), indent=2, default=str))

    # 4. Check all tables for trade-like data
    print("\n" + "=" * 70)
    print("SCANNING ALL TABLES FOR TRADE/PROFIT DATA")
    print("=" * 70)
    
    for t in tables:
        cur.execute(f"SELECT * FROM {t} LIMIT 1")
        row = cur.fetchone()
        if row:
            print(f"\n--- {t} sample row ---")
            print(json.dumps(dict(row), indent=2, default=str))

    conn.close()

if __name__ == "__main__":
    main()