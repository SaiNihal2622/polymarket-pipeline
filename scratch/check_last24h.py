import sqlite3, os, sys
from pathlib import Path
from datetime import datetime, timedelta

# Check multiple possible DB locations
candidates = [
    Path(__file__).parent.parent / "bot.db",
    Path("bot.db"),
    Path("/data/bot.db"),
    Path("/data/trades.db"),
]

for p in candidates:
    if p.exists() and p.stat().st_size > 0:
        print(f"\n=== Found DB: {p} ({p.stat().st_size} bytes) ===")
        conn = sqlite3.connect(str(p))
        conn.row_factory = sqlite3.Row
        
        # List tables
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        print(f"Tables: {tables}")
        
        # Check each table for last 24h
        cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()
        
        for t in tables:
            try:
                count = conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
                print(f"\n  [{t}] total rows: {count}")
                
                # Try to find a timestamp column
                cols = [r[1] for r in conn.execute(f"PRAGMA table_info([{t}])").fetchall()]
                print(f"  Columns: {cols}")
                
                # Look for time columns
                time_cols = [c for c in cols if 'time' in c.lower() or 'date' in c.lower() or 'created' in c.lower()]
                if time_cols:
                    tc = time_cols[0]
                    recent = conn.execute(f"SELECT COUNT(*) FROM [{t}] WHERE [{tc}] >= ?", (cutoff,)).fetchone()[0]
                    print(f"  Last 24h ({tc} >= {cutoff}): {recent} rows")
                    
                    # Show last 5
                    rows = conn.execute(f"SELECT * FROM [{t}] ORDER BY [{tc}] DESC LIMIT 5").fetchall()
                    for r in rows:
                        print(f"    {dict(r)}")
            except Exception as e:
                print(f"  Error on {t}: {e}")
        
        conn.close()
        break
else:
    print("No non-empty database found locally.")
    print("The trades DB is on Railway's persistent volume (/data/bot.db).")
    print("Let's check the dashboard /diagnostics endpoint instead.")