import sqlite3
c = sqlite3.connect('trades.db')
cur = c.cursor()
cur.execute("SELECT DISTINCT status FROM trades")
print("All statuses:", [r[0] for r in cur.fetchall()])

cur.execute("SELECT id, side, edge, amount_usd, status FROM trades WHERE status != 'dry_run' ORDER BY id DESC LIMIT 10")
for r in cur.fetchall():
    print(r)
c.close()