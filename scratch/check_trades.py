import sqlite3
con = sqlite3.connect('trades.db')
con.row_factory = sqlite3.Row
rows = con.execute('SELECT id, market_question, side, entry_price, result, strategy, token_id FROM demo_trades ORDER BY id DESC LIMIT 10').fetchall()
for r in rows:
    print(f'#{r["id"]} {r["side"]} @ {r["entry_price"]:.3f} | {r["strategy"]} | {r["result"]} | {r["market_question"][:60]}')
count = con.execute('SELECT COUNT(*) as cnt FROM demo_trades').fetchone()[0]
print(f'\nTotal trades: {count}')
con.close()