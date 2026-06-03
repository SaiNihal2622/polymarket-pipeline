"""Check trade resolution status from local DB and verify via Gamma API."""
import sqlite3
import json
from pathlib import Path
import urllib.request

# Find the DB
DB_PATH = Path("trades.db")
if not DB_PATH.exists():
    print("No local trades.db found")
    exit(1)

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

# Get all trades with their outcomes
rows = conn.execute("""
    SELECT t.id, t.market_id, t.market_question, t.side, t.status, t.token_id,
           t.market_price, t.amount_usd, t.created_at,
           o.result, o.pnl, o.resolved_at
    FROM trades t
    LEFT JOIN outcomes o ON t.id = o.trade_id
    ORDER BY t.id DESC
    LIMIT 20
""").fetchall()

print(f"Found {len(rows)} trades in local DB:\n")
for r in rows:
    result = r["result"] if r["result"] else "PENDING"
    print(f"  #{r['id']} | {r['market_question'][:65]} | {r['side']} | result={result} | status={r['status']}")
    print(f"         market_id={r['market_id'][:50]}  token_id={str(r['token_id'])[:30]}")
    if r["resolved_at"]:
        print(f"         resolved_at={r['resolved_at']}  pnl=${r['pnl']:.2f}")
    print()

# Now check Gamma API for unresolved trades
unresolved = [r for r in rows if not r["result"]]
print(f"\n--- Checking {len(unresolved)} unresolved trades via Gamma API ---\n")

GAMMA_API = "https://gamma-api.polymarket.com"
for r in unresolved:
    mid = r["market_id"]
    token_id = r["token_id"]
    q = r["market_question"]
    
    print(f"  #{r['id']}: {q[:60]}")
    
    # Try conditionId lookup
    found = False
    try:
        url = f"{GAMMA_API}/markets?conditionId={mid}&limit=1"
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        items = data if isinstance(data, list) else data.get("data", [])
        for m in items:
            resolved = m.get("resolved", False)
            closed = m.get("closed", False)
            resolved_outcome = m.get("resolvedOutcome", "")
            op_raw = m.get("outcomePrices", "")
            print(f"    Gamma: resolved={resolved} closed={closed} resolvedOutcome={resolved_outcome}")
            if op_raw:
                prices = json.loads(op_raw) if isinstance(op_raw, str) else op_raw
                print(f"    outcomePrices: YES={prices[0]}, NO={prices[1]}")
            if resolved and resolved_outcome:
                print(f"    >>> MARKET IS RESOLVED: {resolved_outcome}")
                found = True
            elif resolved:
                yes_p = float(json.loads(op_raw)[0]) if op_raw else 0
                print(f"    >>> RESOLVED (via prices): YES={yes_p}")
                found = True
    except Exception as e:
        print(f"    Error: {e}")
    
    if not found and token_id:
        try:
            url = f"{GAMMA_API}/markets?clob_token_ids=[\"{token_id}\"]&limit=1"
            req = urllib.request.Request(url)
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            items = data if isinstance(data, list) else data.get("data", [])
            for m in items:
                resolved = m.get("resolved", False)
                closed = m.get("closed", False)
                resolved_outcome = m.get("resolvedOutcome", "")
                op_raw = m.get("outcomePrices", "")
                print(f"    Gamma (by token): resolved={resolved} closed={closed} resolvedOutcome={resolved_outcome}")
                if op_raw:
                    prices = json.loads(op_raw) if isinstance(op_raw, str) else op_raw
                    print(f"    outcomePrices: YES={prices[0]}, NO={prices[1]}")
                if resolved:
                    print(f"    >>> MARKET IS RESOLVED: {resolved_outcome or '(check prices)'}")
                    found = True
        except Exception as e:
            print(f"    Error (token): {e}")
    
    if not found:
        print(f"    >>> NOT RESOLVED YET (or cannot find on Gamma)")

conn.close()