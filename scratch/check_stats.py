import sqlite3
from pathlib import Path

DB_PATH = Path("trades.db")

def check_stats():
    if not DB_PATH.exists():
        print("No database found.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Total trades
        total = cursor.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
        
        # Resolved stats
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
        
        print(f"Total Trades: {total}")
        print(f"Total Resolved: {total_resolved}")
        print(f"Wins: {wins}")
        print(f"Losses: {losses}")
        print(f"Accuracy: {accuracy:.2f}%")
        
        # Check recent trades
        recent = cursor.execute("SELECT market_question, side, status, created_at FROM trades ORDER BY id DESC LIMIT 5").fetchall()
        print("\nRecent Trades:")
        for r in recent:
            print(f"- {r['created_at']} | {r['market_question'][:50]}... | {r['side']} | {r['status']}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    check_stats()
