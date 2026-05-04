import sqlite3
import os

db_path = 'trades.db'
if not os.path.exists(db_path):
    print(f"Database {db_path} not found.")
else:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cur.fetchall()
    print(f"Tables: {tables}")
    for table in tables:
        table_name = table[0]
        cur.execute(f"SELECT count(*) FROM {table_name}")
        count = cur.fetchone()[0]
        print(f"Table {table_name}: {count} records")
    conn.close()
