import requests
import json

# Check Houston Dash trade resolution
markets_to_check = [
    "will-houston-dash-win-on-2026-05-20",
    "will-the-highest-temperature-in-dallas-be-between-76-77f-on-may-20",
]

for slug in markets_to_check:
    print(f"\n=== Checking: {slug} ===")
    try:
        r = requests.get("https://gamma-api.polymarket.com/markets", 
                        params={"slug": slug}, timeout=15)
        d = r.json()
        if isinstance(d, list):
            for m in d:
                print(f"  question: {m.get('question')}")
                print(f"  closed: {m.get('closed')}")
                print(f"  resolved: {m.get('resolved')}")
                print(f"  outcome: {m.get('outcome')}")
                print(f"  endDate: {m.get('endDate')}")
                print(f"  conditionId: {m.get('conditionId', '')[:50]}")
        else:
            print(f"  Response: {json.dumps(d, indent=2)[:500]}")
    except Exception as e:
        print(f"  Error: {e}")

# Also search by keyword
print("\n\n=== Searching by keyword for Houston Dash ===")
try:
    r = requests.get("https://gamma-api.polymarket.com/markets", 
                    params={"closed": "true", "limit": 50, "order": "endDate", "ascending": "false"},
                    timeout=15)
    d = r.json()
    items = d if isinstance(d, list) else d.get('data', [])
    for m in items:
        q = m.get('question', '')
        if 'houston' in q.lower() or 'dash' in q.lower() or 'dallas' in q.lower() and 'temperature' in q.lower():
            print(f"\n  MATCH: {q}")
            print(f"  closed={m.get('closed')} resolved={m.get('resolved')} outcome={m.get('outcome')}")
            print(f"  slug={m.get('slug')}")
            print(f"  endDate={m.get('endDate')}")
except Exception as e:
    print(f"  Error: {e}")

# Search for Dallas temperature
print("\n\n=== Searching for Dallas temperature ===")
try:
    r = requests.get("https://gamma-api.polymarket.com/markets", 
                    params={"limit": 100, "order": "endDate", "ascending": "false", "active": "false"},
                    timeout=15)
    d = r.json()
    items = d if isinstance(d, list) else d.get('data', [])
    for m in items:
        q = m.get('question', '').lower()
        if 'dallas' in q and 'temperature' in q:
            print(f"\n  MATCH: {m.get('question')}")
            print(f"  closed={m.get('closed')} resolved={m.get('resolved')} outcome={m.get('outcome')}")
            print(f"  slug={m.get('slug')}")
except Exception as e:
    print(f"  Error: {e}")