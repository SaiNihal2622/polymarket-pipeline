#!/usr/bin/env python3
"""Check Polymarket resolution - alternative search."""
import httpx
import json

GAMMA_API = "https://gamma-api.polymarket.com"

trades = [
    {"id": 253, "question": "Will Houston Dash win on 2026-05-20?", "side": "YES", "entry": 0.2},
    {"id": 237, "question": "Will Team Falcons win DreamLeague Season 29?", "side": "YES", "entry": 0.309},
]

for t in trades:
    print(f"\n{'='*60}")
    print(f"Trade #{t['id']}: {t['question']}")
    print(f"{'='*60}")
    
    # Try text_query search
    keywords = t["question"].split()
    search_phrases = [
        t["question"][:80],
        " ".join(keywords[:6]),
        " ".join(keywords[:4]),
    ]
    
    found = False
    for phrase in search_phrases:
        if found:
            break
        for endpoint in ["/markets"]:
            try:
                r = httpx.get(
                    f"{GAMMA_API}{endpoint}",
                    params={"_q": phrase, "limit": 10, "closed": "true"},
                    timeout=15,
                    verify=False
                )
                if r.status_code == 200:
                    data = r.json()
                    items = data if isinstance(data, list) else data.get("data", [])
                    if items:
                        print(f"  Search '{phrase}' found {len(items)} results")
                    for m in items[:3]:
                        mq = m.get("question", "")
                        # Check if it's a relevant match
                        if any(w.lower() in mq.lower() for w in ["Houston", "Falcons", "Dash", "DreamLeague"]):
                            print(f"\n  MATCH: {mq}")
                            print(f"    resolved: {m.get('resolved')}")
                            print(f"    resolvedOutcome: {m.get('resolvedOutcome')}")
                            print(f"    resolutionPrice: {m.get('resolutionPrice')}")
                            print(f"    outcomePrices: {m.get('outcomePrices')}")
                            print(f"    closed: {m.get('closed')}")
                            print(f"    active: {m.get('active')}")
                            print(f"    outcomes: {m.get('outcomes')}")
                            found = True
            except Exception as e:
                print(f"  Error with {endpoint}: {e}")
    
    if not found:
        print("  NOT FOUND via Gamma API search")
        # Try slug-based
        slug = t["question"].lower().replace(" ", "-").replace("?", "").replace(",", "")[:60]
        print(f"  Trying slug: {slug}")
        try:
            r = httpx.get(f"{GAMMA_API}/markets", params={"slug": slug}, timeout=15, verify=False)
            if r.status_code == 200:
                data = r.json()
                items = data if isinstance(data, list) else data.get("data", [])
                for m in items:
                    print(f"  Found via slug: {m.get('question')} resolved={m.get('resolved')} resolvedOutcome={m.get('resolvedOutcome')}")
        except Exception as e:
            print(f"  Slug error: {e}")