import sqlite3
import os

db_path = r'C:\Users\saini\Desktop\iplclaude\polymarket-pipeline\trades.db'
conn = sqlite3.connect(db_path)
cur = conn.cursor()

cur.execute('SELECT COUNT(*) FROM trades WHERE token_id IS NOT NULL AND status = "voided"')
print(f"Voided with token_id: {cur.fetchone()[0]}")

cur.execute('SELECT COUNT(*) FROM trades WHERE token_id IS NULL AND status = "voided"')
print(f"Voided without token_id: {cur.fetchone()[0]}")

# Also check for 'dry_run' or 'pending'
cur.execute('SELECT status, COUNT(*) FROM trades GROUP BY status')
print(f"Status distribution: {cur.fetchall()}")

conn.close()
