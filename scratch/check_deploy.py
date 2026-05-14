import json, urllib.request
url = "https://demo-runner-production-3f90.up.railway.app/api/trades"
data = json.loads(urllib.request.urlopen(url, timeout=10).read())
print(f"{len(data)} trades loaded")
for t in data[:5]:
    print(f"ID={t['id']}: score={t.get('claude_score')}, edge={t.get('edge')}, strat={t.get('strategy')}, mat={t.get('materiality')}, comp={t.get('composite_score')}")