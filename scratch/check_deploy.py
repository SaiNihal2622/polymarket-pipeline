import urllib.request

urls = [
    "https://industrious-blessing-production-b110.up.railway.app/",
    "https://industrious-blessing-production-b110.up.railway.app/api/stats",
    "https://industrious-blessing-production-b110.up.railway.app/api/trades",
]

for url in urls:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=10)
        data = resp.read().decode("utf-8", errors="replace")
        print(f"\n=== {url} ===")
        print(f"Status: {resp.status}")
        print(data[:1500])
    except Exception as e:
        print(f"\n=== {url} ===")
        print(f"Error: {e}")