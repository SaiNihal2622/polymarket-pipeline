import urllib.request, json

r = urllib.request.urlopen('https://demo-runner-production-3f90.up.railway.app/api/trades', timeout=15)
data = json.loads(r.read())

resolved = [t for t in data if t.get('result') in ('win', 'loss')]
pending = [t for t in data if t.get('result') not in ('win', 'loss')]

print(f"Total: {len(data)}, Resolved: {len(resolved)}, Pending: {len(pending)}")
print(f"\n=== RESOLVED TRADES ({len(resolved)}) ===")
for t in resolved:
    print(f"  #{t['id']} {t['side']} edge={t.get('edge',0):.3f} price={t.get('market_price',0):.3f} "
          f"score={t.get('claude_score',0):.3f} result={t['result']} pnl={t.get('pnl',0):.2f} "
          f"strat={t.get('strategy','')}")

print(f"\n=== PENDING TRADES ({len(pending)}) ===")
for t in pending:
    print(f"  #{t['id']} {t['side']} edge={t.get('edge',0):.3f} price={t.get('market_price',0):.3f} "
          f"score={t.get('claude_score',0):.3f} strat={t.get('strategy','')} "
          f"market={t.get('market_question','')[:60]}")

# Check classification
classifications = {}
for t in data:
    c = t.get('classification', 'unknown')
    classifications[c] = classifications.get(c, 0) + 1
print(f"\nClassifications: {classifications}")

# Check strategies
strategies = {}
for t in data:
    s = t.get('strategy', 'unknown')
    strategies[s] = strategies.get(s, 0) + 1
print(f"Strategies: {strategies}")