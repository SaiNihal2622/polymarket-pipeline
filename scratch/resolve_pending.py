#!/usr/bin/env python3
"""Manually resolve the pending Glenn Youngkin trade."""
import sqlite3
from datetime import datetime, timezone

DB = "trades.db"
conn = sqlite3.connect(DB)

# Check if already resolved
r = conn.execute("SELECT id, trade_id FROM outcomes WHERE trade_id=541").fetchone()
if r:
    print(f"Already resolved: {r}")
else:
    # Glenn Youngkin lost the 2024 Republican primary (Trump won)
    # Traded YES at 0.5, outcome = loss
    conn.execute(
        "INSERT INTO outcomes (trade_id, result, pnl, resolved_at) VALUES (?, ?, ?, ?)",
        (541, "loss", -1.0, datetime.now(timezone.utc).isoformat()),
    )
    conn.execute("UPDATE trades SET status=? WHERE id=?", ("dry_run", 541))
    conn.commit()
    print("Resolved trade #541: Glenn Youngkin -> LOSS (Trump won 2024 primary)")

# Now check final stats
row = conn.execute("""
    SELECT 
        sum(case when result='win' then 1 else 0 end) as w,
        sum(case when result='loss' then 1 else 0 end) as l
    FROM outcomes WHERE result IN ('win','loss')
""").fetchone()
w, l = row[0] or 0, row[1] or 0
t = w + l
print(f"\nFinal stats: {w}W/{l}L = {w/t*100:.1f}% accuracy" if t > 0 else "\nNo resolved trades")

# Show all outcomes
print("\nAll outcomes:")
for r in conn.execute("""
    SELECT t.id, substr(t.market_question,1,60) as q, t.side, o.result, o.pnl
    FROM trades t JOIN outcomes o ON t.id=o.trade_id
    ORDER BY t.id
""").fetchall():
    print(f"  #{r[0]:3d} | {r[2]:3s} | {r[3]:7s} | ${r[4]:+.2f} | {r[1]}")

conn.close()