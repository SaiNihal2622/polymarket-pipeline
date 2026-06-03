"""Check what trades the dashboard has and try alternative API lookups."""
import httpx

client = httpx.Client(verify=False, timeout=20, follow_redirects=True)

# Get all trades from dashboard
print("Fetching dashboard data...")
r = client.get("https://polymarket-pipeline-production.up.railway.app/api/dashboard")
print(f"Dashboard status: {r.status_code}")
dash = r.json()
trades = dash.get("recent_trades", [])
print(f"Total trades returned: {len(trades)}")

# Show all trades
for t in trades:
    tid = t.get("id", "?")
    q = t.get("market_question", "")[:60]
    side = t.get("side", "?")
    status = t.get("status", "?")
    result = t.get("result", "?")
    mid = str(t.get("market_id", ""))[:50]
    print(f"  #{tid} | {q} | {side} | status={status} | result={result} | mid={mid}")

# Now try to look up by market_id using the condition ID from the DB
print("\n\n=== Trying to find markets by condition_id hash ===")

# The market_id stored in the DB appears to be a condition_id hash
# Let me try to use the Polymarket CLOB /markets endpoint with proper params
# Try looking up via the Polymarket subgraph or alternative endpoints

# First, let me search for the Houston Dash market
print("\n--- Searching for 'Houston Dash' ---")
try:
    r = client.get("https://gamma-api.polymarket.com/markets", params={
        "limit": 10,
        "active": "false",
        "closed": "true",
    })
    if r.status_code == 200:
        data = r.json()
        items = data if isinstance(data, list) else data.get("data", [])
        print(f"  Got {len(items)} closed markets")
        for m in items:
            q = m.get("question", "")
            if "houston" in q.lower() or "dash" in q.lower() or "falcons" in q.lower() or "virtus" in q.lower():
                print(f"  MATCH: {q}")
                print(f"    resolved: {m.get('resolved')} resolvedOutcome: {m.get('resolvedOutcome')}")
                print(f"    closed: {m.get('closed')} active: {m.get('active')}")
                print(f"    conditionId: {m.get('conditionId')}")
                clob_ids = m.get("clobTokenIds", [])
                print(f"    clobTokenIds: {clob_ids}")
except Exception as e:
    print(f"  Error: {e}")

# Try searching with tag or text
print("\n--- Text search ---")
for keyword in ["Houston Dash", "Falcons Virtus"]:
    try:
        r = client.get("https://gamma-api.polymarket.com/markets", params={
            "limit": 50,
            "active": "false",
        })
        if r.status_code == 200:
            data = r.json()
            items = data if isinstance(data, list) else data.get("data", [])
            for m in items:
                q = m.get("question", "")
                if keyword.split()[0].lower() in q.lower():
                    print(f"  Found: {q[:80]}")
                    print(f"    resolved: {m.get('resolved')} resolvedOutcome: {m.get('resolvedOutcome')}")
                    print(f"    closed: {m.get('closed')}")
    except Exception as e:
        print(f"  Error: {e}")

# Also try looking at the executor.py to understand the market_id format
print("\n\n=== Checking Polymarket CLOB /sampling-markets ===")
try:
    r = client.get("https://clob.polymarket.com/sampling-markets", params={"next_cursor": "LTE="})
    if r.status_code == 200:
        data = r.json()
        print(f"  Got sampling markets: {len(data.get('data', []))} markets")
except Exception as e:
    print(f"  Error: {e}")

client.close()
print("\nDone.")