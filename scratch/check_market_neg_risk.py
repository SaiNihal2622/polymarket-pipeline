import sys, httpx, os, json
from dotenv import load_dotenv
load_dotenv()

# Check if the Colombia market is neg_risk
token_id = '74636610772409469817718475200152067076720965641263785464662938420699072982790'
proxy = 'https://vercel-proxy-nine-rose.vercel.app'

# Get market info from gamma API
r = httpx.get(f'https://gamma-api.polymarket.com/markets?limit=5', timeout=15)
markets = r.json()
for m in markets[:3]:
    q = m.get('question','')
    nr = m.get('neg_risk', False)
    cid = m.get('condition_id','')[:20]
    print(f"neg_risk={nr} | {q[:60]} | {cid}")

# Check neg_risk for Colombia market
r2 = httpx.get(f'https://gamma-api.polymarket.com/markets?condition_id=0xc6e54956b79ddf6f86', timeout=15)
markets2 = r2.json()
for m in markets2:
    print(f"\nColombia market:")
    print(f"  neg_risk: {m.get('neg_risk', 'N/A')}")
    print(f"  question: {m.get('question', 'N/A')}")
    print(f"  tokens: {json.dumps(m.get('clobTokenIds', []))[:200]}")