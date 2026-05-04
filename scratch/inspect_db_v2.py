import sqlite3
from pathlib import Path

db_path = Path("c:/Users/saini/Desktop/iplclaude/polymarket-pipeline/trades.db")
print(f"Inspecting {db_path}...")

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

tables = ["trades", "outcomes", "calibration", "pipeline_runs", "news_events"]

for table in tables:
    try:
        count = cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"Table {table}: {count} rows")
    except Exception as e:
        print(f"Error reading {table}: {e}")

# If calibration has rows, show accuracy
try:
    res = cursor.execute("SELECT COUNT(*) as total, SUM(CASE WHEN correct = 1 THEN 1 ELSE 0 END) as correct FROM calibration WHERE correct IS NOT NULL").fetchone()
    if res and res['total'] > 0:
        total = res['total']
        correct = res['correct'] or 0
        accuracy = (correct / total) * 100
        print(f"\nAccuracy: {accuracy:.2f}% ({correct}/{total})")
except Exception as e:
    print(f"Error calculating accuracy: {e}")

conn.close()
