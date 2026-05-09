import urllib.request, json

d = json.loads(urllib.request.urlopen('https://polymarket-pipeline-production.up.railway.app/api/trades').read())
trades = d.get('trades', [])

wins = sum(1 for t in trades if t.get('status') == 'win')
losses = sum(1 for t in trades if t.get('status') == 'loss')
pending = sum(1 for t in trades if t.get('status') not in ('win', 'loss'))
total = wins + losses

print(f'Total trades in DB: {len(trades)}')
print(f'Resolved: {total} (W:{wins} L:{losses})')
print(f'Pending:  {pending}')
if total > 0:
    print(f'Win Rate: {wins/total*100:.1f}%')
print()

print('=== RESOLVED TRADES ===')
for t in trades:
    if t.get('status') in ('win', 'loss'):
        q = t.get('market_question', '?')[:70]
        tid = t.get('id', '?')
        side = t.get('side', '?')
        outcome = t.get('outcome', '?')
        print(f'  {t["status"].upper():5s} #{tid} {q} (side={side}, outcome={outcome})')

print()
print('=== PENDING TRADES ===')
for t in trades:
    if t.get('status') not in ('win', 'loss'):
        q = t.get('market_question', '?')[:70]
        tid = t.get('id', '?')
        side = t.get('side', '?')
        status = t.get('status', '?')
        print(f'  PEND #{tid} {q} (status={status}, side={side})')