import sqlite3
conn = sqlite3.connect('trades.db')
conn.execute("UPDATE trades SET status='dry_run' WHERE status='voided'")
print("Un-voided count:", conn.total_changes)
conn.commit()
conn.close()
