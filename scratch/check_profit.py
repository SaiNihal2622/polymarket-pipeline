#!/usr/bin/env python3
"""Check profit summary from all database tables."""
import sqlite3
import os
from pathlib import Path

# Check both possible DB locations
for db_path in ["trades.db", "bot.db", "/data/trades.db"]:
    if not Path(db_path).exists():
        continue
    print(f"\n{'='*60}")
    print(f"DATABASE: {db_path}")
    print(f"Size: {Path(db_path).stat().st_size / 1024:.1f} KB")
    print(f"{'='*60}")
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    # List tables
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print(f"Tables: {tables}")
    
    for table in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
        print(f"  {table}: {count} rows")
        
        if table == "demo_trades" or table == "trades":
            # Full profit analysis
            print(f"\n  --- {table} ANALYSIS ---")
            
            # Status breakdown
            status_rows = conn.execute(f"""
                SELECT result, COUNT(*) as cnt, 
                       COALESCE(SUM(pnl), 0) as total_pnl,
                       COALESCE(SUM(bet_amount), 0) as total_bet
                FROM [{table}]
                GROUP BY result
            """).fetchall()
            
            for r in status_rows:
                print(f"    {r['result']}: {r['cnt']} trades | PnL: ${r['total_pnl']:+.2f} | Wagered: ${r['total_bet']:.2f}")
            
            # Overall stats
            overall = conn.execute(f"""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) as losses,
                    SUM(CASE WHEN result='push' THEN 1 ELSE 0 END) as pushes,
                    SUM(CASE WHEN result='pending' THEN 1 ELSE 0 END) as pending,
                    COALESCE(SUM(pnl), 0) as total_pnl,
                    COALESCE(SUM(bet_amount), 0) as total_wagered,
                    COALESCE(AVG(CASE WHEN result IN ('win','loss') THEN pnl END), 0) as avg_pnl,
                    COALESCE(MAX(pnl), 0) as best_trade,
                    COALESCE(MIN(pnl), 0) as worst_trade
                FROM [{table}]
            """).fetchone()
            
            wins = overall['wins']
            losses = overall['losses']
            decisive = wins + losses
            accuracy = (wins / decisive * 100) if decisive > 0 else 0
            
            print(f"\n    SUMMARY:")
            print(f"    Total trades: {overall['total']}")
            print(f"    Resolved: {decisive} ({wins}W / {losses}L / {overall['pushes']}P)")
            print(f"    Pending: {overall['pending']}")
            print(f"    Accuracy: {accuracy:.1f}%")
            print(f"    Total PnL: ${overall['total_pnl']:+.2f}")
            print(f"    Total Wagered: ${overall['total_wagered']:.2f}")
            print(f"    Avg PnL/trade: ${overall['avg_pnl']:+.2f}")
            print(f"    Best trade: ${overall['best_trade']:+.2f}")
            print(f"    Worst trade: ${overall['worst_trade']:+.2f}")
            if overall['total_wagered'] > 0:
                roi = (overall['total_pnl'] / overall['total_wagered']) * 100
                print(f"    ROI: {roi:+.1f}%")
            
            # Strategy breakdown
            print(f"\n    BY STRATEGY:")
            strat_rows = conn.execute(f"""
                SELECT COALESCE(strategy, 'none') as strat, 
                       COUNT(*) as cnt,
                       SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins,
                       SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) as losses,
                       COALESCE(SUM(pnl), 0) as pnl
                FROM [{table}]
                GROUP BY strategy
                ORDER BY pnl DESC
            """).fetchall()
            for s in strat_rows:
                dec = s['wins'] + s['losses']
                acc = (s['wins'] / dec * 100) if dec > 0 else 0
                print(f"      {s['strat']}: {s['cnt']} trades ({s['wins']}W/{s['losses']}L = {acc:.0f}%) PnL: ${s['pnl']:+.2f}")
            
            # Recent trades
            print(f"\n    LAST 10 TRADES:")
            recent = conn.execute(f"""
                SELECT id, substr(market_question,1,50) as q, side, entry_price, 
                       bet_amount, result, pnl, strategy, created_at
                FROM [{table}] ORDER BY id DESC LIMIT 10
            """).fetchall()
            for r in recent:
                sym = "✅" if r['result'] == 'win' else "❌" if r['result'] == 'loss' else "⏳" if r['result'] == 'pending' else "↩️"
                print(f"      #{r['id']} {sym} {r['side']} @{r['entry_price']:.2f} ${r['bet_amount']:.0f} | {r['result']} ${r['pnl'] or 0:+.2f} | {r['q']}")
    
    conn.close()

# Also check outcomes table if exists
print(f"\n{'='*60}")
print("CHECKING OUTCOMES TABLE")
print(f"{'='*60}")
for db_path in ["trades.db", "bot.db", "/data/trades.db"]:
    if not Path(db_path).exists():
        continue
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if "outcomes" in tables:
        rows = conn.execute("SELECT * FROM outcomes ORDER BY id DESC LIMIT 20").fetchall()
        print(f"  {db_path}.outcomes: {len(rows)} recent")
        for r in rows:
            print(f"    trade_id={r['trade_id']} result={r.get('result','')} pnl={r.get('pnl',0)} resolved={r.get('resolved_at','')}")
    conn.close()