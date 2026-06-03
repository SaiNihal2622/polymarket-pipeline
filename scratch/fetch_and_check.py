"""Fetch trades from Railway and verify resolutions against Polymarket."""
import httpx
import json

RAILWAY_URL = "https://industrious-blessing-production-b110.up.railway.app"
GAMMA_API = "https://gamma-api.polymarket.com"

# Fetch all trades
r = httpx.get(f"{RAILWAY_URL}/api/trades", timeout=15, follow_redirects=True)
data = r.json()
trades = data.get("trades", [])

print(f"=== ALL TRADES ({len(trades)}) ===")
for t in trades:
    tid = t.get("id", "?")
    q = t.get("market_question", "")[:70]
    side = t.get("side", "")
    outcome = t.get("outcome", "pending")
    pnl = t.get("pnl", "")
    status = t.get("status", "")
    market_id = t.get("market_id", "")[:50]
    print(f"#{tid} | {q} | side={side} | outcome={outcome} | pnl={pnl} | status={status}")

# Now verify resolved trades against Polymarket
print("\n=== VERIFYING RESOLVED TRADES AGAINST POLYMARKET ===")
resolved = [t for t in trades if t.get("outcome") in ("win", "loss")]
for t in resolved:
    q = t.get("market_question", "")
    market_id = t.get("market_id", "")
    token_id = t.get("token_id", "")
    side = t.get("side", "")
    our_outcome = t.get("outcome", "")
    
    print(f"\n--- #{t['id']}: {q[:80]} ---")
    print(f"  Our result: {our_outcome} (side={side})")
    
    # Try Gamma API
    gamma_result = None
    
    # Try by conditionId
    if market_id:
        try:
            r2 = httpx.get(f"{GAMMA_API}/markets", params={"conditionId": market_id, "limit": 3}, timeout=10)
            if r2.status_code == 200:
                items = r2.json()
                if isinstance(items, dict):
                    items = items.get("data", [])
                for m in items:
                    ro = m.get("resolvedOutcome")
                    op = m.get("outcomePrices")
                    closed = m.get("closed")
                    resolved_flag = m.get("resolved")
                    print(f"  Gamma: question={m.get('question','')[:60]}")
                    print(f"    resolvedOutcome={ro}, outcomePrices={op}, closed={closed}, resolved={resolved_flag}")
                    if ro:
                        gamma_result = ro
        except Exception as e:
            print(f"  Gamma error: {e}")
    
    # Try by token_id
    if not gamma_result and token_id:
        try:
            r2 = httpx.get(f"{GAMMA_API}/markets", params={"clob_token_ids": json.dumps([token_id]), "limit": 3}, timeout=10)
            if r2.status_code == 200:
                items = r2.json()
                if isinstance(items, dict):
                    items = items.get("data", [])
                for m in items:
                    ro = m.get("resolvedOutcome")
                    op = m.get("outcomePrices")
                    closed = m.get("closed")
                    resolved_flag = m.get("resolved")
                    print(f"  Gamma(token): question={m.get('question','')[:60]}")
                    print(f"    resolvedOutcome={ro}, outcomePrices={op}, closed={closed}, resolved={resolved_flag}")
                    if ro:
                        gamma_result = ro
        except Exception as e:
            print(f"  Gamma(token) error: {e}")
    
    # Also check CLOB book
    if token_id:
        try:
            r3 = httpx.get("https://clob.polymarket.com/book-snapshot", params={"token_id": token_id}, timeout=10)
            if r3.status_code == 200:
                book = r3.json()
                bids = book.get("bids", [])
                asks = book.get("asks", [])
                best_bid = float(bids[0]["price"]) if bids else 0
                best_ask = float(asks[0]["price"]) if asks else 1
                print(f"  CLOB: best_bid={best_bid}, best_ask={best_ask}")
            elif r3.status_code == 404:
                print(f"  CLOB: 404 (likely resolved and delisted)")
        except Exception as e:
            print(f"  CLOB error: {e}")

# Check pending trades
print("\n=== PENDING TRADES ===")
pending = [t for t in trades if t.get("outcome") not in ("win", "loss")]
for t in pending:
    q = t.get("market_question", "")[:70]
    print(f"  #{t['id']} | {q} | side={t.get('side')} | status={t.get('status')}")