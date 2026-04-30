import sqlite3

db_path = r'C:\Users\saini\Desktop\iplclaude\polymarket-pipeline\trades.db'
conn = sqlite3.connect(db_path)
cur = conn.cursor()

cur.execute('SELECT market_id, market_question FROM trades WHERE token_id IS NULL AND status = "dry_run" LIMIT 5')
rows = cur.fetchall()
for r in rows:
    print(f"ID: {r[0]} | Q: {r[1]}")

conn.close()
