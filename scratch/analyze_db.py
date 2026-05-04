import sqlite3
import pandas as pd

def analyze_accuracy():
    conn = sqlite3.connect('trades.db')
    try:
        # Check tables
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        print(f"Tables: {tables}")

        # Try to read trades
        query = "SELECT * FROM trades ORDER BY timestamp DESC LIMIT 20"
        df = pd.read_sql_query(query, conn)
        print("\nLast 20 trades:")
        print(df)

        # Accuracy stats (replicating resolver logic)
        # Assuming outcomes table exists
        stats_query = """
            SELECT 
                t.status,
                o.outcome as actual_outcome,
                t.direction as predicted_direction,
                COUNT(*) as count
            FROM trades t
            LEFT JOIN outcomes o ON t.market_id = o.market_id
            WHERE t.status IN ('demo', 'dry_run')
            GROUP BY 1, 2, 3
        """
        stats_df = pd.read_sql_query(stats_query, conn)
        print("\nTrade Stats:")
        print(stats_df)

    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    analyze_accuracy()
