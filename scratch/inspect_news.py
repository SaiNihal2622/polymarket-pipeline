import sqlite3

db_path = r"C:\Users\saini\Desktop\iplclaude\polymarket-pipeline\.claude\worktrees\serene-wu\trades.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute("PRAGMA table_info(news_events)")
cols = [r["name"] for r in cursor.fetchall()]
print(f"Columns: {cols}")

cursor.execute("SELECT * FROM news_events ORDER BY created_at DESC LIMIT 5")
rows = cursor.fetchall()
for r in rows:
    print(dict(r))

conn.close()
