import sqlite3
conn = sqlite3.connect('trades.db')
conn.row_factory = sqlite3.Row
rows = conn.execute("""
    SELECT t.id, t.market_id, t.market_question, t.token_id, t.created_at
    FROM trades t LEFT JOIN outcomes o ON t.id=o.trade_id
    WHERE t.status IN ('demo','dry_run') AND o.id IS NULL AND t.market_id != ''
    ORDER BY t.created_at ASC
""").fetchall()
for r in rows:
    tid = str(r['token_id'])[:20] if r['token_id'] else 'None'
    print(f"#{r['id']} | mid={r['market_id'][:30]} | tid={tid} | q={r['market_question'][:60]}")
print(f"\nTotal pending: {len(rows)}")

# Also show overall stats
row = conn.execute("""
    SELECT COUNT(*) as total,
           SUM(CASE WHEN o.result='win' THEN 1 ELSE 0 END) as wins,
           SUM(CASE WHEN o.result='loss' THEN 1 ELSE 0 END) as losses,
           SUM(CASE WHEN o.result='push' THEN 1 ELSE 0 END) as pushes
    FROM trades t JOIN outcomes o ON t.id=o.trade_id
    WHERE t.status IN ('demo','dry_run')
""").fetchone()
total = row['total'] or 0
wins = row['wins'] or 0
losses = row['losses'] or 0
pushes = row['pushes'] or 0
decisive = wins + losses
acc = (wins/decisive*100) if decisive > 0 else 0
print(f"\nResolved: {total} | W:{wins} L:{losses} P:{pushes} | Acc:{acc:.1f}%")
conn.close()