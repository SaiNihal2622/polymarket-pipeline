import urllib.request
import json

BASE = "https://polymarket-pipeline-production.up.railway.app"

for endpoint in ["/api/health", "/api/stats", "/api/trades", "/api/profits"]:
    try:
        r = urllib.request.urlopen(f"{BASE}{endpoint}", timeout=15)
        data = json.loads(r.read().decode())
        print(f"✅ {endpoint} → {json.dumps(data, indent=2)[:300]}")
    except Exception as e:
        print(f"❌ {endpoint} → {e}")
    print()