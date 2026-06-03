#!/usr/bin/env python3
"""Search Polymarket Gamma API for the two resolved trades by question text."""
import urllib.request, json

def search_gamma(question, closed="true"):
    """Search Gamma API by question text."""
    q = urllib.parse.quote(question[:100])
    url = f"https://gamma-api.polymarket.com/markets?question={q}&limit=5"
    if closed:
        url += f"&closed={closed}"
    try:
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        return data if isinstance(data, list) else data.get("data", [])
    except Exception as e:
        print(f"  Error: {e}")
        return []

def search_gamma_text(text):
    """Search Gamma API using text search."""
    q = urllib.parse.quote(text)
    url = f"https://gamma-api.polymarket.com/markets?_q={q}&limit=5"
    try:
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        return data if isinstance(data, list) else data.get("data", [])
    except Exception as e:
        print(f"  Error: {e}")
        return []

print("=" * 70)
print("TRADE #237: Will Team Falcons win DreamLeague Season 29?")
print("=" * 70)

# Search by question
results = search_gamma("Will Team Falcons win DreamLeague Season 29?")
print(f"\n  Gamma search (closed=true): {len(results)} results")
for m in results[:3]:
    q = m.get("question", "")
    print(f"    Q: {q}")
    print(f"    resolved: {m.get('resolved')}, closed: {m.get('closed')}")
    print(f"    resolvedOutcome: {m.get('resolvedOutcome')}")
    print(f"    outcomePrices: {m.get('outcomePrices')}")
    print(f"    conditionId: {m.get('conditionId', '')[:50]}")
    print()

# Search without closed filter
results2 = search_gamma("Will Team Falcons win DreamLeague Season 29?", closed=None)
print(f"  Gamma search (all): {len(results2)} results")
for m in results2[:3]:
    q = m.get("question", "")
    print(f"    Q: {q}")
    print(f"    resolved: {m.get('resolved')}, closed: {m.get('closed')}")
    print(f"    resolvedOutcome: {m.get('resolvedOutcome')}")
    print(f"    outcomePrices: {m.get('outcomePrices')}")
    print(f"    conditionId: {m.get('conditionId', '')[:50]}")
    print()

# Broader search
results3 = search_gamma_text("Team Falcons DreamLeague")
print(f"  Gamma text search: {len(results3)} results")
for m in results3[:3]:
    q = m.get("question", "")
    print(f"    Q: {q}")
    print(f"    resolved: {m.get('resolved')}, closed: {m.get('closed')}")
    print(f"    resolvedOutcome: {m.get('resolvedOutcome')}")
    print(f"    outcomePrices: {m.get('outcomePrices')}")
    print()


print("\n" + "=" * 70)
print("TRADE #253: Will Houston Dash win on 2026-05-20?")
print("=" * 70)

results = search_gamma("Will Houston Dash win on 2026-05-20?")
print(f"\n  Gamma search (closed=true): {len(results)} results")
for m in results[:3]:
    q = m.get("question", "")
    print(f"    Q: {q}")
    print(f"    resolved: {m.get('resolved')}, closed: {m.get('closed')}")
    print(f"    resolvedOutcome: {m.get('resolvedOutcome')}")
    print(f"    outcomePrices: {m.get('outcomePrices')}")
    print(f"    conditionId: {m.get('conditionId', '')[:50]}")
    print()

results2 = search_gamma("Houston Dash", closed=None)
print(f"  Gamma search (Houston Dash, all): {len(results2)} results")
for m in results2[:5]:
    q = m.get("question", "")
    if "dash" in q.lower() or "houston" in q.lower():
        print(f"    Q: {q}")
        print(f"    resolved: {m.get('resolved')}, closed: {m.get('closed')}")
        print(f"    resolvedOutcome: {m.get('resolvedOutcome')}")
        print(f"    outcomePrices: {m.get('outcomePrices')}")
        print()

# Also check what the resolver actually saw - check outcomes table
print("\n" + "=" * 70)
print("CHECKING DB VIA DEPLOYED API")
print("=" * 70)

url = "https://industrious-blessing-production-b110.up.railway.app/api/trades"
resp = urllib.request.urlopen(url, timeout=15)
data = json.loads(resp.read())
trades = data.get("trades", [])

# Show resolved
resolved = [t for t in trades if t.get("result") not in ("pending", None, "")]
for t in resolved:
    print(f"\n  Trade #{t['id']}: {t['market_question']}")
    print(f"  Result: {t['result']}, PnL: {t.get('pnl')}")
    print(f"  Side: {t['side']}, Entry: {t['entry_price']}")
    print(f"  Market ID: {t.get('market_id', 'NONE')}")
    print(f"  Token ID: {t.get('token_id', 'NONE')}")

# Show some pending past close
print(f"\n\n  === PENDING PAST CLOSE ===")
from datetime import datetime, timezone
now = datetime.now(timezone.utc).isoformat()
past = [t for t in trades if t.get("result") == "pending" and t.get("close_time", "") < now]
for t in past[:5]:
    print(f"\n  Trade #{t['id']}: {t['market_question'][:60]}")
    print(f"  close_time: {t.get('close_time')}, entry: {t['entry_price']}")
    print(f"  Market ID: {t.get('market_id', 'NONE')}")
    print(f"  Token ID: {t.get('token_id', 'NONE')}")