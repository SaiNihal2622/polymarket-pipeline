"""Check worktree copy of trades.db for historical data."""
import sqlite3
import json

DB = ".claude/worktrees/serene-wu/trades.db"

def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Get all tables
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur.fetchall()]
    print("TABLES:", tables)

    for t in tables:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        cnt = cur.fetchone()[0]
        print(f"  {t}: {cnt} rows")

    # Check trades data
    print("\n=== TRADES ===")
    cur.execute("SELECT * FROM trades ORDER BY id DESC LIMIT 5")
    for row in cur.fetchall():
        d = dict(row)
        print(json.dumps(d, indent=2, default=str))

    # Check outcomes
    print("\n=== OUTCOMES ===")
    cur.execute("SELECT * FROM outcomes ORDER BY id DESC LIMIT 10")
    rows = cur.fetchall()
    print(f"Total outcomes: {len(rows)}")
    for row in rows:
        d = dict(row)
        print(json.dumps(d, indent=2, default=str))

    # Profit summary from outcomes
    print("\n=== PROFIT SUMMARY FROM OUTCOMES ===")
    cur.execute("""
        SELECT 
            result,
            COUNT(*) as count,
            SUM(pnl) as total_pnl,
            AVG(pnl) as avg_pnl
        FROM outcomes 
        GROUP BY result
    """)
    for row in cur.fetchall():
        print(dict(row))

    # Trades summary
    print("\n=== TRADES SUMMARY ===")
    cur.execute("""
        SELECT 
            status,
            COUNT(*) as count,
            SUM(amount_usd) as total_amount,
            AVG(edge) as avg_edge
        FROM trades 
        GROUP BY status
    """)
    for row in cur.fetchall():
        print(dict(row))

    # Calibration
    print("\n=== CALIBRATION ===")
    cur.execute("SELECT COUNT(*) FROM calibration")
    cnt = cur.fetchone()[0]
    print(f"Total calibration entries: {cnt}")
    if cnt > 0:
        cur.execute("""
            SELECT 
                classification,
                correct,
                COUNT(*) as count
            FROM calibration 
            GROUP BY classification, correct
        """)
        for row in cur.fetchall():
            print(dict(row))

    # Pipeline runs
    print("\n=== PIPELINE RUNS ===")
    cur.execute("SELECT * FROM pipeline_runs ORDER BY id")
    for row in cur.fetchall():
        print(json.dumps(dict(row), indent=2, default=str))

    # Demo trades
    print("\n=== DEMO TRADES SUMMARY ===")
    cur.execute("SELECT COUNT(*) FROM demo_trades")
    cnt = cur.fetchone()[0]
    print(f"Total demo trades: {cnt}")
    if cnt > 0:
        cur.execute("""
            SELECT 
                result,
                COUNT(*) as count,
                SUM(pnl) as total_pnl,
                AVG(pnl) as avg_pnl,
                SUM(bet_amount) as total_bet,
                SUM(win_amount) as total_win
            FROM demo_trades 
            GROUP BY result
        """)
        for row in cur.fetchall():
            print(dict(row))
        
        # Overall demo P&L
        cur.execute("""
            SELECT 
                COUNT(*) as total_trades,
                SUM(bet_amount) as total_wagered,
                SUM(win_amount) as total_won,
                SUM(pnl) as net_pnl,
                AVG(pnl) as avg_pnl_per_trade,
                MIN(created_at) as first_trade,
                MAX(created_at) as last_trade
            FROM demo_trades
        """)
        print("\nOVERALL DEMO STATS:")
        print(json.dumps(dict(cur.fetchone()), indent=2, default=str))

    conn.close()

if __name__ == "__main__":
    main()