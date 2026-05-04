import sqlite3
from pathlib import Path

DB_PATH = Path(r"c:\Users\saini\Desktop\iplclaude\cricket-trading-system\cricket_trading_local.db")

def check_cricket_stats():
    if not DB_PATH.exists():
        print(f"No database found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Check tables
        tables = cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        print(f"Tables: {[t['name'] for t in tables]}")
        
        for table in [t['name'] for t in tables]:
            count = cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"Table {table}: {count} rows")
            
        # Try to find accuracy if outcome table exists
        if 'outcomes' in [t['name'] for t in tables]:
            res = cursor.execute("""
                SELECT 
                    COUNT(*) as total_resolved,
                    SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) as losses
                FROM outcomes
            """).fetchone()
            
            total_resolved = res['total_resolved']
            wins = res['wins'] or 0
            losses = res['losses'] or 0
            
            accuracy = (wins / total_resolved * 100) if total_resolved > 0 else 0
            print(f"\nAccuracy: {accuracy:.2f}% ({wins}/{total_resolved})")
        else:
            print("\nNo 'outcomes' table found.")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    check_cricket_stats()
