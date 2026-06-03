#!/usr/bin/env python3
"""Check if the 2 resolved trades actually resolved on Polymarket."""
import httpx, sqlite3, json, os
from pathlib import Path
from difflib import SequenceMatcher

httpx_client = httpx.Client(verify=False, timeout=10)

# Check both DBs
for db_name in ['trades.db', 'bot.db']:
    db_path = Path(db_name)
    if not db_path.exists():
        print(f'{db_name}: NOT FOUND')
        continue
    print(f'\n=== {db_name} ===')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    if db_name == 'trades.db':
        rows = conn.execute('''
            SELECT t.id, t.market_question, t.market_id, t.side, t.amount_usd,
                   t.market_price, t.token_id, t.end_date_iso,
                   o.result, o.pnl, o.resolved_at
            FROM trades t
            LEFT JOIN outcomes o ON t.id = o.trade_id
            WHERE o.id IS NOT NULL
            ORDER BY t.id DESC
        ''').fetchall()
        print(f'Resolved trades in trades.db: {len(rows)}')
        for r in rows:
            print(f'  #{r["id"]} | {r["market_question"][:60]} | {r["side"]} | result={r["result"]}')
            print(f'    market_id={r["market_id"]}')
            try:
                resp = httpx_client.get('https://gamma-api.polymarket.com/markets',
                    params={'slug': r['market_id'], 'limit': 1})
                if resp.status_code == 200:
                    data = resp.json()
                    items = data if isinstance(data, list) else data.get('data', [])
                    for m in items:
                        print(f'    Gamma: resolved={m.get("resolved")} resolvedOutcome={m.get("resolvedOutcome")} outcomePrices={m.get("outcomePrices")} closed={m.get("closed")}')
                        break
                    if not items:
                        # Try by question
                        resp2 = httpx_client.get('https://gamma-api.polymarket.com/markets',
                            params={'question': r['market_question'][:100], 'limit': 5})
                        if resp2.status_code == 200:
                            data2 = resp2.json()
                            items2 = data2 if isinstance(data2, list) else data2.get('data', [])
                            for m in items2:
                                q1 = r['market_question'].lower().strip()[:100]
                                q2 = (m.get('question','') or '').lower().strip()[:100]
                                sim = SequenceMatcher(None, q1, q2).ratio()
                                if sim > 0.6:
                                    print(f'    Gamma (q-search sim={sim:.2f}): resolved={m.get("resolved")} resolvedOutcome={m.get("resolvedOutcome")} outcomePrices={m.get("outcomePrices")} closed={m.get("closed")}')
                                    print(f'    Gamma question: {m.get("question","")[:80]}')
                                    break
                else:
                    print(f'    Gamma API status: {resp.status_code}')
            except Exception as e:
                print(f'    Gamma error: {e}')
    else:
        rows = conn.execute('''
            SELECT id, market_question, market_id, side, bet_amount, entry_price,
                   result, pnl, resolved_at, token_id
            FROM demo_trades
            WHERE result != 'pending'
            ORDER BY id DESC
        ''').fetchall()
        print(f'Resolved trades in bot.db: {len(rows)}')
        for r in rows:
            print(f'  #{r["id"]} | {r["market_question"][:60]} | {r["side"]} | result={r["result"]}')
            print(f'    market_id={r["market_id"]}')
            try:
                resp = httpx_client.get('https://gamma-api.polymarket.com/markets',
                    params={'slug': str(r['market_id']), 'limit': 1})
                if resp.status_code == 200:
                    data = resp.json()
                    items = data if isinstance(data, list) else data.get('data', [])
                    for m in items:
                        print(f'    Gamma: resolved={m.get("resolved")} resolvedOutcome={m.get("resolvedOutcome")} outcomePrices={m.get("outcomePrices")} closed={m.get("closed")}')
                        break
                    if not items:
                        resp2 = httpx_client.get('https://gamma-api.polymarket.com/markets',
                            params={'question': r['market_question'][:100], 'limit': 5})
                        if resp2.status_code == 200:
                            data2 = resp2.json()
                            items2 = data2 if isinstance(data2, list) else data2.get('data', [])
                            for m in items2:
                                q1 = r['market_question'].lower().strip()[:100]
                                q2 = (m.get('question','') or '').lower().strip()[:100]
                                sim = SequenceMatcher(None, q1, q2).ratio()
                                if sim > 0.6:
                                    print(f'    Gamma (q-search sim={sim:.2f}): resolved={m.get("resolved")} resolvedOutcome={m.get("resolvedOutcome")} outcomePrices={m.get("outcomePrices")} closed={m.get("closed")}')
                                    print(f'    Gamma question: {m.get("question","")[:80]}')
                                    break
                else:
                    print(f'    Gamma API status: {resp.status_code}')
            except Exception as e:
                print(f'    Gamma error: {e}')
    
    conn.close()

httpx_client.close()