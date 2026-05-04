import sqlite3
from pathlib import Path

db_path = Path("c:/Users/saini/Desktop/iplclaude/polymarket-pipeline/trades.db")
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()

for table in tables:
    t_name = table[0]
    print(f"\n--- Table: {t_name} ---")
    try:
        rows = cursor.execute(f"SELECT * FROM {t_name} LIMIT 5").fetchall()
        if not rows:
            print("Empty")
        for row in rows:
            print(dict(row))
    except Exception as e:
        print(f"Error: {e}")

conn.close()
