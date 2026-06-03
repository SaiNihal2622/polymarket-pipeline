import httpx, json

try:
    r = httpx.get('https://polymarket-pipeline-production.up.railway.app/api/positions', timeout=15, verify=False)
    data = r.json()
    positions = data if isinstance(data, list) else data.get('positions', data.get('data', []))
    print(f'Total positions: {len(positions)}')
    for p in positions:
        print(json.dumps(p, indent=2, default=str)[:500])
        print('---')
except Exception as e:
    print(f'Error: {e}')