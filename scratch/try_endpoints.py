#!/usr/bin/env python3
"""Try all possible API endpoints on Railway."""
import urllib.request
import json

BASE = "https://industrious-blessing-production-b110.up.railway.app"
paths = [
    "/api/trades", "/trades", "/api/stats", "/stats",
    "/api/dashboard", "/api/data", "/api/summary",
    "/api/pnl", "/api/profits", "/api/resolved",
    "/api/health", "/health", "/api/status",
    "/data", "/api/v1/trades"
]

for p in paths:
    url = BASE + p
    try:
        resp = urllib.request.urlopen(url, timeout=10)
        body = resp.read().decode()
        print(f"  OK {resp.status} {p} ({len(body)} bytes) -> {body[:150]}")
    except urllib.error.HTTPError as e:
        print(f"  ERR {e.code} {p}")
    except Exception as e:
        print(f"  ERR {e} {p}")