import sqlite3
c = sqlite3.connect('trades.db')
cur = c.cursor()

# Check end_date_iso and market_price
cur.execute("SELECT id, market_price, claude_score, amount_usd, side, end_date_iso, strategy FROM trades ORDER BY id DESC LIMIT 10")
print("Recent trades:")
for r in cur.fetchall():
    print(f"  #{r[0]}: price={r[1]} score={r[2]} amt={r[3]} side={r[4]} end_iso={r[5]} strat={r[6]}")

# Check outcomes table
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print("\nTables:", tables)

if 'outcomes' in tables:
    cur.execute("SELECT * FROM outcomes ORDER BY rowid DESC LIMIT 5")
    cols = [d[0] for d in cur.description]
    print("\nOutcomes columns:", cols)
    for r in cur.fetchall():
        print(dict(zip(cols, r)))
else:
    print("\nNo outcomes table!")

# Check if end_date_iso is ever populated
cur.execute("SELECT COUNT(*) FROM trades WHERE end_date_iso IS NOT NULL AND end_date_iso != ''")
print(f"\nTrades with end_date_iso: {cur.fetchone()[0]}")
cur.execute("SELECT COUNT(*) FROM trades WHERE end_date_iso IS NULL OR end_date_iso = ''")
print(f"Trades without end_date_iso: {cur.fetchone()[0]}")

c.close()