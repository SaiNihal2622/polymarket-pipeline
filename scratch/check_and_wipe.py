import json, urllib.request
data = json.loads(urllib.request.urlopen("https://demo-runner-production-3f90.up.railway.app/api/trades", timeout=10).read())
print(f"Total: {len(data)} trades")
print(f"All S8: {all(t.get('strategy')=='S8_rrf_highconv' for t in data)}")
scores = [t['claude_score'] for t in data]
print(f"Score range: {min(scores):.3f} - {max(scores):.3f}")
print(f"Statuses: {set(t.get('status') for t in data)}")
over1 = [t for t in data if t['claude_score'] > 0.95]
print(f"Trades with score >0.95 (bad RRF): {len(over1)}/{len(data)}")