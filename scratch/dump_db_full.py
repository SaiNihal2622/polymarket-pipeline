import sqlite3
import os

db_path = r'c:\Users\saini\Desktop\iplclaude\polymarket-pipeline\trades.db'

if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Get all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = [row[0] for row in cursor.fetchall()]

print(f"Database: {db_path}")
for table in tables:
    cursor.execute(f"SELECT count(*) FROM {table}")
    count = cursor.fetchone()[0]
    print(f"Table {table:20}: {count} rows")

print("\n--- Recent Trades ---")
cursor.execute("SELECT * FROM trades ORDER BY created_at DESC LIMIT 5")
trades = cursor.fetchall()
for t in trades:
    print(dict(t))

print("\n--- Calibration Data ---")
cursor.execute("SELECT * FROM calibration LIMIT 5")
cal = cursor.fetchall()
for c in cal:
    print(dict(c))

conn.close()
