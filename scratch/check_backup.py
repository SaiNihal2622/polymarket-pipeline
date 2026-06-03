import json
import sqlite3

# Check JSON backup
try:
    data = json.load(open('trades_backup.json'))
    trades = data['trades']
    print(f"=== JSON Backup: {len(trades)} trades ===")
    for t in trades[-10:]:
        print(f"#{t.get('id','?')} | {t.get('side','?')} | status={t.get('status','?')} | q={t.get('market_question','?')[:70]}")
        print(f"   market_id={str(t.get('market_id','N/A'))[:40]}")
except FileNotFoundError:
    print("No trades_backup.json found")
except Exception as e:
    print(f"JSON error: {e}")

# Check SQLite DB
try:
    conn = sqlite3.connect('trades.db')
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT t.id, t.market_question, t.side, t.status, t.market_id, t.token_id, t.created_at,
               o.result, o.pnl, o.resolved_at
        FROM trades t
        LEFT JOIN outcomes o ON t.id = o.trade_id
        ORDER BY t.id DESC LIMIT 10
    """).fetchall()
    print(f"\n=== SQLite DB: {len(rows)} recent trades ===")
    for r in rows:
        print(f"#{r['id']} | {r['side']} | status={r['status']} | result={r['result']} | pnl={r['pnl']}")
        print(f"   q={r['market_question'][:80]}")
        print(f"   market_id={r['market_id'][:40] if r['market_id'] else 'N/A'} | token={str(r['token_id'])[:20] if r['token_id'] else 'N/A'} | created={r['created_at']}")
    conn.close()
except Exception as e:
    print(f"SQLite error: {e}")