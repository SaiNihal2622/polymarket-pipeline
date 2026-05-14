#!/usr/bin/env python3
"""Check the live Railway deployment for trades, dashboard, and API endpoints."""
import urllib.request
import json

BASE = "https://industrious-blessing-production-b110.up.railway.app"

endpoints = [
    "/",
    "/healthz",
    "/api/summary",
    "/api/trades",
    "/api/news",
    "/api/runs",
    "/api/config",
    "/api/expectations",
    "/api/diagnostics",
    "/api/logs",
]

for ep in endpoints:
    try:
        url = BASE + ep
        resp = urllib.request.urlopen(url, timeout=15)
        data = resp.read().decode('utf-8', errors='ignore')
        content_type = resp.headers.get('Content-Type', '')
        if 'json' in content_type or data.strip().startswith('{') or data.strip().startswith('['):
            try:
                parsed = json.loads(data)
                print(f"\n{ep} [JSON]: {json.dumps(parsed, indent=2)[:2000]}")
            except:
                print(f"\n{ep} [text]: {data[:1000]}")
        else:
            # HTML response - check for key data
            print(f"\n{ep} [HTML, {len(data)} bytes]")
            # Extract key stats
            if 'stat-value' in data:
                import re
                # Find all stat values
                stats = re.findall(r'class="stat-label">(.*?)</span><span class="stat-value[^"]*">(.*?)</span>', data)
                for label, val in stats:
                    print(f"  {label}: {val.strip()}")
            if 'trades' in data.lower():
                # Count trade rows
                rows = data.count('<tr>')
                print(f"  Table rows: {rows}")
    except Exception as e:
        print(f"\n{ep}: ERROR - {e}")