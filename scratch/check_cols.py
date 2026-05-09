import sqlite3
conn = sqlite3.connect("trades.db")
cols = [r[1] for r in conn.execute("PRAGMA table_info(trades)").fetchall()]
print("TRADES COLUMNS:", cols)

# Add end_date_iso column if missing
if "end_date_iso" not in cols:
    conn.execute("ALTER TABLE trades ADD COLUMN end_date_iso TEXT")
    conn.commit()
    print("Added end_date_iso column")
else:
    print("end_date_iso already exists")

# Check outcomes count
out = conn.execute("SELECT COUNT(*) FROM outcomes").fetchone()
print(f"\nOUTCOMES: {out[0]} resolved trades")

# Check pending count
pend = conn.execute("SELECT COUNT(*) FROM trades WHERE status IN ('demo','dry_run')").fetchone()
print(f"PENDING: {pend[0]}")

# Check recent resolved
rows2 = conn.execute("""
    SELECT t.id, t.market_question, o.result, o.pnl
    FROM trades t JOIN outcomes o ON t.id=o.trade_id
    ORDER BY o.resolved_at DESC LIMIT 5
""").fetchall()
for r in rows2:
    print(f"  #{r[0]} {r[2]} pnl={r[3]} q={r[1][:50]}")

conn.close()
