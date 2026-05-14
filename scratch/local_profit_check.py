import sqlite3, os

DB = "bot.db"
if not os.path.exists(DB):
    print(f"ERROR: {DB} not found")
    exit(1)

conn = sqlite3.connect(DB)
c = conn.cursor()

# List all tables
tables = [t[0] for t in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print(f"=== LOCAL bot.db ===")
print(f"Tables: {tables}\n")

for t in tables:
    cnt = c.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
    print(f"  {t}: {cnt} rows")

# Check columns of each table
print("\n=== TABLE SCHEMAS ===")
for t in tables:
    cols = c.execute(f"PRAGMA table_info([{t}])").fetchall()
    print(f"\n{t}: {[col[1] for col in cols]}")

# Check trades table if exists
if "trades" in tables:
    print("\n=== TRADES SAMPLE ===")
    rows = c.execute("SELECT * FROM trades ORDER BY rowid DESC LIMIT 5").fetchall()
    cols = [d[0] for d in c.execute("PRAGMA table_info(trades)")]
    print(f"Columns: {cols}")
    for r in rows:
        print(r)

    print("\n=== TRADE STATS ===")
    total = c.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    resolved = c.execute("SELECT COUNT(*) FROM trades WHERE status='resolved'").fetchone()[0]
    pending = c.execute("SELECT COUNT(*) FROM trades WHERE status='pending'").fetchone()[0]
    print(f"Total trades: {total}")
    print(f"Resolved: {resolved}")
    print(f"Pending: {pending}")

    # Check for PnL
    try:
        pnl = c.execute("SELECT SUM(pnl) FROM trades WHERE pnl IS NOT NULL").fetchone()[0]
        print(f"Total PnL: ${pnl or 0:.4f}")
    except:
        print("No pnl column")

# Check demo_trades
if "demo_trades" in tables:
    print("\n=== DEMO TRADES ===")
    rows = c.execute("SELECT * FROM demo_trades ORDER BY rowid DESC LIMIT 5").fetchall()
    cols = [d[0] for d in c.execute("PRAGMA table_info(demo_trades)")]
    print(f"Columns: {cols}")
    for r in rows:
        print(r)

    total = c.execute("SELECT COUNT(*) FROM demo_trades").fetchone()[0]
    print(f"Total demo trades: {total}")

conn.close()