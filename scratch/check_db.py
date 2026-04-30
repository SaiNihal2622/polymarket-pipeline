import sqlite3
import os

db_path = r"C:\Users\saini\Desktop\iplclaude\polymarket-pipeline\trades.db"

def check_trades():
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Check trades that were recently un-voided
    rows = cursor.execute("SELECT id, market_question, side, amount_usd, created_at FROM trades WHERE status='dry_run' AND id >= 192 ORDER BY id ASC LIMIT 20").fetchall()
    
    print(f"Found {len(rows)} new pipeline trades in dry_run:")
    for r in rows:
        print(f"ID: {r['id']} | Q: {r['market_question'][:40]} | Side: {r['side']} | Amt: ${r['amount_usd']} | Created: {r['created_at']}")
    
    conn.close()

if __name__ == "__main__":
    check_trades()
