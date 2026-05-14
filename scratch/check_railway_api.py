#!/usr/bin/env python3
"""Try to fetch live data from Railway deployment."""
import json
import urllib.request
import urllib.error

BASE = "https://demo-runner-production-3f90.up.railway.app"

endpoints = [
    "/api/stats",
    "/api/trades", 
    "/api/profits",
    "/api/dashboard",
    "/",
    "/health",
]

for ep in endpoints:
    url = BASE + ep
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read().decode("utf-8", errors="ignore")
            print(f"\n{ep} -> {resp.status}")
            # Try to parse JSON
            try:
                j = json.loads(data)
                print(json.dumps(j, indent=2)[:3000])
            except json.JSONDecodeError:
                print(data[:2000])
    except urllib.error.HTTPError as e:
        print(f"\n{ep} -> HTTP {e.code}")
        try:
            body = e.read().decode("utf-8", errors="ignore")[:500]
            print(f"  Body: {body}")
        except:
            pass
    except Exception as e:
        print(f"\n{ep} -> Error: {e}")