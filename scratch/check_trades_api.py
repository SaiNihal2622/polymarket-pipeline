import httpx, json

try:
    r = httpx.get('https://polymarket-pipeline-production.up.railway.app/api/trades', timeout=15, verify=False)
    data = r.json()
    trades = data.get('trades', [])
    print(f'Total trades: {len(trades)}')
    for t in trades:
        tid = t.get('id', '?')
        side = t.get('side', '?')
        status = t.get('status', '?')
        result = t.get('result', '?')
        q = str(t.get('market_question', ''))[:80]
        mid = t.get('market_id', '')[:60]
        tok = str(t.get('token_id', ''))[:60]
        amt = t.get('amount_usd', 0)
        price = t.get('market_price', 0)
        strat = t.get('strategy', '')
        edge = t.get('edge', 0)
        created = t.get('created_at', '')
        
        print(f'#{tid} | side={side} | status={status} | result={result}')
        print(f'  q={q}')
        print(f'  market_id={mid}')
        print(f'  token_id={tok}')
        print(f'  amount=${amt} price={price} strategy={strat} edge={edge}')
        print(f'  created={created}')
        print()
except Exception as e:
    print(f'Error: {e}')