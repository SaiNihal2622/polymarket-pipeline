import sqlite3
conn = sqlite3.connect('trades.db')
print("Non-push outcomes:", conn.execute("SELECT COUNT(*) FROM outcomes WHERE result != 'push'").fetchone()[0])
print("Sample outcomes:")
for r in conn.execute("SELECT * FROM outcomes LIMIT 5").fetchall():
    print(r)
conn.close()
