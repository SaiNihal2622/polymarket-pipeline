#!/usr/bin/env python3
"""
Show trade stats - displays dry-run trades and their status.
Run this to see current trade statistics.
"""
from logger import _conn


def show_stats():
    """Show trade stats."""
    conn = _conn()
    
    # Total trades
    total = conn.execute("SELECT COUNT(*) as c FROM trades").fetchone()["c"]
    dry_run = conn.execute("SELECT COUNT(*) as c FROM trades WHERE status='dry_run'").fetchone()["c"]
    executed = conn.execute("SELECT COUNT(*) as c FROM trades WHERE status='executed'").fetchone()["c"]
    
    print("=== TRADE STATS ===")
    print(f"Total trades: {total}")
    print(f"Dry-run: {dry_run}")
    print(f"Live executed: {executed}")
    
    # Calibration stats
    calibrated = conn.execute("SELECT COUNT(*) as c FROM calibration WHERE correct IS NOT NULL").fetchone()["c"]
    
    if calibrated > 0:
        correct = conn.execute("SELECT COUNT(*) as c FROM calibration WHERE correct = 1").fetchone()["c"]
        accuracy = correct / calibrated * 100
        print(f"\n=== ACCURACY ===")
        print(f"Resolved trades: {calibrated}")
        print(f"Correct: {correct}")
        print(f"Accuracy: {accuracy:.1f}%")
    else:
        print(f"\nNo resolved trades yet (markets haven't closed)")
        print("The bot is generating dry-run signals.")
        print("Accuracy will be tracked once markets resolve.")
    
    # Show recent trades
    print(f"\n=== RECENT TRADES ===")
    trades = conn.execute('''
        SELECT market_question, side, amount_usd, status, created_at
        FROM trades ORDER BY created_at DESC LIMIT 10
    ''').fetchall()
    
    for t in trades:
        print(f"  {t['side']} ${t['amount_usd']:.2f} on {t['market_question'][:40]}...")
    
    conn.close()


if __name__ == "__main__":
    show_stats()
