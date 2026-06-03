"""Verify DB persistence and trade resolution state"""
import sqlite3, os, sys
from pathlib import Path

# Check local DB
local_db = Path(__file__).parent.parent / "trades.db"
railway_db = Path("/data/trades.db")

print("=== DB Path Configuration ===")
for fname in ["resolver.py", "demo_runner.py", "logger.py", "run_both.py", "web_dashboard.py"]:
    fpath = Path(__file__).parent.parent / fname
    if fpath.exists():
        with open(fpath, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                if any(kw in line for kw in ["DB_PATH", "db_path", "/data/", "trades.db", "DATABASE_URL"]):
                    print(f"  {fname}:{i}: {line.rstrip()}")
    else:
        print(f"  {fname}: NOT FOUND")

print(f"\n=== Local DB ({local_db}) ===")
if local_db.exists():
    con = sqlite3.connect(str(local_db))
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print(f"  Tables: {tables}")
    for t in tables:
        try:
            count = con.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
            print(f"  {t}: {count} rows")
        except:
            pass
    
    # Check trades specifically
    if "trades" in tables:
        rows = con.execute("""
            SELECT id, market_question, side, entry_price, market_price, result, 
                   pnl, market_outcome, resolved_at, created_at
            FROM trades ORDER BY id DESC LIMIT 10
        """).fetchall()
        cols = ["id", "question", "side", "entry", "mkt_price", "result", 
                "pnl", "outcome", "resolved_at", "created_at"]
        print(f"\n  Recent trades:")
        for r in rows:
            d = dict(zip(cols, r))
            print(f"    #{d['id']} | {d['result']} | {d['question'][:55]} | "
                  f"side={d['side']} entry={d['entry']} pnl={d['pnl']} | "
                  f"outcome={d['outcome']} | resolved={d['resolved_at']}")
    con.close()
else:
    print("  NOT FOUND")

print(f"\n=== Railway DB ({railway_db}) ===")
if railway_db.exists():
    print("  EXISTS")
else:
    print("  NOT FOUND (expected - only on Railway)")

# Check if resolver.py uses CLOB correctly
print("\n=== Resolver API Usage ===")
with open(Path(__file__).parent.parent / "resolver.py", encoding="utf-8") as f:
    content = f.read()
    
if "gamma-api.polymarket.com" in content:
    print("  Uses Gamma API for resolution")
if "clob.polymarket.com" in content:
    print("  Uses CLOB API for resolution")
if "/markets/" in content:
    print("  Uses /markets/ endpoint")
if "/events/" in content:
    print("  Uses /events/ endpoint")

# Check what the resolver does when Gamma API times out
print("\n=== Resolver Error Handling ===")
lines = content.split('\n')
for i, line in enumerate(lines):
    if 'except' in line.lower() or 'timeout' in line.lower() or 'retry' in line.lower():
        print(f"  L{i+1}: {line.rstrip()}")

print("\n=== Network Test (Polymarket APIs) ===")
import urllib.request, ssl
ctx = ssl.create_default_context()

test_urls = [
    "https://gamma-api.polymarket.com/markets?limit=1",
    "https://clob.polymarket.com/markets?limit=1",
]

for url in test_urls:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        r = urllib.request.urlopen(req, timeout=10, context=ctx)
        print(f"  OK: {url}")
    except Exception as e:
        print(f"  FAIL: {url} -> {e}")