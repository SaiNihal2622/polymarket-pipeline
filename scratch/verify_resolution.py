import urllib.request, json, urllib.parse

# Search Polymarket for these specific markets to check actual resolution
markets = [
    "Team Falcons DreamLeague Season 29",
    "Trump say Traitor this week",
    "Racing Club de Lens win",
    "CSyD Macara win",
]

GAMMA = "https://gamma-api.polymarket.com"
for q in markets:
    encoded_q = urllib.parse.quote(q)
    url = f"{GAMMA}/markets?closed=true&limit=3&_q={encoded_q}"
    try:
        r = urllib.request.urlopen(url, timeout=10)
        data = json.loads(r.read())
        for m in data[:2]:
            print(f"Q: {q}")
            print(f"  title: {m.get('question', '?')[:80]}")
            print(f"  closed: {m.get('closed')}  resolved: {m.get('resolved')}")
            print(f"  outcome: {m.get('outcome')}  outcomes: {m.get('outcomes')}")
            print(f"  end: {m.get('endDate')}")
            print(f"  id: {m.get('id')}  slug: {m.get('slug')}")
            print()
    except Exception as e:
        print(f"ERR {q}: {e}")