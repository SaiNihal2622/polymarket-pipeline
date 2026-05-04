import sqlite3

db_path = r"C:\Users\saini\Desktop\iplclaude\polymarket-pipeline\trades.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()

for table in tables:
    tname = table[0]
    cursor.execute(f"SELECT count(*) FROM {tname}")
    count = cursor.fetchone()[0]
    print(f"Table {tname}: {count} rows")

conn.close()
