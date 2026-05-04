import sqlite3

def get_schema():
    conn = sqlite3.connect('trades.db')
    cursor = conn.cursor()
    
    tables = ['trades', 'outcomes', 'news_events']
    for table in tables:
        print(f"\nSchema for {table}:")
        cursor.execute(f"PRAGMA table_info({table})")
        columns = cursor.fetchall()
        for col in columns:
            print(col)
            
    conn.close()

if __name__ == "__main__":
    get_schema()
