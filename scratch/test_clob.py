#!/usr/bin/env python3
"""Test CLOB API endpoints."""
import httpx

clob = "https://clob.polymarket.com"
gamma = "https://gamma-api.polymarket.com"
data = "https://data-api.polymarket.com"

# Known CLOB endpoints from py-clob-client
endpoints = [
    # CLOB
    (f"{clob}/sampling-simplified-markets", {}),
    (f"{clob}/simplified-markets", {"limit": 2}),
    (f"{clob}/markets-simplified", {"limit": 2}),
    (f"{clob}/midpoint", {"token_id": "1"}),
    (f"{clob}/price", {"token_id": "1", "side": "buy"}),
    # Gamma
    (f"{gamma}/markets", {"limit": 2, "active": "true"}),
    (f"{gamma}/markets", {"limit": 2}),
    (f"{gamma}/events", {"limit": 2}),
    (f"{gamma}/markets/simplified", {"limit": 2}),
    # Data
    (f"{data}/markets", {"limit": 2}),
    (f"{data}/events", {"limit": 2}),
    (f"{data}/prices-history", {"market": "test", "interval": "max", "fidelity": 60}),
]

for url, params in endpoints:
    try:
        r = httpx.get(url, params=params, timeout=15, verify=False)
        print(f"  {r.status_code} {url}")
        if r.status_code == 200:
            try:
                d = r.json()
                if isinstance(d, list):
                    print(f"       -> list of {len(d)} items")
                elif isinstance(d, dict):
                    print(f"       -> dict keys: {list(d.keys())[:6]}")
            except:
                print(f"       -> text: {r.text[:80]}")
    except Exception as e:
        print(f"  ERR {url} -> {str(e)[:80]}")