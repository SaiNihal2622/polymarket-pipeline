import sqlite3
from pathlib import Path

db_path = Path("c:/Users/saini/Desktop/iplclaude/polymarket-pipeline/trades.db")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
print(f"Tables in {db_path}:")
for table in tables:
    print(f"- {table[0]}")

conn.close()
