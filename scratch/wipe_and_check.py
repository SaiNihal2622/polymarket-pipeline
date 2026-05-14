"""Wipe old bad trades and check deploy status."""
import json, urllib.request

BASE = "https://demo-runner-production-3f90.up.railway.app"

# 1. Wipe old bad trades
print("=== WIPING OLD BAD TRADES ===")
try:
    req = urllib.request.Request(f"{BASE}/reset_db", method="POST")
    resp = urllib.request.urlopen(req, timeout=15)
    result = json.loads(resp.read())
    print(f"Wipe result: {result}")
except Exception as e:
    # Try GET fallback
    try:
        resp = urllib.request.urlopen(f"{BASE}/reset_db", timeout=15)
        result = json.loads(resp.read())
        print(f"Wipe result (GET): {result}")
    except Exception as e2:
        print(f"Wipe failed: {e2}")

# 2. Check trades after wipe
print("\n=== TRADES AFTER WIPE ===")
try:
    data = json.loads(urllib.request.urlopen(f"{BASE}/api/trades", timeout=10).read())
    print(f"Total trades: {len(data)}")
    if data:
        for t in data[:3]:
            print(f"  ID={t['id']}: score={t.get('claude_score')}, strat={t.get('strategy')}")
except Exception as e:
    print(f"Check failed: {e}")

# 3. Check accuracy
print("\n=== ACCURACY ===")
try:
    stats = json.loads(urllib.request.urlopen(f"{BASE}/api/accuracy", timeout=10).read())
    print(f"Resolved: {stats.get('total_resolved', 0)}")
    print(f"Wins: {stats.get('wins', 0)}")
    print(f"Losses: {stats.get('losses', 0)}")
    print(f"Accuracy: {stats.get('accuracy_pct', 0):.1f}%")
except Exception as e:
    print(f"Accuracy check failed: {e}")