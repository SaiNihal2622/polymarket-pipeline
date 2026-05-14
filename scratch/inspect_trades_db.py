#!/usr/bin/env python3
"""Inspect the trades.db database."""
import sqlite3
import os

db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "trades.db")
print(f"DB path: {db_path}")
print(f"DB size: {os.path.getsize(db_path)} bytes")

con = sqlite3.connect(db_path)
con.row_factory = sqlite3.Row

# List all tables
tables = con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print(f"\nTables: {[t['name'] for t in tables]}")

# For each table, show count and schema
for t in tables:
    name = t['name']
    try:
        count = con.execute(f'SELECT COUNT(*) as c FROM [{name}]').fetchone()['c']
        cols = con.execute(f'PRAGMA table_info([{name}])').fetchall()
        col_names = [c['name'] for c in cols]
        print(f"\nTable: {name} ({count} rows)")
        print(f"  Columns: {col_names}")
        if count > 0:
            sample = con.execute(f'SELECT * FROM [{name}] LIMIT 3').fetchall()
            for row in sample:
                print(f"  Sample: {dict(row)}")
    except Exception as e:
        print(f"  Error: {e}")

# Also check demo_trades specifically if it exists
table_names = [t['name'] for t in tables]
if 'demo_trades' in table_names:
    print("\n" + "=" * 60)
    print("DEMO_TRADES DETAILED ANALYSIS")
    print("=" * 60)
    
    row = con.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) as losses,
            SUM(CASE WHEN result = 'push' THEN 1 ELSE 0 END) as pushes,
            SUM(CASE WHEN result = 'void' THEN 1 ELSE 0 END) as voids,
            SUM(CASE WHEN result = 'pending' THEN 1 ELSE 0 END) as pending,
            COALESCE(SUM(pnl), 0) as total_pnl,
            COUNT(CASE WHEN result IN ('win','loss','push') THEN 1 END) as resolved,
            MIN(created_at) as first_trade,
            MAX(created_at) as last_trade
        FROM demo_trades
    """).fetchone()
    
    print(f"Total trades:     {row['total']}")
    print(f"Wins:             {row['wins']}")
    print(f"Losses:           {row['losses']}")
    print(f"Pushes:           {row['pushes']}")
    print(f"Voids:            {row['voids']}")
    print(f"Pending:          {row['pending']}")
    print(f"Resolved:         {row['resolved']}")
    total_pnl = row['total_pnl'] or 0.0
    print(f"Total PnL:        ${total_pnl:+.2f}")
    print(f"First trade:      {row['first_trade']}")
    print(f"Last trade:       {row['last_trade']}")
    
    wins = row['wins'] or 0
    losses = row['losses'] or 0
    decisive = wins + losses
    if decisive > 0:
        print(f"Accuracy:         {wins / decisive * 100:.1f}%")
        print(f"Win/Loss ratio:   {wins}:{losses}")
    
    # Strategy breakdown
    print("\n--- Strategy Breakdown ---")
    strats = con.execute("""
        SELECT strategy,
            COUNT(*) as total,
            SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) as losses,
            COALESCE(SUM(pnl), 0) as pnl
        FROM demo_trades
        GROUP BY strategy
        ORDER BY pnl DESC
    """).fetchall()
    
    for s in strats:
        s_wins = s['wins'] or 0
        s_losses = s['losses'] or 0
        s_dec = s_wins + s_losses
        acc = f"{s_wins / s_dec * 100:.0f}%" if s_dec > 0 else "N/A"
        strat_name = s['strategy'] or "(none)"
        s_pnl = s['pnl'] or 0.0
        print(f"  {strat_name:<25} {s['total']:>4} trades | {s_wins}W/{s_losses}L | Acc:{acc:>5} | PnL: ${s_pnl:+.2f}")
    
    # Daily PnL
    print("\n--- Daily PnL ---")
    daily = con.execute("""
        SELECT date(resolved_at) as day,
            COUNT(*) as trades,
            SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) as losses,
            COALESCE(SUM(pnl), 0) as pnl
        FROM demo_trades
        WHERE resolved_at IS NOT NULL
        GROUP BY date(resolved_at)
        ORDER BY day DESC
        LIMIT 14
    """).fetchall()
    
    for d in daily:
        d_wins = d['wins'] or 0
        d_losses = d['losses'] or 0
        d_pnl = d['pnl'] or 0.0
        print(f"  {d['day']} | {d['trades']} trades | {d_wins}W/{d_losses}L | PnL: ${d_pnl:+.2f}")
    
    # Side breakdown
    print("\n--- Side Breakdown (YES vs NO) ---")
    sides = con.execute("""
        SELECT side,
            COUNT(*) as total,
            SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) as losses,
            COALESCE(SUM(pnl), 0) as pnl
        FROM demo_trades
        WHERE result IN ('win','loss')
        GROUP BY side
    """).fetchall()
    
    for s in sides:
        s_wins = s['wins'] or 0
        s_losses = s['losses'] or 0
        s_dec = s_wins + s_losses
        acc = f"{s_wins / s_dec * 100:.0f}%" if s_dec > 0 else "N/A"
        s_pnl = s['pnl'] or 0.0
        print(f"  {s['side']:<6} {s['total']:>4} trades | {s_wins}W/{s_losses}L | Acc:{acc:>5} | PnL: ${s_pnl:+.2f}")
    
    # Recent resolved trades
    print("\n--- Recent Resolved Trades (last 20) ---")
    recent = con.execute("""
        SELECT id, market_question, side, entry_price, bet_amount, result, pnl, strategy, resolved_at
        FROM demo_trades
        WHERE result IN ('win','loss')
        ORDER BY resolved_at DESC
        LIMIT 20
    """).fetchall()
    
    for t in recent:
        sym = "WIN" if t['result'] == 'win' else "LOSS"
        ep = t['entry_price'] or 0
        ba = t['bet_amount'] or 0
        pnl = t['pnl'] or 0
        strat = t['strategy'] or ""
        q = (t['market_question'] or "")[:60]
        print(f"  #{t['id']} [{sym}] {t['side']} @{ep:.2f} bet=${ba:.2f} pnl=${pnl:+.2f} | {strat} | {q}")
    
    # Pending trades
    print("\n--- Pending Trades (latest 15) ---")
    pend = con.execute("""
        SELECT id, market_question, side, entry_price, bet_amount, strategy, created_at,
            CAST((julianday('now') - julianday(created_at)) * 24 AS INTEGER) as hours_waiting
        FROM demo_trades
        WHERE result = 'pending'
        ORDER BY created_at DESC
        LIMIT 15
    """).fetchall()
    
    for p in pend:
        ep = p['entry_price'] or 0
        ba = p['bet_amount'] or 0
        hw = p['hours_waiting'] or 0
        strat = p['strategy'] or ""
        q = (p['market_question'] or "")[:55]
        print(f"  #{p['id']} {p['side']} @{ep:.2f} bet=${ba:.2f} | {hw}h waiting | {strat} | {q}")
    
    total_pending = row['pending'] or 0
    print(f"\n  ... {len(pend)} shown, total pending = {total_pending}")

con.close()