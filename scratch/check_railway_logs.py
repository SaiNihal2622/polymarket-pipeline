import urllib.request, json

url = "https://industrious-blessing-production-b110.up.railway.app/api/logs"
try:
    with urllib.request.urlopen(url, timeout=10) as r:
        data = json.loads(r.read())
        logs = data.get("logs", [])
        print(f"Total log lines: {len(logs)}")
        for line in logs[-30:]:
            print(line)
except Exception as e:
    print(f"Error: {e}")

# Also check /api/health
try:
    with urllib.request.urlopen("https://industrious-blessing-production-b110.up.railway.app/api/health", timeout=10) as r:
        print("\n--- HEALTH ---")
        print(json.loads(r.read()))
except Exception as e:
    print(f"Health error: {e}")