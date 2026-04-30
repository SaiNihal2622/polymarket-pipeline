import sqlite3
import os

db_path = "trades.db"

def reset_db():
    if not os.path.exists(db_path):
        print(f"Database {db_path} not found.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    tables = ["trades", "outcomes", "pipeline_runs", "news_events", "calibration"]
    
    for table in tables:
        try:
            cursor.execute(f"DELETE FROM {table}")
            print(f"Cleared table: {table}")
        except sqlite3.OperationalError as e:
            print(f"Error clearing {table}: {e}")

    conn.commit()
    conn.close()
    print("Database reset complete.")

if __name__ == "__main__":
    reset_db()
