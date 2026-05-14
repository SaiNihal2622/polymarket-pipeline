import sqlite3, os

DB = "/data/trades.db"
if not os.path.exists(DB):
    print(f"ERROR: {DB} not found")
    exit(1)

conn = sqlite3.connect(DB)
c = conn.cursor()

tables = [t[0] for t in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print(f"=== REMOTE /data/trades.db ===")
print(f"Tables: {tables}\n")

for t in tables:
    cnt = c.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
    print(f"  {t}: {cnt} rows")

print("\n=== TABLE SCHEMAS ===")
for t in tables:
    cols = c.execute(f"PRAGMA table_info([{t}])").fetchall()
    print(f"\n{t}: {[col[1] for col in cols]}")

# Check ALL trades (any status)
if "trades" in tables:
    print("\n=== ALL TRADES (last 20) ===")
    cols = [d[0] for d in c.execute("PRAGMA table_info(trades)")]
    print(f"Columns: {cols}")
    rows = c.execute("SELECT * FROM trades ORDER BY rowid DESC LIMIT 20").fetchall()
    for r in rows:
        print(r)

    print("\n=== TRADE STATS ===")
    total = c.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    print(f"Total: {total}")
    
    # Check all statuses
    statuses = c.execute("SELECT status, COUNT(*) FROM trades GROUP BY status").fetchall()
    for s in statuses:
        print(f"  status='{s[0]}': {s[1]}")
    
    try:
        pnl = c.execute("SELECT SUM(pnl) FROM trades WHERE pnl IS NOT NULL").fetchone()[0]
        print(f"Total PnL: ${pnl or 0:.4f}")
    except Exception as e:
        print(f"PnL error: {e}")

if "demo_trades" in tables:
    print("\n=== DEMO TRADES (last 20) ===")
    cols = [d[0] for d in c.execute("PRAGMA table_info(demo_trades)")]
    print(f"Columns: {cols}")
    rows = c.execute("SELECT * FROM demo_trades ORDER BY rowid DESC LIMIT 20").fetchall()
    for r in rows:
        print(r)
    
    total = c.execute("SELECT COUNT(*) FROM demo_trades").fetchone()[0]
    print(f"Total demo trades: {total}")

if "demo_runs" in tables:
    print("\n=== DEMO RUNS (last 10) ===")
    cols = [d[0] for d in c.execute("PRAGMA table_info(demo_runs)")]
    print(f"Columns: {cols}")
    rows = c.execute("SELECT * FROM demo_runs ORDER BY rowid DESC LIMIT 10").fetchall()
    for r in rows:
        print(r)

# Check pipeline_runs
if "pipeline_runs" in tables:
    print("\n=== PIPELINE RUNS (last 10) ===")
    rows = c.execute("SELECT * FROM pipeline_runs ORDER BY rowid DESC LIMIT 10").fetchall()
    cols = [d[0] for d in c.execute("PRAGMA table_info(pipeline_runs)")]
    print(f"Columns: {cols}")
    for r in rows:
        print(r)

conn.close()