#!/usr/bin/env python3
"""Comprehensive profit analysis for the Polymarket pipeline."""
import sqlite3
import json
import os
from pathlib import Path
from datetime import datetime

DB_FILES = ["trades.db", "bot.db"]

def check_db(db_path):
    if not Path(db_path).exists():
        print(f"  [SKIP] {db_path} does not exist")
        return
    
    size = Path(db_path).stat().st_size / 1024
    print(f"\n{'='*70}")
    print(f"  DATABASE: {db_path} ({size:.1f} KB)")
    print(f"{'='*70}")
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    print(f"  Tables: {tables}")
    
    # --- demo_trades analysis ---
    if "demo_trades" in tables:
        print(f"\n--- demo_trades ---")
        total = conn.execute("SELECT COUNT(*) as c FROM demo_trades").fetchone()["c"]
        print(f"  Total trades: {total}")
        
        # By result
        rows = conn.execute(
            "SELECT result, COUNT(*) as c, SUM(pnl) as total_pnl, "
            "AVG(pnl) as avg_pnl FROM demo_trades GROUP BY result"
        ).fetchall()
        print(f"\n  By result:")
        grand_pnl = 0.0
        for r in rows:
            pnl = r["total_pnl"] or 0
            grand_pnl += pnl
            avg = r["avg_pnl"] or 0
            print(f"    {r['result']:15s}: {r['c']:5d} trades | PnL: ${pnl:+.2f} | Avg: ${avg:+.4f}")
        print(f"    {'TOTAL':15s}: {total:5d} trades | PnL: ${grand_pnl:+.2f}")
        
        # Win rate
        wins = conn.execute("SELECT COUNT(*) as c FROM demo_trades WHERE result='win'").fetchone()["c"]
        losses = conn.execute("SELECT COUNT(*) as c FROM demo_trades WHERE result='loss'").fetchone()["c"]
        pending = conn.execute("SELECT COUNT(*) as c FROM demo_trades WHERE result='pending'").fetchone()["c"]
        resolved = wins + losses
        if resolved > 0:
            wr = wins / resolved * 100
            print(f"\n  Win rate: {wr:.1f}% ({wins}W / {losses}L / {pending} pending)")
        
        # By strategy
        rows = conn.execute(
            "SELECT strategy, COUNT(*) as c, SUM(pnl) as total_pnl, "
            "SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins "
            "FROM demo_trades WHERE result != 'pending' "
            "GROUP BY strategy ORDER BY total_pnl DESC"
        ).fetchall()
        if rows:
            print(f"\n  By strategy:")
            for r in rows:
                strat = r["strategy"] or "unknown"
                wr = r["wins"] / r["c"] * 100 if r["c"] > 0 else 0
                print(f"    {strat:8s}: {r['c']:4d} trades | {wr:5.1f}% win | PnL: ${r['total_pnl']:+.2f}")
        
        # Recent trades
        rows = conn.execute(
            "SELECT market_question, side, entry_price, result, pnl, strategy, created_at "
            "FROM demo_trades ORDER BY created_at DESC LIMIT 10"
        ).fetchall()
        print(f"\n  Last 10 trades:")
        for r in rows:
            q = (r["market_question"] or "")[:60]
            print(f"    {r['result']:8s} | {r['side']:3s} @{r['entry_price']:.2f} | "
                  f"PnL ${r['pnl']:+.2f} | {r['strategy'] or '-':6s} | {q}")
        
        # PnL over time (by day)
        rows = conn.execute(
            "SELECT date(created_at) as day, COUNT(*) as trades, "
            "SUM(pnl) as daily_pnl, "
            "SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins "
            "FROM demo_trades WHERE result != 'pending' "
            "GROUP BY date(created_at) ORDER BY day"
        ).fetchall()
        if rows:
            print(f"\n  Daily PnL:")
            cumulative = 0.0
            for r in rows:
                cumulative += (r["daily_pnl"] or 0)
                wr = r["wins"] / r["trades"] * 100 if r["trades"] > 0 else 0
                print(f"    {r['day']}: {r['trades']:3d} trades | {wr:5.1f}% win | "
                      f"PnL ${r['daily_pnl']:+.2f} | Cumulative: ${cumulative:+.2f}")
        
        # Entry price distribution
        rows = conn.execute(
            "SELECT "
            "  CASE WHEN entry_price < 0.20 THEN '<0.20' "
            "       WHEN entry_price < 0.30 THEN '0.20-0.30' "
            "       WHEN entry_price < 0.40 THEN '0.30-0.40' "
            "       WHEN entry_price < 0.50 THEN '0.40-0.50' "
            "       ELSE '>=0.50' END as bucket, "
            "COUNT(*) as c, SUM(pnl) as total_pnl "
            "FROM demo_trades GROUP BY bucket ORDER BY bucket"
        ).fetchall()
        if rows:
            print(f"\n  Entry price distribution:")
            for r in rows:
                print(f"    {r['bucket']:12s}: {r['c']:4d} trades | PnL: ${r['total_pnl']:+.2f}")
    
    # --- trades table (real/proposed trades) ---
    if "trades" in tables:
        print(f"\n--- trades (legacy/real) ---")
        total = conn.execute("SELECT COUNT(*) as c FROM trades").fetchone()["c"]
        print(f"  Total: {total}")
        rows = conn.execute(
            "SELECT status, COUNT(*) as c FROM trades GROUP BY status"
        ).fetchall()
        for r in rows:
            print(f"    {r['status']:15s}: {r['c']}")
        
        # Check outcomes
        if "outcomes" in tables:
            out_total = conn.execute("SELECT COUNT(*) as c FROM outcomes").fetchone()["c"]
            print(f"\n  Outcomes: {out_total}")
            if out_total > 0:
                rows = conn.execute(
                    "SELECT result, COUNT(*) as c, SUM(pnl) as total_pnl "
                    "FROM outcomes GROUP BY result"
                ).fetchall()
                for r in rows:
                    print(f"    {r['result']:10s}: {r['c']:4d} | PnL: ${r['total_pnl']:+.2f}")
    
    # --- calibration ---
    if "calibration" in tables:
        print(f"\n--- calibration ---")
        total = conn.execute("SELECT COUNT(*) as c FROM calibration WHERE correct IS NOT NULL").fetchone()["c"]
        if total > 0:
            correct = conn.execute("SELECT COUNT(*) as c FROM calibration WHERE correct=1").fetchone()["c"]
            print(f"  Accuracy: {correct/total*100:.1f}% ({correct}/{total})")
    
    # --- pipeline runs ---
    if "pipeline_runs" in tables:
        runs = conn.execute("SELECT COUNT(*) as c FROM pipeline_runs").fetchone()["c"]
        print(f"\n--- pipeline_runs: {runs} total ---")
        rows = conn.execute(
            "SELECT status, COUNT(*) as c, SUM(trades_placed) as trades "
            "FROM pipeline_runs GROUP BY status"
        ).fetchall()
        for r in rows:
            print(f"    {r['status']:12s}: {r['c']:4d} runs | {r['trades'] or 0} trades placed")
    
    # --- demo_runs ---
    if "demo_runs" in tables:
        runs = conn.execute("SELECT COUNT(*) as c FROM demo_runs").fetchone()["c"]
        print(f"\n--- demo_runs: {runs} total ---")
        rows = conn.execute(
            "SELECT status, COUNT(*) as c, SUM(trades) as total_trades "
            "FROM demo_runs GROUP BY status"
        ).fetchall()
        for r in rows:
            print(f"    {r['status']:12s}: {r['c']:4d} runs | {r['total_trades'] or 0} trades")
    
    conn.close()

def check_railway_api():
    """Check Railway live API."""
    import urllib.request
    import urllib.error
    
    url = "https://industrious-blessing-production-b110.up.railway.app/api/stats"
    print(f"\n{'='*70}")
    print(f"  RAILWAY LIVE API: {url}")
    print(f"{'='*70}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "profit-check/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            print(json.dumps(data, indent=2))
    except Exception as e:
        print(f"  ERROR: {e}")

if __name__ == "__main__":
    os.chdir(Path(__file__).parent.parent)
    print("POLYMARKET PIPELINE — PROFIT ANALYSIS")
    print("=" * 70)
    
    for db in DB_FILES:
        check_db(db)
    
    check_railway_api()
    
    print(f"\n{'='*70}")
    print("  ANALYSIS COMPLETE")
    print(f"{'='*70}")