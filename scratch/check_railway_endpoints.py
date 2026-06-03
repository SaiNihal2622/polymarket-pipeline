"""Try multiple Railway endpoints to find the trades."""
import urllib.request
import json

base = "https://polymarket-pipeline-production.up.railway.app"
endpoints = ["/trades", "/api/trades", "/api/status", "/api/dashboard", "/api/runs"]

for ep in endpoints:
    url = base + ep
    try:
        resp = urllib.request.urlopen(url, timeout=10)
        data = resp.read().decode()[:300]
        print(f"OK {url}: {data}")
    except urllib.error.HTTPError as e:
        print(f"ERR {url}: HTTP {e.code}")
    except Exception as e:
        print(f"ERR {url}: {e}")