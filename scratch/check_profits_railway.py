import sqlite3
import os

db_path = "/data/bot.db" if os.path.exists("/data") else "bot.db"
print(f"DB path: {db_path}")
print(f"DB exists: {os.path.exists(db_path)}")

conn = sqlite3.connect(db_path)

print("\n=== TRADE STATS ===")
total = conn.execute("SELECT COUNT(*) FROM demo_trades").fetchone()[0]
resolved = conn.execute("SELECT COUNT(*) FROM demo_trades WHERE result NOT IN ('pending', '', 'void') AND result IS NOT NULL").fetchone()[0]
wins = conn.execute("SELECT COUNT(*) FROM demo_trades WHERE result = 'win'").fetchone()[0]
losses = conn.execute("SELECT COUNT(*) FROM demo_trades WHERE result = 'loss'").fetchone()[0]
pushes = conn.execute("SELECT COUNT(*) FROM demo_trades WHERE result = 'push'").fetchone()[0]
voids = conn.execute("SELECT COUNT(*) FROM demo_trades WHERE result = 'void'").fetchone()[0]
pending = conn.execute("SELECT COUNT(*) FROM demo_trades WHERE result IS NULL OR result = '' OR result = 'pending'").fetchone()[0]
pnl = conn.execute("SELECT COALESCE(SUM(pnl), 0) FROM demo_trades WHERE result NOT IN ('pending', '', 'void') AND result IS NOT NULL AND pnl IS NOT NULL").fetchone()[0]

print(f"Total trades: {total}")
print(f"Resolved: {resolved}")
print(f"Wins: {wins}")
print(f"Losses: {losses}")
print(f"Pushes: {pushes}")
print(f"Voids: {voids}")
print(f"Pending: {pending}")
print(f"Total PnL: ${pnl:+.2f}")
if resolved > 0:
    print(f"Accuracy: {wins/resolved*100:.1f}%")
    print(f"Avg PnL/trade: ${pnl/resolved:+.2f}")

print("\n=== RECENT TRADES (last 30) ===")
rows = conn.execute(
    "SELECT id, market_question, side, entry_price, bet_amount, result, pnl, strategy, created_at, resolved_at "
    "FROM demo_trades ORDER BY id DESC LIMIT 30"
).fetchall()
for r in rows:
    q = (r[1] or "?")[:55]
    res = r[5] or "pending"
    p = r[6] if r[6] is not None else 0.0
    print(f"#{r[0]:>4} | {res:<6} | {r[2]:<3} | entry={r[3] or 0:.2f} | bet=${r[4] or 0:.2f} | pnl=${p:+.2f} | {r[7] or '?':<20} | {q}")

print("\n=== RESOLVED TRADES DETAIL ===")
rows2 = conn.execute(
    "SELECT id, market_question, side, entry_price, bet_amount, result, pnl, strategy, created_at, resolved_at "
    "FROM demo_trades WHERE result NOT IN ('pending', '', 'void') AND result IS NOT NULL ORDER BY id DESC"
).fetchall()
for r in rows2:
    q = (r[1] or "?")[:55]
    p = r[6] if r[6] is not None else 0.0
    print(f"#{r[0]:>4} | {r[5]:<6} | {r[2]:<3} | entry={r[3] or 0:.2f} | bet=${r[4] or 0:.2f} | pnl=${p:+.2f} | {r[7] or '?':<20} | created={r[8] or '?'} | resolved={r[9] or '?'} | {q}")

print("\n=== PnL BY STRATEGY ===")
strats = conn.execute(
    "SELECT strategy, COUNT(*) as cnt, SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as w, "
    "SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) as l, COALESCE(SUM(pnl),0) as total_pnl "
    "FROM demo_trades WHERE result NOT IN ('pending','','void') AND result IS NOT NULL GROUP BY strategy"
).fetchall()
for s in strats:
    print(f"  {s[0] or 'unknown':<25} | {s[1]} trades | {s[2]}W/{s[3]}L | PnL: ${s[4]:+.2f}")

print("\n=== PnL BY SIDE ===")
sides = conn.execute(
    "SELECT side, COUNT(*) as cnt, SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as w, "
    "SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) as l, COALESCE(SUM(pnl),0) as total_pnl "
    "FROM demo_trades WHERE result NOT IN ('pending','','void') AND result IS NOT NULL GROUP BY side"
).fetchall()
for s in sides:
    print(f"  {s[0] or 'unknown':<5} | {s[1]} trades | {s[2]}W/{s[3]}L | PnL: ${s[4]:+.2f}")

print("\n=== TABLES IN DB ===")
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
for t in tables:
    cnt = conn.execute(f"SELECT COUNT(*) FROM [{t[0]}]").fetchone()[0]
    print(f"  {t[0]}: {cnt} rows")

conn.close()