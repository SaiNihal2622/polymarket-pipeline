import sqlite3

db_path = r'C:\Users\saini\Desktop\iplclaude\polymarket-pipeline\trades.db'
conn = sqlite3.connect(db_path)
cur = conn.cursor()

cur.execute("UPDATE trades SET status = 'dry_run' WHERE status = 'voided'")
print(f"Un-voided {cur.rowcount} trades.")

conn.commit()
conn.close()
