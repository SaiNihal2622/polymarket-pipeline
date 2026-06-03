#!/usr/bin/env python3
"""Check trade status in local DB and verify resolution on Polymarket."""
import sqlite3
from pathlib import Path
import httpx
import json

# Check local DB
db = Path("trades.db")
if not db.exists():
    print("No local trades.db found")
    exit()

conn = sqlite3.connect("trades.db")
conn.row_factory = sqlite3.Row

# Get all trades
rows = conn.execute(
    "SELECT id, market_id, market_question, side, amount_usd, market_price, "
    "status, token_id, end_date_iso, created_at FROM trades ORDER BY id DESC LIMIT 30"
).fetchall()
print(f"=== Local trades ({len(rows)} found) ===")
for r in rows:
    print(
        f"#{r['id']} | {r['market_question'][:60]} | side={r['side']} | "
        f"price={r['market_price']} | status={r['status']} | mid={str(r['market_id'])[:40]}"
    )

# Check outcomes
outcomes = conn.execute("SELECT * FROM outcomes ORDER BY id DESC LIMIT 10").fetchall()
print(f"\n=== Outcomes ({len(outcomes)} found) ===")
for o in outcomes:
    print(f"trade_id={o['trade_id']} | result={o['result']} | pnl={o['pnl']} | resolved_at={o['resolved_at']}")

# Get pending (unresolved) trades
pending = conn.execute(
    "SELECT t.id, t.market_id, t.market_question, t.side, t.amount_usd, "
    "t.market_price, t.token_id, t.end_date_iso "
    "FROM trades t LEFT JOIN outcomes o ON t.id = o.trade_id "
    "WHERE t.status IN ('demo','dry_run') AND o.id IS NULL AND t.market_id != '' "
    "ORDER BY t.created_at ASC"
).fetchall()
print(f"\n=== Pending trades ({len(pending)} found) ===")

GAMMA_API = "https://gamma-api.polymarket.com"

for t in pending:
    mid = t["market_id"]
    question = t["market_question"]
    token_id = t["token_id"] or ""
    print(f"\n--- #{t['id']}: {question[:70]} ---")
    print(f"    side={t['side']} amount=${t['amount_usd']} market_price={t['market_price']}")
    print(f"    market_id={mid} token_id={str(token_id)[:30]}...")

    # Try Gamma API
    try:
        # Method 1: conditionId
        r = httpx.get(
            f"{GAMMA_API}/markets",
            params={"conditionId": mid, "limit": 1},
            timeout=10, verify=False,
        )
        if r.status_code == 200:
            data = r.json()
            items = data if isinstance(data, list) else data.get("data", [])
            if items:
                m = items[0]
                print(f"    [Gamma conditionId] question={m.get('question','')[:60]}")
                print(f"    resolved={m.get('resolved')} closed={m.get('closed')}")
                print(f"    resolvedOutcome={m.get('resolvedOutcome')}")
                print(f"    resolutionPrice={m.get('resolutionPrice')}")
                op = m.get("outcomePrices", "")
                if op:
                    print(f"    outcomePrices={op}")
            else:
                print(f"    [Gamma conditionId] No results")
    except Exception as e:
        print(f"    [Gamma conditionId] Error: {e}")

    # Method 2: By token_id
    if token_id and len(str(token_id)) > 50:
        try:
            r = httpx.get(
                f"{GAMMA_API}/markets",
                params={"clob_token_ids": f'["{token_id}"]', "limit": 3},
                timeout=10, verify=False,
            )
            if r.status_code == 200:
                data = r.json()
                items = data if isinstance(data, list) else data.get("data", [])
                if items:
                    m = items[0]
                    print(f"    [Gamma token_id] question={m.get('question','')[:60]}")
                    print(f"    resolved={m.get('resolved')} closed={m.get('closed')}")
                    print(f"    resolvedOutcome={m.get('resolvedOutcome')}")
                    op = m.get("outcomePrices", "")
                    if op:
                        print(f"    outcomePrices={op}")
                else:
                    print(f"    [Gamma token_id] No results")
        except Exception as e:
            print(f"    [Gamma token_id] Error: {e}")

    # Method 3: By question search
    try:
        r = httpx.get(
            f"{GAMMA_API}/markets",
            params={"question": question[:80], "limit": 3, "closed": "true"},
            timeout=10, verify=False,
        )
        if r.status_code == 200:
            data = r.json()
            items = data if isinstance(data, list) else data.get("data", [])
            if items:
                m = items[0]
                print(f"    [Gamma search] question={m.get('question','')[:60]}")
                print(f"    resolved={m.get('resolved')} closed={m.get('closed')}")
                print(f"    resolvedOutcome={m.get('resolvedOutcome')}")
                op = m.get("outcomePrices", "")
                if op:
                    print(f"    outcomePrices={op}")
            else:
                print(f"    [Gamma search] No closed results")
    except Exception as e:
        print(f"    [Gamma search] Error: {e}")

conn.close()