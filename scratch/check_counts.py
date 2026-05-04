import sqlite3

def check_counts():
    conn = sqlite3.connect('trades.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    
    for (table,) in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        print(f"Table {table}: {count} rows")
            
    conn.close()

if __name__ == "__main__":
    check_counts()
