import sqlite3
conn = sqlite3.connect("trades.db")
conn.row_factory = sqlite3.Row

# Check recent trades with token_ids
rows = conn.execute("SELECT id, market_id, token_id, market_question, status FROM trades ORDER BY id DESC LIMIT 10").fetchall()
for r in rows:
    tid = r["token_id"] or "NULL"
    print(f"#{r['id']} mid={r['market_id'][:30]} tid={tid[:30]} q={r['market_question'][:60]} status={r['status']}")

# Check outcomes
rows2 = conn.execute("SELECT COUNT(*) as c FROM outcomes").fetchone()
print(f"\nTotal outcomes: {rows2['c']}")
rows3 = conn.execute("SELECT result, COUNT(*) as c FROM outcomes GROUP BY result").fetchall()
for r in rows3:
    print(f"  {r['result']}: {r['c']}")

# Check pending trades
rows4 = conn.execute("SELECT COUNT(*) as c FROM trades WHERE status IN ('demo','dry_run')").fetchone()
print(f"\nTotal demo/dry_run trades: {rows4['c']}")
rows5 = conn.execute("""
    SELECT COUNT(*) as c FROM trades t
    LEFT JOIN outcomes o ON t.id = o.trade_id
    WHERE t.status IN ('demo','dry_run') AND o.id IS NULL
""").fetchone()
print(f"Pending (no outcome): {rows5['c']}")

# Check token_id format
rows6 = conn.execute("SELECT token_id FROM trades WHERE token_id IS NOT NULL LIMIT 5").fetchall()
print(f"\nSample token_ids:")
for r in rows6:
    print(f"  len={len(r['token_id'])} val={r['token_id'][:60]}...")

conn.close()