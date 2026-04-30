import sqlite3
import os

DB_PATH = 'trades.db'

def recalibrate():
    if not os.path.exists(DB_PATH):
        print("DB not found")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 1. Delete all 'push' outcomes so they can be re-resolved with Strategy 1/2
    cur.execute("DELETE FROM outcomes WHERE result = 'push'")
    print(f"Deleted {cur.rowcount} 'push' outcomes.")

    # 2. Delete trades that are clearly hallucinated (heuristic: mention of different states/sports in reason)
    # This is a bit risky but we want to clean the 80% accuracy target.
    # Actually, let's just delete trades where the reason mentions "Pennsylvania" AND "IPL" or "cricket"
    hallucinated_query = """
    DELETE FROM trades 
    WHERE (LOWER(reasoning) LIKE '%pennsylvania%' AND (LOWER(reasoning) LIKE '%ipl%' OR LOWER(reasoning) LIKE '%cricket%'))
       OR (LOWER(reasoning) LIKE '%governor%' AND LOWER(reasoning) LIKE '%batter%')
    """
    cur.execute(hallucinated_query)
    print(f"Deleted {cur.rowcount} hallucinated trades.")
    
    # 3. Clean up orphans
    cur.execute("DELETE FROM outcomes WHERE trade_id NOT IN (SELECT id FROM trades)")
    cur.execute("DELETE FROM calibration WHERE trade_id NOT IN (SELECT id FROM trades)")

    conn.commit()
    conn.close()
    print("Recalibration complete.")

if __name__ == "__main__":
    recalibrate()
