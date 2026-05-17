#!/usr/bin/env python3
"""Find working Polymarket API endpoints."""
import httpx

# Try various Gamma API endpoints
gamma_bases = [
    "https://gamma-api.polymarket.com",
    "https://gamma-api.polymarket.xyz",
    "https://polymarket.com/api",
]
gamma_paths = [
    "/markets",
    "/v1/markets", 
    "/v2/markets",
    "/markets?limit=2",
    "/events",
    "/v1/events",
]

print("=== GAMMA API ENDPOINT DISCOVERY ===")
for base in gamma_bases:
    for path in gamma_paths:
        url = base + path
        try:
            r = httpx.get(url, timeout=10, verify=False)
            if r.status_code == 200:
                data = r.json()
                items = data if isinstance(data, list) else data.get("data", data.get("markets", []))
                print(f"  OK {url} -> {r.status_code} ({len(items)} items, keys={list(data.keys())[:5] if isinstance(data, dict) else 'list'})")
            else:
                print(f"  FAIL {url} -> {r.status_code}")
        except Exception as e:
            print(f"  ERR  {url} -> {e}")

# Try various CLOB API endpoints
clob_bases = [
    "https://clob.polymarket.com",
    "https://clob.polymarket.xyz",
]
clob_paths = [
    "/sampling-markets",
    "/markets",
    "/v1/markets",
    "/books",
    "/v1/books",
    "/markets?limit=2",
    "/",
    "/v1/sampling-markets",
]

print("\n=== CLOB API ENDPOINT DISCOVERY ===")
for base in clob_bases:
    for path in clob_paths:
        url = base + path
        try:
            r = httpx.get(url, timeout=10, verify=False)
            if r.status_code == 200:
                data = r.json()
                print(f"  OK {url} -> {r.status_code} (keys={list(data.keys())[:5] if isinstance(data, dict) else 'list'})")
            elif r.status_code < 500:
                print(f"  FAIL {url} -> {r.status_code}: {r.text[:100]}")
            else:
                print(f"  FAIL {url} -> {r.status_code}")
        except Exception as e:
            print(f"  ERR  {url} -> {e}")

# Try Data API
data_bases = [
    "https://data-api.polymarket.com",
    "https://data-api.polymarket.xyz",
]
data_paths = [
    "/markets",
    "/v1/markets",
    "/",
    "/events",
    "/tokens",
    "/prices-history",
]

print("\n=== DATA API ENDPOINT DISCOVERY ===")
for base in data_bases:
    for path in data_paths:
        url = base + path
        try:
            r = httpx.get(url, timeout=10, verify=False)
            if r.status_code == 200:
                data = r.json()
                items = data if isinstance(data, list) else data.get("data", [])
                print(f"  OK {url} -> {r.status_code} ({len(items) if isinstance(items, list) else 'N/A'} items)")
            elif r.status_code < 500:
                print(f"  FAIL {url} -> {r.status_code}: {r.text[:80]}")
            else:
                print(f"  FAIL {url} -> {r.status_code}")
        except Exception as e:
            print(f"  ERR  {url} -> {e}")

# Try Strapi API 
print("\n=== STRAPI API ENDPOINT DISCOVERY ===")
strapi_urls = [
    "https://strapi-matic.poly.market/markets?limit=2",
    "https://strapi-matic.polymarket.com/markets?limit=2",
    "https://strapi-matic.poly.market/events?limit=2",
]
for url in strapi_urls:
    try:
        r = httpx.get(url, timeout=10, verify=False)
        if r.status_code == 200:
            data = r.json()
            print(f"  OK {url} -> {r.status_code} (keys={list(data.keys())[:5] if isinstance(data, dict) else 'list'})")
        else:
            print(f"  FAIL {url} -> {r.status_code}")
    except Exception as e:
        print(f"  ERR  {url} -> {e}")