import os, sqlite3

# Check both possible DB paths
for db_path in ['trades.db', 'bot.db']:
    if os.path.exists(db_path):
        print(f"\n=== {db_path} ===")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        print(f"Tables: {[t['name'] for t in tables]}")
        for t in tables:
            count = conn.execute(f"SELECT COUNT(*) as c FROM [{t['name']}]").fetchone()['c']
            print(f"  {t['name']}: {count} rows")
            if t['name'] == 'trades' and count > 0:
                rows = conn.execute('SELECT id, market_id, market_question, side, amount_usd, order_id, status, created_at, token_id FROM trades ORDER BY created_at DESC LIMIT 20').fetchall()
                for r in rows:
                    print(f"    {dict(r)}")
        conn.close()