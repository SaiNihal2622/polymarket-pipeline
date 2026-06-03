"""Check actual Polymarket resolution status - v2 with better API handling."""
import httpx
import json

client = httpx.Client(verify=False, timeout=20, follow_redirects=True)

# First get the market_ids from Railway DB via dashboard API
print("Fetching dashboard data...")
r = client.get("https://polymarket-pipeline-production.up.railway.app/api/dashboard")
dash = r.json()
trades = dash.get("recent_trades", [])

trades_237 = [t for t in trades if t.get("id") == 237]
trades_253 = [t for t in trades if t.get("id") == 253]

for t in trades_237 + trades_253:
    print(f"\n=== Trade #{t['id']} ===")
    print(f"  Question: {t.get('market_question', '')}")
    print(f"  Side: {t.get('side')}")
    print(f"  Market ID: {t.get('market_id', '')}")
    print(f"  Status: {t.get('status')}")
    print(f"  Result: {t.get('result')}")
    print(f"  Token ID: {t.get('token_id', 'N/A')}")

# Now try to look up via CLOB API with the token_id
print("\n\n=== Checking CLOB API directly ===")
token_ids = {
    253: "28373082635120606118021424956286854584599396750274217026929304464106260845959",
    237: "4856999255589969978948964840039071449805083749417684326208049103686581222913",
}

for tid, token_id in token_ids.items():
    print(f"\n--- Trade #{tid} ---")
    # Try CLOB endpoint
    try:
        r = client.get(f"https://clob.polymarket.com/markets/{token_id}")
        print(f"  CLOB status: {r.status_code}")
        if r.status_code == 200 and r.text.strip():
            data = r.json()
            print(f"  CLOB response keys: {list(data.keys())[:15]}")
            print(f"  condition_id: {data.get('condition_id')}")
            print(f"  active: {data.get('active')}")
            print(f"  closed: {data.get('closed')}")
            print(f"  question: {data.get('question', '')[:80]}")
            # Check tokens array
            tokens = data.get("tokens", [])
            for tok in tokens:
                print(f"    token: outcome={tok.get('outcome')} token_id={str(tok.get('token_id',''))[:30]}")
        elif r.status_code == 404:
            print("  Market not found (404) - may have been resolved/delisted")
        else:
            print(f"  Response: {r.text[:200]}")
    except Exception as e:
        print(f"  Error: {e}")

# Try the Polymarket event resolution endpoint
print("\n\n=== Checking via events API ===")
for tid, token_id in token_ids.items():
    print(f"\n--- Trade #{tid} ---")
    try:
        # Try searching events
        r = client.get("https://gamma-api.polymarket.com/events", params={"limit": 100, "closed": "true"})
        if r.status_code == 200 and r.text.strip():
            events = r.json()
            items = events if isinstance(events, list) else events.get("data", [])
            for evt in items:
                markets = evt.get("markets", [])
                for m in markets:
                    clob_ids = m.get("clobTokenIds", [])
                    if token_id in str(clob_ids):
                        print(f"  FOUND! Event: {evt.get('title', '')[:60]}")
                        print(f"  Market: {m.get('question', '')}")
                        print(f"  resolved: {m.get('resolved')}")
                        print(f"  resolvedOutcome: {m.get('resolvedOutcome')}")
                        break
    except Exception as e:
        print(f"  Error: {e}")

# Also try searching the gamma API with different param names
print("\n\n=== Trying gamma API with token_id as market slug ===")
for tid, token_id in token_ids.items():
    print(f"\n--- Trade #{tid} ---")
    # The market_id in DB might be the condition_id hash
    market_ids_from_dash = []
    for t in trades_237 + trades_253:
        if t.get("id") == tid:
            market_ids_from_dash.append(t.get("market_id", ""))
    
    for mid in market_ids_from_dash:
        if mid:
            print(f"  Trying market_id: {mid[:80]}...")
            try:
                r = client.get(f"https://gamma-api.polymarket.com/markets/{mid}")
                print(f"  Status: {r.status_code}")
                if r.status_code == 200 and r.text.strip():
                    data = r.json()
                    print(f"  Q: {data.get('question', '')}")
                    print(f"  resolved: {data.get('resolved')}")
                    print(f"  closed: {data.get('closed')}")
            except Exception as e:
                print(f"  Error: {e}")

client.close()
print("\nDone.")