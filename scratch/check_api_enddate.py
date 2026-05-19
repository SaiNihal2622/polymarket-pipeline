"""Test fetching end_date from Polymarket API for a condition_id."""
import requests

# Example: fetch markets from gamma API
resp = requests.get("https://gamma-api.polymarket.com/markets?limit=3&active=true", timeout=10)
data = resp.json()
for m in data[:3]:
    print(f"Q: {m.get('question','')[:60]}")
    print(f"  end_date: {m.get('end_date')}")
    print(f"  condition_id: {m.get('condition_id','')[:30]}")
    print()