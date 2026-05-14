#!/usr/bin/env python3
"""Check API endpoints and dashboard routes."""
import re

# Dashboard HTML API endpoints
with open("dashboard_live.html", encoding="utf-8", errors="ignore") as f:
    content = f.read()
apis = re.findall(r"fetch\(['\"]([^'\"]+)", content)
print("Dashboard HTML API endpoints:")
for a in apis:
    print(f"  {a}")

# web_dashboard.py routes
with open("web_dashboard.py", encoding="utf-8", errors="ignore") as f:
    wd = f.read()
routes = re.findall(r"@app\.(get|post)\(['\"]([^'\"]+)", wd)
print("\nweb_dashboard.py routes:")
for method, route in routes:
    print(f"  {method.upper()} {route}")

# Check for Railway deployment URL
print("\nChecking .env.example and config for Railway URL...")
with open(".env.example", encoding="utf-8", errors="ignore") as f:
    env = f.read()
urls = re.findall(r"https?://[^\s'\"]+", env)
for u in urls:
    print(f"  {u}")