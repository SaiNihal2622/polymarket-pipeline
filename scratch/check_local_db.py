"""Check local bot.db for trade data."""
import sqlite3

conn = sqlite3.connect('bot.db')
cursor = conn.cursor()

# List tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [t[0] for t in cursor.fetchall()]
print(f"Tables: {tables}")

for table in tables:
    cursor.execute(f"SELECT COUNT(*) FROM {table}")
    count = cursor.fetchone()[0]
    print(f"  {table}: {count} rows")

# Check trades table
if 'trades' in tables:
    cursor.execute("SELECT COUNT(*) FROM trades")
    total = cursor.fetchone()[0]
    print(f"\nTotal trades in local DB: {total}")
    
    # Get schema
    cursor.execute("PRAGMA table_info(trades)")
    cols = [c[1] for c in cursor.fetchall()]
    print(f"Columns: {cols}")
    
    # Group by result
    cursor.execute("SELECT result, COUNT(*), SUM(pnl), SUM(amount_usd) FROM trades GROUP BY result")
    rows = cursor.fetchall()
    print("\nBy result:")
    for r in rows:
        print(f"  {r[0]}: {r[1]} trades, P&L: {r[2]}, Wagered: {r[3]}")
    
    # Total P&L
    cursor.execute("SELECT SUM(pnl), SUM(amount_usd) FROM trades")
    row = cursor.fetchone()
    print(f"\nTotal P&L: {row[0]}, Total Wagered: {row[1]}")
    
    # By strategy
    cursor.execute("SELECT strategy, COUNT(*), SUM(CASE WHEN result='win' THEN 1 ELSE 0 END), SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END), SUM(pnl), SUM(amount_usd) FROM trades GROUP BY strategy ORDER BY SUM(pnl) DESC")
    rows = cursor.fetchall()
    print("\nBy strategy:")
    for r in rows:
        dec = r[2] + r[3]
        wr = f"{r[2]/dec*100:.0f}%" if dec > 0 else "N/A"
        print(f"  {r[0]}: {r[1]} trades | {r[2]}W/{r[3]}L | WR:{wr} | Wagered:{r[5]} | P&L:{r[4]}")
    
    # By date
    cursor.execute("SELECT DATE(created_at), COUNT(*), SUM(CASE WHEN result='win' THEN 1 ELSE 0 END), SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END), SUM(pnl) FROM trades GROUP BY DATE(created_at) ORDER BY DATE(created_at)")
    rows = cursor.fetchall()
    print("\nBy date:")
    for r in rows:
        dec = r[2] + r[3]
        wr = f"{r[2]/dec*100:.0f}%" if dec > 0 else "N/A"
        print(f"  {r[0]}: {r[1]} trades | {r[2]}W/{r[3]}L | WR:{wr} | P&L:{r[4]}")

    # Print ALL trades
    cursor.execute("SELECT created_at, result, side, entry_price, amount_usd, pnl, strategy, market_question FROM trades ORDER BY created_at")
    rows = cursor.fetchall()
    print(f"\n{'='*70}")
    print("ALL TRADES (chronological)")
    print(f"{'='*70}")
    for r in rows:
        sym = "WIN" if r[1] == 'win' else "LOSS" if r[1] == 'loss' else (r[1] or 'PEND')
        q = (r[7] or '')[:55]
        print(f"  [{(r[0] or '')[:16]}] {sym:>4} | {r[2]} @{r[3]:.3f} | bet=${r[4]:.2f} | P&L=${r[5]:+.2f} | {r[6]} | {q}")

conn.close()