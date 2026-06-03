#!/usr/bin/env python3
"""Check raw Gamma API response format via the running Railway server."""
import httpx

# Check the web_dashboard which shows live market data
r = httpx.get("https://industrious-blessing-production-b110.up.railway.app/api/positions", timeout=15)
data = r.json()
print(f"Positions: {data}")

# Check pipeline status for market count
r2 = httpx.get("https://industrious-blessing-production-b110.up.railway.app/api/pipeline_status", timeout=15)
data2 = r2.json()
print(f"\nPipeline status: {data2}")