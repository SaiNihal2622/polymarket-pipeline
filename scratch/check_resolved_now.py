import requests, json

BASE = "https://industrious-blessing-production-b110.up.railway.app"

# Get all positions
r = requests.get(f"{BASE}/api/positions", timeout=10)
data = r.json()
positions = data.get("positions", [])
print(f"Total positions: {len(positions)}")

# Show all unique position statuses
statuses = set(p.get("position_status") for p in positions)
print(f"Unique statuses: {statuses}")

# Find ended/resolved/won/lost
ended = [p for p in positions if p.get("position_status") != "open"]
print(f"\nNon-open positions: {len(ended)}")
for p in ended:
    print(json.dumps(p, indent=2, default=str))

# Also check /api/trades
r2 = requests.get(f"{BASE}/api/trades", timeout=10)
if r2.status_code == 200:
    trades_data = r2.json()
    trades = trades_data if isinstance(trades_data, list) else trades_data.get("trades", [])
    print(f"\n--- /api/trades: {len(trades)} trades ---")
    for t in trades:
        print(json.dumps(t, indent=2, default=str))
else:
    print(f"\n/api/trades returned {r2.status_code}")

# Check specific markets on Gamma API
# The user mentioned "bitcoin above 111k" and "falcons dreamleague"
# Let's search for recently closed/resolved markets
print("\n--- Checking Gamma API for recently resolved markets ---")
r3 = requests.get(
    "https://gamma-api.polymarket.com/markets",
    params={"closed": "true", "limit": 50, "order": "endDate", "ascending": "false"},
    timeout=10
)
if r3.status_code == 200:
    markets = r3.json()
    if isinstance(markets, dict):
        markets = markets.get("data", [])
    for m in markets:
        q = m.get("question", "")
        resolved = m.get("resolved")
        closed = m.get("closed")
        outcome = m.get("outcome", "")
        # Check for bitcoin or falcons/dreamleague
        if any(kw in q.lower() for kw in ["bitcoin", "111", "falcon", "dreamleague", "dota", "norway", "sweden"]):
            print(f"MATCH: {q}")
            print(f"  resolved={resolved} outcome={outcome} closed={closed}")
            print(f"  cid={m.get('conditionId','')[:40]}")
            print(f"  end={m.get('endDate','')}")
            print()