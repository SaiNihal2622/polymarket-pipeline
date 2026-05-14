import sqlite3
conn = sqlite3.connect('/data/trades.db')
conn.row_factory = sqlite3.Row
print('=== TRADES ===')
rows = conn.execute('SELECT id,market_question,side,status,market_price,edge,created_at FROM trades ORDER BY id DESC LIMIT 20').fetchall()
for r in rows:
    q = r['market_question'][:60] if r['market_question'] else '?'
    e = r['edge'] if r['edge'] else 0
    print(f"#{r['id']} | {r['side']} | p={r['market_price']} e={e:.3f} | {r['status']} | {q} | {r['created_at']}")

print('\n=== OUTCOMES ===')
rows2 = conn.execute('SELECT o.*,t.side,t.market_question FROM outcomes o JOIN trades t ON o.trade_id=t.id ORDER BY o.id DESC LIMIT 10').fetchall()
for r in rows2:
    q = r['market_question'][:50] if r['market_question'] else '?'
    print(f"trade#{r['trade_id']} {r['result']} pnl={r['pnl']} | {q}")

print('\n=== STATS ===')
for row in conn.execute('SELECT status, COUNT(*) as c FROM trades GROUP BY status'):
    print(f"  {row[0]}: {row[1]}")

print(f"\nTotal trades: {conn.execute('SELECT COUNT(*) FROM trades').fetchone()[0]}")
print(f"Total outcomes: {conn.execute('SELECT COUNT(*) FROM outcomes').fetchone()[0]}")
conn.close()