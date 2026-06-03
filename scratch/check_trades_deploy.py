import sqlite3
conn = sqlite3.connect('trades.db')
conn.row_factory = sqlite3.Row
rows = conn.execute("""
    SELECT t.id, t.market_question, t.side, t.status, t.market_id, t.token_id, t.created_at,
           o.result, o.pnl, o.resolved_at
    FROM trades t
    LEFT JOIN outcomes o ON t.id = o.trade_id
    ORDER BY t.id DESC LIMIT 10
""").fetchall()
for r in rows:
    print(f"#{r['id']} | {r['side']} | status={r['status']} | result={r['result']} | pnl={r['pnl']} | q={r['market_question'][:80]}")
    print(f"   market_id={r['market_id'][:40] if r['market_id'] else 'N/A'} | token_id={str(r['token_id'])[:20] if r['token_id'] else 'N/A'} | created={r['created_at']}")
conn.close()