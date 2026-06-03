#!/usr/bin/env python3
"""Test Gamma API response format from outside India."""
import httpx, json

# Try the Gamma API with different endpoint patterns
endpoints = [
    ("markets (standard)", "https://gamma-api.polymarket.com/markets", {
        "limit": 2, "active": "true", "closed": "false"
    }),
    ("markets (with clob)", "https://gamma-api.polymarket.com/markets", {
        "limit": 2, "active": "true", "closed": "false", "clob": "true"
    }),
]

for name, url, params in endpoints:
    try:
        r = httpx.get(url, params=params, timeout=15, verify=False)
        print(f"\n=== {name} (status={r.status_code}) ===")
        data = r.json()
        items = data if isinstance(data, list) else data.get("data", [])
        if items:
            m = items[0]
            # Print ALL keys
            print(f"All keys: {sorted(m.keys())}")
            # Print token-related fields
            for key in ["clobTokenIds", "tokens", "outcomes", "outcomePrices", 
                       "conditionId", "condition_id", "id", "slug", "question"]:
                val = m.get(key, "MISSING")
                if isinstance(val, str) and len(val) > 100:
                    val = val[:100] + "..."
                print(f"  {key}: {repr(val)}")
        else:
            print("  No items returned")
    except Exception as e:
        print(f"\n=== {name} ERROR: {e} ===")