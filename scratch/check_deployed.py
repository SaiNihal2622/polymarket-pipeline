import urllib.request, json, ssl

ctx = ssl.create_default_context()
url = "https://polymarket-pipeline-production.up.railway.app/api/trades"
try:
    r = urllib.request.urlopen(url, timeout=30, context=ctx)
    data = json.loads(r.read())
    trades = data if isinstance(data, list) else data.get("trades", [])
    print(f"Total trades: {len(trades)}")
    for t in trades[:10]:
        tid = t.get("id", "?")
        result = t.get("result", "?")
        q = str(t.get("market_question", "?"))[:60]
        side = t.get("side", "?")
        cid = str(t.get("market_id", "?"))[:30]
        print(f"#{tid} | {result} | {q} | side={side} | cid={cid}")
except Exception as e:
    print(f"Error reaching server: {e}")
    # Try Gamma API directly to check resolution status
    print("\n--- Checking Gamma API directly ---")
    for slug in [
        "will-bitcoin-hit-111k-in-may",
        "will-team-falcons-win-dreamleague-season-29"
    ]:
        try:
            gurl = f"https://gamma-api.polymarket.com/markets?slug={slug}&limit=1"
            gr = urllib.request.urlopen(gurl, timeout=10, context=ctx)
            gdata = json.loads(gr.read())
            items = gdata if isinstance(gdata, list) else gdata.get("data", [])
            for m in items:
                print(f"Q: {m.get('question')}")
                print(f"  closed={m.get('closed')} resolved={m.get('resolved')} outcome={m.get('outcome')}")
                print(f"  endDate={m.get('endDate')} volume={m.get('volume')}")
        except Exception as ge:
            print(f"  Error: {ge}")