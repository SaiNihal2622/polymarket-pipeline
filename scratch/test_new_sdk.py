"""Test the new unified Polymarket SDK (polymarket-client)."""
import os
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

print("Importing polymarket SDK...", flush=True)
from polymarket import PublicClient

# First, check public data works
with PublicClient() as client:
    market = client.get_market(url="https://polymarket.com/event/us-politics")
    print(f"Got market: {market}", flush=True)