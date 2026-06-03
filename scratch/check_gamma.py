import urllib.request, json, ssl

ctx = ssl.create_default_context()

# First, let's look at the resolver to understand DB path
print("=== Checking resolver DB path ===")
with open("resolver.py", encoding="utf-8") as f:
    for i, line in enumerate(f, 1):
        if "DB_PATH" in line or "db_path" in line or "/data/" in line or ".db" in line:
            print(f"  L{i}: {line.rstrip()}")

print("\n=== Checking demo_runner DB path ===")
with open("demo_runner.py", encoding="utf-8") as f:
    for i, line in enumerate(f, 1):
        if "DB_PATH" in line or "db_path" in line or "/data/" in line or ".db" in line:
            print(f"  L{i}: {line.rstrip()}")

print("\n=== Checking Gamma API for our trade markets ===")
# Bitcoin 111k in May
slugs = [
    "will-bitcoin-hit-111k-in-may",
    "will-team-falcons-win-dreamleague-season-29",
]

for slug in slugs:
    try:
        url = f"https://gamma-api.polymarket.com/markets?slug={slug}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        r = urllib.request.urlopen(req, timeout=15, context=ctx)
        data = json.loads(r.read())
        items = data if isinstance(data, list) else data.get("data", [])
        if items:
            m = items[0]
            print(f"\nQ: {m.get('question')}")
            print(f"  closed={m.get('closed')} resolved={m.get('resolved')} outcome={m.get('outcome')}")
            print(f"  endDate={m.get('endDate')} volume={m.get('volume')}")
            print(f"  cid={m.get('conditionId','')[:50]}")
        else:
            print(f"\n{slug}: No market found by slug, trying search...")
            url2 = f"https://gamma-api.polymarket.com/markets?limit=5&active=false&closed=true"
            req2 = urllib.request.Request(url2, headers={"User-Agent": "Mozilla/5.0"})
            r2 = urllib.request.urlopen(req2, timeout=15, context=ctx)
            d2 = json.loads(r2.read())
            items2 = d2 if isinstance(d2, list) else d2.get("data", [])
            for m2 in items2:
                q = m2.get("question", "")
                if "bitcoin" in q.lower() or "111" in q or "falcon" in q.lower() or "dreamleague" in q.lower():
                    print(f"  FOUND: {q}")
                    print(f"    closed={m2.get('closed')} resolved={m2.get('resolved')} outcome={m2.get('outcome')}")
                    print(f"    cid={m2.get('conditionId','')[:50]}")
    except Exception as e:
        print(f"\n{slug}: Error - {e}")