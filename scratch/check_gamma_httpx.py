"""Check Gamma API for resolution status of our two trades using httpx."""
import httpx
import json

GAMMA_API = "https://gamma-api.polymarket.com"

trades_to_check = [
    {"question": "Will Bitcoin hit $111K before June?", "side": "YES", "slug": "will-bitcoin-hit-111k-before-june"},
    {"question": "Will Team Falcons win DreamLeague Season 29?", "side": "YES", "slug": "will-team-falcons-win-dreamleague-season-29"},
]

for t in trades_to_check:
    print(f"\n{'='*60}")
    print(f"Checking: {t['question']}")
    print(f"Bet side: {t['side']}")
    
    # Try slug lookup
    for param in ["slug", "question"]:
        try:
            params = {param: t["slug"] if param == "slug" else t["question"], "limit": 5}
            if param == "question":
                params["closed"] = "true"
            r = httpx.get(f"{GAMMA_API}/markets", params=params, timeout=15)
            print(f"  [{param}] HTTP {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                items = data if isinstance(data, list) else data.get("data", [])
                for m in items[:3]:
                    q = m.get("question", "")
                    resolved = m.get("resolved")
                    closed = m.get("closed")
                    outcome = m.get("outcome", "")
                    resolved_outcome = m.get("resolvedOutcome", "")
                    outcome_prices = m.get("outcomePrices", "")
                    cid = m.get("conditionId", "")[:40]
                    print(f"    Q: {q[:70]}")
                    print(f"    resolved={resolved} closed={closed} outcome={outcome}")
                    print(f"    resolvedOutcome={resolved_outcome}")
                    print(f"    outcomePrices={outcome_prices}")
                    print(f"    cid={cid}")
        except Exception as e:
            print(f"  [{param}] ERROR: {e}")
    
    # Try keyword search
    try:
        keywords = [w for w in t["question"].split() if len(w) > 3 and w.lower() not in {"will", "the", "hit", "before"}]
        search_q = " ".join(keywords[:3])
        r = httpx.get(f"{GAMMA_API}/markets", params={"question": search_q, "limit": 10, "closed": "true"}, timeout=15)
        print(f"  [keyword: '{search_q}'] HTTP {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            items = data if isinstance(data, list) else data.get("data", [])
            for m in items[:5]:
                q = m.get("question", "")
                if any(kw.lower() in q.lower() for kw in ["bitcoin", "111", "falcons", "dreamleague"]):
                    print(f"    *** MATCH: {q}")
                    print(f"    resolved={m.get('resolved')} closed={m.get('closed')}")
                    print(f"    resolvedOutcome={m.get('resolvedOutcome','')}")
                    print(f"    outcomePrices={m.get('outcomePrices','')}")
    except Exception as e:
        print(f"  [keyword] ERROR: {e}")