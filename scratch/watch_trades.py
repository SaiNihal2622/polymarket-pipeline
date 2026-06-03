"""Watch trades database for new entries."""
import sqlite3
import time

DB = "trades.db"
for i in range(6):
    try:
        con = sqlite3.connect(DB)
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT id, market_question, side, entry_price, result, strategy FROM demo_trades ORDER BY id DESC LIMIT 5"
        ).fetchall()
        count = con.execute("SELECT COUNT(*) as cnt FROM demo_trades").fetchone()[0]
        print(f"\nCheck {i+1}: {count} trades total")
        for r in rows:
            print(f"  #{r['id']} {r['side']} @ {r['entry_price']:.3f} | {r['strategy']} | {r['result']} | {r['market_question'][:50]}")
        con.close()
    except Exception as e:
        print(f"Check {i+1}: Error - {e}")
    if i < 5:
        time.sleep(10)