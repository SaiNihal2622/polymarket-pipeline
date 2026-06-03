import urllib.request, json, sys

URLS = [
    "https://polymarket-pipeline-production.up.railway.app/",
    "https://polymarket-pipeline-production.up.railway.app/api/trades",
    "https://polymarket-pipeline-production.up.railway.app/api/stats",
    "https://demo-runner-production-3f90.up.railway.app/api/trades",
    "https://demo-runner-production-3f90.up.railway.app/",
    "https://industrious-blessing-production-b110.up.railway.app/api/trades",
    "https://industrious-blessing-production-b110.up.railway.app/",
]

for url in URLS:
    try:
        r = urllib.request.urlopen(url, timeout=10)
        data = r.read().decode("utf-8", errors="replace")
        print(f"OK {url}")
        print(f"  Status: {r.status}")
        if "json" in r.headers.get("content-type", ""):
            j = json.loads(data)
            if isinstance(j, list):
                print(f"  {len(j)} items")
            elif isinstance(j, dict):
                print(f"  Keys: {list(j.keys())[:10]}")
                if "trades" in j:
                    print(f"  trades: {len(j['trades'])}")
        else:
            print(f"  {data[:200]}")
    except Exception as e:
        print(f"ERR {url}: {e}")
    print()