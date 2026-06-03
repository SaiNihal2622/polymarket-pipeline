#!/usr/bin/env python3
"""Check Polymarket API for recent cricket/IPL market resolutions."""
import urllib.request
import json

gamma = "https://gamma-api.polymarket.com"

# Search for cricket markets
for tag in ["cricket", "IPL"]:
    try:
        url = f"{gamma}/markets?tag={tag}&limit=10&order=endDate&ascending=false"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            items = data if isinstance(data, list) else data.get("data", [])
            print(f"\nTag={tag}: {len(items)} markets")
            for m in items[:8]:
                q = m.get("question", "")[:70]
                closed = m.get("closed")
                resolved = m.get("resolved")
                outcome = m.get("outcome")
                end_date = m.get("endDate", "")
                slug = m.get("slug", "")
                print(f"  Q: {q}")
                print(f"    closed={closed} resolved={resolved} outcome={outcome} end={end_date}")
                print(f"    slug={slug}")
    except Exception as e:
        print(f"Error with tag={tag}: {e}")

# Also search by recent text
for query in ["Will Team Falcons", "IPL", "Will Royal Challengers", "Will Punjab Kings"]:
    try:
        url = f"{gamma}/markets?limit=5&order=endDate&ascending=false&closed=true"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            items = data if isinstance(data, list) else data.get("data", [])
            # Filter by question containing the query
            matched = [m for m in items if query.lower() in m.get("question", "").lower()]
            if matched:
                print(f"\nSearch '{query}': {len(matched)} matches")
                for m in matched[:3]:
                    q = m.get("question", "")[:70]
                    print(f"  Q: {q}")
                    print(f"    closed={m.get('closed')} resolved={m.get('resolved')} outcome={m.get('outcome')}")
    except Exception as e:
        print(f"Error searching '{query}': {e}")

# Try slug-based search for the specific markets mentioned
slugs = [
    "will-team-falcons-win-dreamleague-season-29",
    "will-royal-challengers-bengaluru-win-ipl-2025",
    "will-punjab-kings-win-ipl-2025",
    "will-mumbai-indians-win-ipl-2025",
    "ipl-2025-winner",
]

for slug in slugs:
    try:
        url = f"{gamma}/markets?slug={slug}&limit=1"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            items = data if isinstance(data, list) else data.get("data", [])
            for m in items[:1]:
                q = m.get("question", "")[:70]
                print(f"\nSlug '{slug}':")
                print(f"  Q: {q}")
                print(f"  closed={m.get('closed')} resolved={m.get('resolved')} outcome={m.get('outcome')}")
                print(f"  resolvedOutcome={m.get('resolvedOutcome')} resolutionPrice={m.get('resolutionPrice')}")
                print(f"  endDate={m.get('endDate')} conditionId={m.get('conditionId','')[:40]}")
    except Exception as e:
        print(f"Error slug={slug}: {e}")