import sqlite3

# Check bot.db
print("=== bot.db tables ===")
try:
    con = sqlite3.connect('bot.db')
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print(f"Tables: {tables}")
    for t in tables:
        count = con.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
        print(f"  {t}: {count} rows")
    con.close()
except Exception as e:
    print(f"Error: {e}")

# Check trades.db
print("\n=== trades.db tables ===")
try:
    con = sqlite3.connect('trades.db')
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print(f"Tables: {tables}")
    for t in tables:
        count = con.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
        print(f"  {t}: {count} rows")
    con.close()
except Exception as e:
    print(f"Error: {e}")

# Check if demo_trades exists in trades.db
print("\n=== trades.db demo_trades stats ===")
try:
    con = sqlite3.connect('trades.db')
    con.row_factory = sqlite3.Row
    
    # Overall stats
    stats = con.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) as losses,
            SUM(CASE WHEN result = 'pending' THEN 1 ELSE 0 END) as pending,
            SUM(CASE WHEN result = 'void' THEN 1 ELSE 0 END) as voids,
            SUM(CASE WHEN result = 'push' THEN 1 ELSE 0 END) as pushes,
            COALESCE(SUM(CASE WHEN result != 'pending' THEN pnl ELSE 0 END), 0) as total_pnl
        FROM demo_trades
    """).fetchone()
    
    print(f"Total trades: {stats['total']}")
    print(f"Wins: {stats['wins']}")
    print(f"Losses: {stats['losses']}")
    print(f"Pending: {stats['pending']}")
    print(f"Voids: {stats['voids']}")
    print(f"Pushes: {stats['pushes']}")
    
    resolved = (stats['wins'] or 0) + (stats['losses'] or 0)
    if resolved > 0:
        accuracy = (stats['wins'] or 0) / resolved * 100
        print(f"Accuracy: {accuracy:.1f}%")
    
    print(f"Total PnL: ${stats['total_pnl']:.2f}")
    
    # Recent trades
    print("\n=== Last 20 resolved trades ===")
    recent = con.execute("""
        SELECT id, market_question, side, entry_price, bet_amount, result, pnl, strategy, created_at
        FROM demo_trades 
        WHERE result IN ('win', 'loss', 'push')
        ORDER BY id DESC 
        LIMIT 20
    """).fetchall()
    
    for r in recent:
        print(f"#{r['id']} | {r['result'].upper():4} | ${r['pnl']:+.2f} | {r['side']} @{r['entry_price']:.2f} | {r['strategy']} | {r['market_question'][:60]}")
    
    # Strategy breakdown
    print("\n=== By Strategy ===")
    strats = con.execute("""
        SELECT strategy, 
            COUNT(*) as total,
            SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) as losses,
            SUM(CASE WHEN result='pending' THEN 1 ELSE 0 END) as pending,
            COALESCE(SUM(pnl), 0) as total_pnl
        FROM demo_trades
        GROUP BY strategy
        ORDER BY total_pnl DESC
    """).fetchall()
    
    for s in strats:
        resolved = (s['wins'] or 0) + (s['losses'] or 0)
        acc = (s['wins'] or 0) / resolved * 100 if resolved > 0 else 0
        print(f"{s['strategy']:25} | {s['total']:4} trades | {acc:5.1f}% acc | ${s['total_pnl']:+.2f} | {s['pending']} pending")
    
    con.close()
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()