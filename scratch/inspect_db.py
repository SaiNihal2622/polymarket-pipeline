import sqlite3

def inspect():
    db_path = 'C:/Users/saini/Desktop/iplclaude/polymarket-pipeline/trades.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("--- Table Summary ---")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    for table in tables:
        cursor.execute(f"SELECT count(*) FROM {table}")
        count = cursor.fetchone()[0]
        print(f"{table}: {count} rows")
        
    for table in ['trades', 'outcomes', 'calibration']:
        print(f"\n--- {table} Schema ---")
        cursor.execute(f"PRAGMA table_info({table})")
        cols = cursor.fetchall()
        for col in cols:
            print(col)
            
    print("\n--- Recent Trades Sample ---")
    try:
        cursor.execute("SELECT * FROM trades ORDER BY id DESC LIMIT 5")
        rows = cursor.fetchall()
        for row in rows:
            print(row)
    except Exception as e:
        print(f"Error reading trades: {e}")

    print("\n--- Outcomes Sample ---")
    try:
        cursor.execute("SELECT * FROM outcomes ORDER BY id DESC LIMIT 5")
        rows = cursor.fetchall()
        for row in rows:
            print(row)
    except Exception as e:
        print(f"Error reading outcomes: {e}")

    conn.close()

if __name__ == "__main__":
    inspect()

