#!/usr/bin/env python3
"""Audit trades.db for full profit analysis"""
import sqlite3

conn = sqlite3.connect("trades.db")
conn.row_factory = sqlite3.Row

# List tables
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("=== Tables ===")
for t in tables:
    name = t[0]
    count = conn.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]
    print(f"  {name}: {count} rows")

# Check demo_trades
print("\n=== demo_trades columns ===")
try:
    cols = conn.execute("PRAGMA table_info(demo_trades)").fetchall()
    for c in cols:
        print(f"  {c[1]} ({c[2]})")
    
    total = conn.execute("SELECT COUNT(*) FROM demo_trades").fetchone()[0]
    print(f"\nTotal rows: {total}")
    
    if total > 0:
        resolved = conn.execute(
            "SELECT COUNT(*) FROM demo_trades WHERE result IS NOT NULL AND result != '' AND result != 'pending'"
        ).fetchone()[0]
        wins = conn.execute("SELECT COUNT(*) FROM demo_trades WHERE result = 'win'").fetchone()[0]
        losses = conn.execute("SELECT COUNT(*) FROM demo_trades WHERE result = 'loss'").fetchone()[0]
        voids = conn.execute("SELECT COUNT(*) FROM demo_trades WHERE result = 'void'").fetchone()[0]
        pending = total - resolved
        total_pnl = conn.execute(
            "SELECT COALESCE(SUM(COALESCE(pnl,0)), 0) FROM demo_trades WHERE result IS NOT NULL AND result != '' AND result != 'pending'"
        ).fetchone()[0]
        total_bet = conn.execute("SELECT COALESCE(SUM(bet_amount), 0) FROM demo_trades").fetchone()[0]
        
        print(f"\n=== PROFIT SUMMARY ===")
        print(f"Total trades: {total}")
        print(f"Resolved: {resolved} (Wins: {wins}, Losses: {losses}, Voids: {voids})")
        print(f"Pending: {pending}")
        if resolved > 0:
            acc = wins / resolved * 100
            print(f"Accuracy: {acc:.1f}%")
            print(f"Total PnL: ${total_pnl:.2f}")
            print(f"Avg PnL/trade: ${total_pnl/resolved:.2f}")
            print(f"Total bet: ${total_bet:.2f}")
            if total_bet > 0:
                print(f"ROI: {total_pnl/total_bet*100:.1f}%")
        
        # Last 10 trades
        print(f"\n=== Last 10 trades ===")
        rows = conn.execute(
            "SELECT id, market_question, side, entry_price, bet_amount, result, pnl, strategy, created_at "
            "FROM demo_trades ORDER BY id DESC LIMIT 10"
        ).fetchall()
        for r in rows:
            d = dict(r)
            q = (d.get('market_question') or 'N/A')[:55]
            print(f"  #{d['id']} | {d.get('side','?')} @{d.get('entry_price','?')} | ${d.get('bet_amount',0)} | "
                  f"{d.get('result','?')} | PnL=${d.get('pnl') or 0:.2f} | {d.get('strategy','?')} | {q}")
        
        # Strategy breakdown
        print(f"\n=== PnL by Strategy ===")
        strat_rows = conn.execute(
            "SELECT COALESCE(strategy,'none') as strategy, COUNT(*) as cnt, "
            "SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins, "
            "SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) as losses, "
            "COALESCE(SUM(pnl), 0) as total_pnl "
            "FROM demo_trades GROUP BY strategy ORDER BY total_pnl DESC"
        ).fetchall()
        for s in strat_rows:
            d = dict(s)
            print(f"  {d['strategy']}: {d['cnt']} trades ({d['wins']}W/{d['losses']}L) PnL=${d['total_pnl']:.2f}")
        
        # Date range
        first = conn.execute("SELECT MIN(created_at) FROM demo_trades").fetchone()[0]
        last = conn.execute("SELECT MAX(created_at) FROM demo_trades").fetchone()[0]
        print(f"\nDate range: {first} to {last}")
except Exception as e:
    print(f"Error with demo_trades: {e}")
    import traceback; traceback.print_exc()

# Also check bot.db tables
print("\n=== bot.db ===")
try:
    conn2 = sqlite3.connect("bot.db")
    conn2.row_factory = sqlite3.Row
    tables2 = conn2.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    for t in tables2:
        name = t[0]
        count = conn2.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]
        print(f"  {name}: {count} rows")
    conn2.close()
except Exception as e:
    print(f"  Error: {e}")

conn.close()