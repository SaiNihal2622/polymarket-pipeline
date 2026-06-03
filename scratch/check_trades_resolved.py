import urllib.request, json
url = "https://polymarket-pipeline-production.up.railway.app/api/trades"
try:
    with urllib.request.urlopen(url, timeout=15) as resp:
        data = json.loads(resp.read())
    trades = data if isinstance(data, list) else data.get('trades', [])
    print(f"Total trades: {len(trades)}")
    for t in trades:
        q = (t.get('market_question',''))[:55]
        print(f"#{t.get('id','?')} | {t.get('result','?')} | {q} | side={t.get('side','?')} entry={t.get('entry_price','?')} pnl={t.get('pnl','?')} outcome={t.get('market_outcome','?')} cid={t.get('market_id','')[:20]}")
except Exception as e:
    print(f"Error: {e}")