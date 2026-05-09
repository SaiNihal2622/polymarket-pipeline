import urllib.request, json

url = "https://polymarket-pipeline-production.up.railway.app/api/trades"
data = json.loads(urllib.request.urlopen(url, timeout=15).read())
trades = data.get("trades", [])
print(f"Total trades: {len(trades)}")
print()
for t in trades[-5:]:
    print(f"  #{t['id']} {t['market_question'][:70]}")
    print(f"    status={t['status']} strategy={t.get('strategy','?')} price={t.get('market_price','?')} side={t.get('side','?')}")
    print()