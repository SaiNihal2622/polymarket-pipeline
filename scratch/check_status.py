import sqlite3
conn = sqlite3.connect('trades.db')
print("Trades by status:")
for r in conn.execute("SELECT status, COUNT(*) FROM trades GROUP BY status").fetchall():
    print(r)
conn.close()
