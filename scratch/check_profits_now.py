#!/usr/bin/env python3
"""Quick profit audit of local bot.db"""
import sqlite3
from pathlib import Path

db_path = Path(__file__).parent.parent / "bot.db"
if not db_path.exists():
    print("bot.db not found!")
    exit(1)

conn = sqlite3.connect(str(db_path))
conn.row_factory = sqlite3.Row

# List all tables
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("=== Tables in bot.db ===")
for t in tables:
    name = t[0]
    count = conn.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]
    print(f"  {name}: {count} rows")

# Check demo_trades
try:
    total_trades = conn.execute("SELECT COUNT(*) FROM demo_trades").fetchone()[0]
    resolved = conn.execute(
        "SELECT COUNT(*) FROM demo_trades WHERE result IS NOT NULL AND result != '' AND result != 'pending'"
    ).fetchone()[0]
    wins = conn.execute("SELECT COUNT(*) FROM demo_trades WHERE result = 'win'").fetchone()[0]
    losses = conn.execute("SELECT COUNT(*) FROM demo_trades WHERE result = 'loss'").fetchone()[0]
    voids = conn.execute("SELECT COUNT(*) FROM demo_trades WHERE result = 'void'").fetchone()[0]
    pending = total_trades - resolved
    total_pnl = conn.execute(
        "SELECT COALESCE(SUM(pnl), 0) FROM demo_trades WHERE result IS NOT NULL AND result != '' AND result != 'pending'"
    ).fetchone()[0]
    total_bet = conn.execute(
        "SELECT COALESCE(SUM(bet_amount), 0) FROM demo_trades"
    ).fetchone()[0]
    
    print(f"\n=== PROFIT SUMMARY (Local bot.db) ===")
    print(f"Total trades: {total_trades}")
    print(f"Resolved: {resolved} (Wins: {wins}, Losses: {losses}, Voids: {voids})")
    print(f"Pending: {pending}")
    if resolved > 0:
        acc = wins / resolved * 100
        print(f"Accuracy: {acc:.1f}%")
        print(f"Total PnL: ${total_pnl:.2f}")
        print(f"Avg PnL/trade: ${total_pnl/resolved:.2f}")
        print(f"Total bet: ${total_bet:.2f}")
        print(f"ROI: {total_pnl/total_bet*100:.1f}%" if total_bet > 0 else "ROI: N/A")
    
    # Show last 10 trades
    print(f"\n=== Last 10 trades ===")
    rows = conn.execute(
        "SELECT id, market_question, side, entry_price, bet_amount, result, pnl, strategy, created_at "
        "FROM demo_trades ORDER BY id DESC LIMIT 10"
    ).fetchall()
    for r in rows:
        d = dict(r)
        print(f"  #{d['id']} | {d['side']} @{d['entry_price']} | ${d['bet_amount']} | "
              f"{d['result']} | PnL=${d['pnl'] or 0:.2f} | {d['strategy']} | {d['market_question'][:60]}")
    
    # Show strategy breakdown
    print(f"\n=== PnL by Strategy ===")
    strat_rows = conn.execute(
        "SELECT strategy, COUNT(*) as cnt, "
        "SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins, "
        "SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) as losses, "
        "COALESCE(SUM(pnl), 0) as total_pnl "
        "FROM demo_trades GROUP BY strategy ORDER BY total_pnl DESC"
    ).fetchall()
    for s in strat_rows:
        d = dict(s)
        print(f"  {d['strategy'] or 'none'}: {d['cnt']} trades ({d['wins']}W/{d['losses']}L) PnL=${d['total_pnl']:.2f}")

except Exception as e:
    print(f"Error: {e}")

# Check other tables
for table_name in ['demo_news', 'demo_runs', 'news_events', 'pipeline_runs']:
    try:
        count = conn.execute(f"SELECT COUNT(*) FROM [{table_name}]").fetchone()[0]
        print(f"\n  {table_name}: {count} rows")
    except:
        pass

conn.close()