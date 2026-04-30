import sqlite3
conn = sqlite3.connect('trades.db')
for r in conn.execute("SELECT market_question, created_at FROM trades LIMIT 50").fetchall():
    print(f"[{r[1]}] {r[0]}")
conn.close()
