#!/usr/bin/env python3
"""Get full dashboard HTML and extract embedded data."""
import urllib.request
import re
import json

BASE = "https://industrious-blessing-production-b110.up.railway.app"

print("Fetching dashboard HTML...")
resp = urllib.request.urlopen(BASE, timeout=15)
html = resp.read().decode()
print(f"HTML length: {len(html)} bytes")

# Look for embedded JSON data
json_patterns = re.findall(r'(?:const|let|var)\s+\w+\s*=\s*(\{.*?\}|\[.*?\]);', html, re.DOTALL)
print(f"\nFound {len(json_patterns)} embedded data blocks")

# Look for fetch/API calls
fetch_patterns = re.findall(r'fetch\(["\']([^"\']+)["\']', html)
print(f"\nFetch URLs found: {fetch_patterns}")

# Look for API endpoint references
api_refs = re.findall(r'/api/\w+', html)
print(f"\nAPI references: {list(set(api_refs))}")

# Look for data= or trades= patterns
data_patterns = re.findall(r'(?:trades|data|stats|pnl|profit)\s*[=:]\s*(\{[^}]{20,}|\[[^\]]{20,})', html, re.IGNORECASE)
print(f"\nData patterns: {len(data_patterns)}")
for i, p in enumerate(data_patterns[:3]):
    print(f"  [{i}]: {p[:300]}")

# Check if the HTML has script that loads data dynamically
scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
print(f"\nScript blocks: {len(scripts)}")
for i, s in enumerate(scripts):
    print(f"\n  Script {i} ({len(s)} chars):")
    # Show first 500 chars of each script
    print(f"  {s[:800]}")
    print("  ...")