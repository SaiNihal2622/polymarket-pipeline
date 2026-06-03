#!/usr/bin/env python3
"""Check Polymarket API using the same approach as the pipeline code."""
import httpx
import json

# Check what endpoints the pipeline uses
# Let's try the correct Gamma API format
print("=== Testing Polymarket API endpoints ===\n")

# 1. Try /markets with different param formats
test_urls = [
    ("https://gamma-api.polymarket.com/markets?limit=3", {}),
    ("https://gamma-api.polymarket.com/markets", {"limit": 3}),
    ("https://gamma-api.polymarket.com/events", {"limit": 3}),
    ("https://gamma-api.polymarket.com/events?limit=3", {}),
]

for url, params in test_urls:
    try:
        r = httpx.get(url, params=params, timeout=10, verify=False)
        print(f"  {url} params={params}: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                print(f"    List of {len(data)} items")
                if data:
                    print(f"    First item keys: {list(data[0].keys())[:10]}")
            elif isinstance(data, dict):
                print(f"    Dict keys: {list(data.keys())[:10]}")
    except Exception as e:
        print(f"  {url}: Error - {e}")

# 2. Try CLOB API
print("\n=== CLOB API ===")
clob_tests = [
    "https://clob.polymarket.com/markets",
    "https://clob.polymarket.com/markets?next_cursor=MA==",
]
for url in clob_tests:
    try:
        r = httpx.get(url, timeout=10, verify=False)
        print(f"  {url}: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            print(f"    Type: {type(data).__name__}")
            if isinstance(data, dict):
                print(f"    Keys: {list(data.keys())[:10]}")
                if "data" in data:
                    print(f"    data length: {len(data['data'])}")
                    if data["data"]:
                        print(f"    First item keys: {list(data['data'][0].keys())[:10]}")
    except Exception as e:
        print(f"  {url}: Error - {e}")

# 3. Try strapi
print("\n=== Strapi API ===")
try:
    r = httpx.get("https://strapi-matic.poly.market/markets?limit=2", timeout=10, verify=False)
    print(f"  strapi: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        print(f"    Type: {type(data).__name__}")
        if isinstance(data, list):
            print(f"    Items: {len(data)}")
        elif isinstance(data, dict):
            print(f"    Keys: {list(data.keys())[:10]}")
except Exception as e:
    print(f"  strapi: Error - {e}")

print("\nDone.")