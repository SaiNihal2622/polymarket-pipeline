"""Check outcomes table and trade status directly."""
import httpx
import json

RAILWAY_URL = "https://industrious-blessing-production-b110.up.railway.app"

# Check API endpoints
for endpoint in ["/api/trades", "/api/stats", "/api/resolved"]:
    try:
        r = httpx.get(f"{RAILWAY_URL}{endpoint}", timeout=15, follow_redirects=True)
        print(f"\n=== {endpoint} (status={r.status_code}) ===")
        if r.status_code == 200:
            data = r.json()
            print(json.dumps(data, indent=2, default=str)[:3000])
    except Exception as e:
        print(f"{endpoint}: {e}")