#!/usr/bin/env python3
"""Comprehensive profit report from the polymarket pipeline database."""
import sqlite3
import os
from datetime import datetime, timezone

DB_PATH = os.getenv("DB_PATH", "/data/trades.db" if os.path.exists("/data") else "./trades.db")
print(f"Database: {DB_PATH}")
print(f"Exists: {os.path.exists(DB_PATH)}")
print(f"Size: {os.path.getsize(DB_PATH) / 1024:.1f} KB")
print("=" * 80)

con = sqlite3.connect(DB_PATH)
con.row_factory = sqlite3.Row

# List all tables
tables = con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print(f"\n📋 Tables: {[t['name'] for t in tables]}")
print("=" * 80)

# ── 1. Overall Trade Summary ──
print("\n═══ 1. OVERALL TRADE SUMMARY ═══")
try:
    row = con.execute("""
        SELECT
            COUNT(*) as total_trades,
            SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) as losses,
            SUM(CASE WHEN result = 'push' THEN 1 ELSE 0 END) as pushes,
            SUM(CASE WHEN result = 'void' THEN 1 ELSE 0 END) as voids,
            SUM(CASE WHEN result = 'pending' THEN 1 ELSE 0 END) as pending,
            COALESCE(SUM(pnl), 0) as total_pnl,
            COALESCE(SUM(bet_amount), 0) as total_wagered,
            COUNT(CASE WHEN result IN ('win', 'loss') THEN 1 END) as decisive,
            COALESCE(AVG(CASE WHEN result = 'win' THEN pnl END), 0) as avg_win_pnl,
            COALESCE(AVG(CASE WHEN result = 'loss' THEN pnl END), 0) as avg_loss_pnl,
            MIN(created_at) as first_trade,
            MAX(created_at) as last_trade
        FROM demo_trades
    """).fetchone()
    
    decisive = row['decisive'] or 1
    accuracy = (row['wins'] / decisive * 100) if decisive > 0 else 0
    
    print(f"  Total Trades:     {row['total_trades']}")
    print(f"  Wins:             {row['wins']}")
    print(f"  Losses:           {row['losses']}")
    print(f"  Pushes:           {row['pushes']}")
    print(f"  Voids:            {row['voids']}")
    print(f"  Pending:          {row['pending']}")
    print(f"  ───────────────────────────")
    print(f"  Accuracy:         {accuracy:.1f}%")
    print(f"  Total Wagered:    ${row['total_wagered']:.2f}")
    print(f"  Total PnL:        ${row['total_pnl']:+.4f}")
    print(f"  Avg Win PnL:      ${row['avg_win_pnl']:+.4f}")
    print(f"  Avg Loss PnL:     ${row['avg_loss_pnl']:+.4f}")
    print(f"  First Trade:      {row['first_trade']}")
    print(f"  Last Trade:       {row['last_trade']}")
except Exception as e:
    print(f"  Error: {e}")

# ── 2. PnL by Strategy ──
print("\n═══ 2. PnL BY STRATEGY ═══")
try:
    rows = con.execute("""
        SELECT
            strategy,
            COUNT(*) as total,
            SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) as losses,
            SUM(CASE WHEN result = 'pending' THEN 1 ELSE 0 END) as pending,
            COALESCE(SUM(CASE WHEN result IN ('win','loss') THEN pnl ELSE 0 END), 0) as realized_pnl,
            COALESCE(SUM(pnl), 0) as total_pnl,
            COUNT(CASE WHEN result IN ('win','loss') THEN 1 END) as decisive
        FROM demo_trades
        GROUP BY strategy
        ORDER BY realized_pnl DESC
    """).fetchall()
    
    for r in rows:
        dec = r['decisive'] or 1
        acc = (r['wins'] / dec * 100) if dec > 0 else 0
        print(f"  {r['strategy'] or 'unknown':<25} {r['total']:>4} trades | "
              f"{r['wins']}W/{r['losses']}L | {acc:>5.1f}% acc | "
              f"PnL: ${r['realized_pnl']:>+8.2f} | pending: {r['pending']}")
except Exception as e:
    print(f"  Error: {e}")

# ── 3. PnL by Day ──
print("\n═══ 3. PnL BY DAY ═══")
try:
    rows = con.execute("""
        SELECT
            DATE(created_at) as day,
            COUNT(*) as trades,
            SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) as losses,
            COALESCE(SUM(CASE WHEN result IN ('win','loss') THEN pnl ELSE 0 END), 0) as daily_pnl
        FROM demo_trades
        GROUP BY DATE(created_at)
        ORDER BY day DESC
        LIMIT 14
    """).fetchall()
    
    cumulative = 0
    for r in reversed(list(rows)):
        cumulative += r['daily_pnl']
        print(f"  {r['day']}  {r['trades']:>3} trades  {r['wins']}W/{r['losses']}L  "
              f"PnL: ${r['daily_pnl']:>+7.2f}  Cumulative: ${cumulative:>+8.2f}")
except Exception as e:
    print(f"  Error: {e}")

# ── 4. Top Winning Trades ──
print("\n═══ 4. TOP 10 WINNING TRADES ═══")
try:
    rows = con.execute("""
        SELECT id, market_question, side, entry_price, bet_amount, pnl, strategy, created_at
        FROM demo_trades
        WHERE result = 'win'
        ORDER BY pnl DESC
        LIMIT 10
    """).fetchall()
    
    for r in rows:
        print(f"  #{r['id']:>4} ${r['pnl']:>+6.2f} | {r['side']} @{r['entry_price']:.2f} | "
              f"{r['strategy']} | {r['market_question'][:60]}")
except Exception as e:
    print(f"  Error: {e}")

# ── 5. Worst Losing Trades ──
print("\n═══ 5. TOP 10 LOSING TRADES ═══")
try:
    rows = con.execute("""
        SELECT id, market_question, side, entry_price, bet_amount, pnl, strategy, created_at
        FROM demo_trades
        WHERE result = 'loss'
        ORDER BY pnl ASC
        LIMIT 10
    """).fetchall()
    
    for r in rows:
        print(f"  #{r['id']:>4} ${r['pnl']:>+6.2f} | {r['side']} @{r['entry_price']:.2f} | "
              f"{r['strategy']} | {r['market_question'][:60]}")
except Exception as e:
    print(f"  Error: {e}")

# ── 6. Edge & EV Analysis ──
print("\n═══ 6. EDGE & EV ANALYSIS ═══")
try:
    row = con.execute("""
        SELECT
            COUNT(*) as total,
            COALESCE(AVG(edge), 0) as avg_edge,
            COALESCE(AVG(materiality), 0) as avg_mat,
            COALESCE(AVG(composite_score), 0) as avg_rrf,
            COALESCE(AVG(confidence), 0) as avg_conf,
            COALESCE(AVG(entry_price), 0) as avg_entry
        FROM demo_trades
        WHERE result IN ('win', 'loss')
    """).fetchone()
    
    print(f"  Resolved trades:  {row['total']}")
    print(f"  Avg Edge:         {row['avg_edge']:.4f}")
    print(f"  Avg Materiality:  {row['avg_mat']:.4f}")
    print(f"  Avg RRF Score:    {row['avg_rrf']:.4f}")
    print(f"  Avg Confidence:   {row['avg_conf']:.4f}")
    print(f"  Avg Entry Price:  {row['avg_entry']:.4f}")
except Exception as e:
    print(f"  Error: {e}")

# ── 7. Win Rate by Entry Price Range ──
print("\n═══ 7. WIN RATE BY ENTRY PRICE RANGE ═══")
try:
    rows = con.execute("""
        SELECT
            CASE
                WHEN entry_price < 0.15 THEN '0.05-0.14'
                WHEN entry_price < 0.25 THEN '0.15-0.24'
                WHEN entry_price < 0.35 THEN '0.25-0.34'
                WHEN entry_price < 0.50 THEN '0.35-0.49'
                ELSE '0.50+'
            END as price_range,
            COUNT(*) as total,
            SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) as losses,
            COALESCE(SUM(pnl), 0) as total_pnl
        FROM demo_trades
        WHERE result IN ('win', 'loss')
        GROUP BY price_range
        ORDER BY price_range
    """).fetchall()
    
    for r in rows:
        dec = r['wins'] + r['losses']
        acc = (r['wins'] / dec * 100) if dec > 0 else 0
        print(f"  Entry {r['price_range']:<12} {dec:>3} trades | {acc:>5.1f}% win | PnL: ${r['total_pnl']:>+8.2f}")
except Exception as e:
    print(f"  Error: {e}")

# ── 8. Side Performance (YES vs NO) ──
print("\n═══ 8. PERFORMANCE BY SIDE ═══")
try:
    rows = con.execute("""
        SELECT
            side,
            COUNT(*) as total,
            SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) as losses,
            COALESCE(SUM(CASE WHEN result IN ('win','loss') THEN pnl ELSE 0 END), 0) as realized_pnl,
            COALESCE(AVG(entry_price), 0) as avg_entry
        FROM demo_trades
        GROUP BY side
    """).fetchall()
    
    for r in rows:
        dec = r['wins'] + r['losses']
        acc = (r['wins'] / dec * 100) if dec > 0 else 0
        print(f"  {r['side']:<5} {r['total']:>4} trades | {r['wins']}W/{r['losses']}L | "
              f"{acc:>5.1f}% acc | avg entry: {r['avg_entry']:.3f} | PnL: ${r['realized_pnl']:>+8.2f}")
except Exception as e:
    print(f"  Error: {e}")

# ── 9. Live Trading Check ──
print("\n═══ 9. LIVE TRADING READINESS ═══")
try:
    row = con.execute("""
        SELECT COUNT(*) as resolved,
               SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins,
               SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) as losses
        FROM demo_trades
        WHERE result IN ('win', 'loss')
    """).fetchone()
    
    resolved = row['resolved'] or 0
    wins = row['wins'] or 0
    losses = row['losses'] or 0
    acc = (wins / resolved * 100) if resolved > 0 else 0
    
    ready = resolved >= 30 and acc >= 65
    print(f"  Resolved: {resolved}/30 required")
    print(f"  Accuracy: {acc:.1f}%/65% required")
    print(f"  Status:   {'✅ READY TO GO LIVE' if ready else '❌ NOT READY'}")
except Exception as e:
    print(f"  Error: {e}")

# ── 10. Real Money (executor) check ──
print("\n═══ 10. REAL MONEY TRADES (if any) ═══")
try:
    # Check if there's an executor_trades or similar table
    for tbl in ['trades', 'executor_trades', 'live_trades', 'orders']:
        try:
            rows = con.execute(f"SELECT COUNT(*) as cnt FROM {tbl}").fetchone()
            print(f"  Table '{tbl}': {rows['cnt']} rows")
            if rows['cnt'] > 0:
                sample = con.execute(f"SELECT * FROM {tbl} LIMIT 3").fetchall()
                for s in sample:
                    print(f"    {dict(s)}")
        except:
            pass
except Exception as e:
    print(f"  Error: {e}")

con.close()
print("\n" + "=" * 80)
print("Report complete.")