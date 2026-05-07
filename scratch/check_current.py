import sqlite3
conn = sqlite3.connect("trades.db")
conn.row_factory = sqlite3.Row

total = conn.execute("SELECT COUNT(*) as c FROM trades").fetchone()["c"]
outcomes = conn.execute("SELECT COUNT(*) as c FROM outcomes").fetchone()["c"]
demo = conn.execute("SELECT COUNT(*) as c FROM trades WHERE status IN ('demo','dry_run')").fetchone()["c"]
resolved = conn.execute("""
    SELECT COUNT(*) as c FROM trades t JOIN outcomes o ON t.id=o.trade_id WHERE t.status IN ('demo','dry_run')
""").fetchone()["c"]
wins = conn.execute("""
    SELECT COUNT(*) as c FROM trades t JOIN outcomes o ON t.id=o.trade_id WHERE t.status IN ('demo','dry_run') AND o.result='win'
""").fetchone()["c"]
losses = conn.execute("""
    SELECT COUNT(*) as c FROM trades t JOIN outcomes o ON t.id=o.trade_id WHERE t.status IN ('demo','dry_run') AND o.result='loss'
""").fetchone()["c"]
pending = conn.execute("""
    SELECT COUNT(*) as c FROM trades t LEFT JOIN outcomes o ON t.id=o.trade_id WHERE t.status IN ('demo','dry_run') AND o.id IS NULL AND t.market_id != ''
""").fetchone()["c"]

print(f"Total trades: {total}")
print(f"Total outcomes: {outcomes}")
print(f"Demo/dry_run trades: {demo}")
print(f"Resolved: {resolved} ({wins}W/{losses}L)")
print(f"Pending resolution: {pending}")
decisive = wins + losses
if decisive > 0:
    print(f"Accuracy: {wins/decisive*100:.1f}%")

print("\nLast 5 trades:")
for r in conn.execute("SELECT id, market_question, side, status FROM trades ORDER BY id DESC LIMIT 5").fetchall():
    print(f"  #{r['id']} [{r['status']}] {r['side']} - {r['market_question'][:70]}")

print("\nPending trades:")
for r in conn.execute("""
    SELECT t.id, t.market_question, t.side, t.market_id
    FROM trades t LEFT JOIN outcomes o ON t.id=o.trade_id
    WHERE t.status IN ('demo','dry_run') AND o.id IS NULL AND t.market_id != ''
    ORDER BY t.id
""").fetchall():
    print(f"  #{r['id']} {r['side']} mid={r['market_id'][:30]} - {r['market_question'][:60]}")

conn.close()