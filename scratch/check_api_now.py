#!/usr/bin/env python3
"""Comprehensive API diagnostic test."""
import os, sys
os.environ.setdefault('DB_PATH', './bot.db')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print('='*60)
print('API DIAGNOSTIC TEST')
print('='*60)

# 1. Polymarket CLOB API
print('\n[1] Polymarket CLOB API...')
try:
    import httpx
    r = httpx.get('https://clob.polymarket.com/markets?next_cursor=MA==&limit=1', timeout=15)
    data = r.json()
    print(f'  Status: {r.status_code}')
    if 'data' in data and len(data['data']) > 0:
        print(f'  Markets available: YES (got {len(data["data"])} market)')
    else:
        print(f'  Response: {str(data)[:200]}')
except Exception as e:
    print(f'  ERROR: {e}')

# 2. Gamma API
print('\n[2] Gamma API...')
try:
    r = httpx.get('https://gamma-api.polymarket.com/markets?limit=1&active=true', timeout=15)
    data = r.json()
    print(f'  Status: {r.status_code}')
    if isinstance(data, list) and len(data) > 0:
        print(f'  Markets available: YES ({len(data)} market)')
    else:
        print(f'  Response: {str(data)[:200]}')
except Exception as e:
    print(f'  ERROR: {e}')

# 3. LLM API (NVIDIA)
print('\n[3] NVIDIA LLM API...')
try:
    from classifier import LLMProvider
    llm = LLMProvider()
    print(f'  Provider: {llm.provider}')
    print(f'  Model: {getattr(llm, "model", "unknown")}')
    result = llm.classify('Test: Will Bitcoin reach 100k by end of 2025?', '')
    if result:
        print(f'  Classification: {result.get("direction")} / confidence={result.get("confidence", 0):.2f}')
    else:
        print(f'  Classification: FAILED (returned None)')
except Exception as e:
    print(f'  ERROR: {e}')

# 4. News feeds
print('\n[4] News feeds...')
try:
    from news_stream import fetch_latest_news
    headlines = fetch_latest_news()
    print(f'  Headlines fetched: {len(headlines)}')
    if headlines:
        print(f'  Sample: {headlines[0][:80]}...')
except Exception as e:
    print(f'  ERROR: {e}')

# 5. DB state
print('\n[5] Database state...')
try:
    import sqlite3
    from logger import DB_PATH as _DBP
    conn = sqlite3.connect(str(_DBP))
    conn.row_factory = sqlite3.Row
    total = conn.execute('SELECT COUNT(*) as c FROM trades').fetchone()['c']
    by_status = conn.execute('SELECT status, COUNT(*) as c FROM trades GROUP BY status').fetchall()
    try:
        resolved = conn.execute('SELECT result, COUNT(*) as c FROM outcomes GROUP BY result').fetchall()
    except:
        resolved = []
    conn.close()
    print(f'  DB: {_DBP}')
    print(f'  Total trades: {total}')
    for r in by_status:
        print(f'    Status {r["status"]}: {r["c"]}')
    for r in resolved:
        print(f'    Outcome {r["result"]}: {r["c"]}')
except Exception as e:
    print(f'  ERROR: {e}')

# 6. Market categories
print('\n[6] Market analysis (Gamma active markets)...')
try:
    r = httpx.get('https://gamma-api.polymarket.com/markets?limit=50&active=true&closed=false', timeout=15)
    markets = r.json()
    categories = {}
    sports_count = 0
    for m in markets:
        tags = m.get('tags', [])
        q = m.get('question', '')
        for t in tags:
            categories[t] = categories.get(t, 0) + 1
        if any(w in q.lower() for w in ['cricket', 'ipl', 'match', 'nba', 'nfl', 'premier league', 'champions league']):
            sports_count += 1
    print(f'  Total markets: {len(markets)}')
    print(f'  Sports-type questions: {sports_count}')
    print(f'  Top tags: {dict(sorted(categories.items(), key=lambda x: -x[1])[:10])}')
except Exception as e:
    print(f'  ERROR: {e}')

# 7. Resolver test
print('\n[7] Resolver API test...')
try:
    from resolver import resolve_market_outcome
    # Use a known resolved market to test
    r2 = httpx.get('https://gamma-api.polymarket.com/markets?limit=5&closed=true', timeout=15)
    closed = r2.json()
    if closed:
        m = closed[0]
        cid = m.get('conditionId') or m.get('condition_id', '')
        q = m.get('question', 'unknown')
        print(f'  Testing resolution for: {q[:60]}')
        print(f'  Condition ID: {cid[:20]}...')
        outcome = resolve_market_outcome(cid)
        print(f'  Resolution result: {outcome}')
    else:
        print(f'  No closed markets found')
except Exception as e:
    print(f'  ERROR: {e}')

print('\n' + '='*60)
print('DIAGNOSTIC COMPLETE')
print('='*60)