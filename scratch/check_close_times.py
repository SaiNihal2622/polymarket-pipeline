import sqlite3
conn = sqlite3.connect('trades.db')
conn.row_factory = sqlite3.Row
rows = conn.execute('SELECT id, market_question, close_time, close_hours, result FROM demo_trades ORDER BY id DESC LIMIT 15').fetchall()
for r in rows:
    d = dict(r)
    q = (d.get("market_question") or "")[:60]
    ct = d.get("close_time")
    ch = d.get("close_hours")
    res = d.get("result")
    print(f"ID={d['id']} | close_time={ct} | close_hours={ch} | result={res} | {q}")
print()
# Also check if close_time column exists
cols = [row[1] for row in conn.execute("PRAGMA table_info(demo_trades)").fetchall()]
print("Columns:", cols)
print(f"close_time in cols: {'close_time' in cols}")
print(f"close_hours in cols: {'close_hours' in cols}")
conn.close()