"""Verify clean dashboard state after wipe."""
import json, urllib.request

BASE = "https://demo-runner-production-3f90.up.railway.app"

# Check trades
print("=== TRADES ===")
data = json.loads(urllib.request.urlopen(f"{BASE}/api/trades", timeout=10).read())
print(f"Total trades: {len(data)}")
if not data:
    print("Clean slate! No trades.")

# Check stats endpoints
for endpoint in ["/api/stats", "/api/health"]:
    try:
        resp = json.loads(urllib.request.urlopen(f"{BASE}{endpoint}", timeout=10).read())
        print(f"\n=== {endpoint} ===")
        print(json.dumps(resp, indent=2)[:500])
    except Exception as e:
        print(f"{endpoint}: {e}")

# Check main page loads
try:
    resp = urllib.request.urlopen(f"{BASE}/", timeout=10)
    html = resp.read().decode()[:300]
    print(f"\n=== Dashboard HTML (first 300 chars) ===")
    print(html)
except Exception as e:
    print(f"Dashboard: {e}")