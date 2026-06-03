#!/usr/bin/env python3
"""Check Gamma API format - look at ALL fields returned."""
import httpx, json

# Use Railway as proxy (India can't reach Gamma directly)
r = httpx.get("https://industrious-blessing-production-b110.up.railway.app/", timeout=15)
print(f"Dashboard status: {r.status_code}")

# Let's check what the Gamma API returns for token IDs
# Use a known working endpoint
r2 = httpx.get(
    "https://gamma-api.polymarket.com/markets",
    params={"limit": 1, "active": "true", "closed": "false"},
    timeout=30,
    verify=False,
)
print(f"Gamma direct status: {r2.status_code}")
print(f"Gamma body: {r2.text[:500]}")