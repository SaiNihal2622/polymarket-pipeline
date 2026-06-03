#!/usr/bin/env python3
"""Check current trades from live deployment and verify Polymarket resolution."""
import httpx
import json
import sys

httpx.verify = False

RAILWAY_URL = "https://polymarket-pipeline-production.up.railway.app"
GAMMA_API = "https://gamma-api.polymarket.com"

def main():
    # Step 1: Fetch trades from deployment
    print("=" * 70)
    print("STEP 1: Fetching trades from live deployment...")
    print("=" * 70)
    try:
        r = httpx.get(f"{RAILWAY_URL}/api/trades", timeout=15, verify=False)
        data = r.json()
        trades = data.get("trades", [])
        print(f"Total trades: {len(trades)}")
        for t in trades:
            tid = t.get("id", "?")
            side = t.get("side", "?")
            status = t.get("status", "?")
            q = str(t.get("market_question", ""))[:60]
            mid = t.get("market_id", "")[:50]
            tok = str(t.get("token_id", ""))[:40]
            amt = t.get("amount_usd", 0)
            price = t.get("market_price", 0)
            result = t.get("result", "pending")
            print(f"\n  #{tid} | side={side} | status={status} | result={result}")
            print(f"    Q: {q}")
            print(f"    market_id: {mid}")
            print(f"    token_id: {tok}")
            print(f"    amount=${amt} price={price}")
    except Exception as e:
        print(f"Error fetching trades: {e}")
        trades = []

    # Step 2: For each unresolved trade, check Polymarket directly
    print("\n" + "=" * 70)
    print("STEP 2: Checking Polymarket resolution status directly...")
    print("=" * 70)

    for t in trades:
        tid = t.get("id", "?")
        q = t.get("market_question", "")
        mid = t.get("market_id", "")
        token_id = t.get("token_id", "")
        side = t.get("side", "YES")
        result = t.get("result", "pending")

        print(f"\n--- Trade #{tid}: {q[:70]} ---")
        print(f"    Side: {side} | Current result: {result}")

        # Check Gamma API
        gamma_resolved = None
        gamma_outcome = None

        # Try by conditionId
        if mid:
            try:
                r = httpx.get(f"{GAMMA_API}/markets",
                    params={"conditionId": mid, "limit": 1},
                    timeout=10, verify=False)
                if r.status_code == 200:
                    data = r.json()
                    items = data if isinstance(data, list) else data.get("data", [])
                    if items:
                        m = items[0]
                        resolved = m.get("resolved", False)
                        closed = m.get("closed", False)
                        resolved_outcome = m.get("resolvedOutcome", "")
                        outcome_prices = m.get("outcomePrices", "")
                        end_date = m.get("endDate", "")

                        print(f"    [Gamma] resolved={resolved} closed={closed}")
                        print(f"    [Gamma] resolvedOutcome='{resolved_outcome}'")
                        print(f"    [Gamma] outcomePrices={outcome_prices}")
                        print(f"    [Gamma] endDate={end_date}")

                        if resolved_outcome:
                            gamma_resolved = True
                            gamma_outcome = resolved_outcome
                        elif outcome_prices:
                            try:
                                prices = json.loads(outcome_prices) if isinstance(outcome_prices, str) else outcome_prices
                                yes_price = float(prices[0])
                                no_price = float(prices[1])
                                if resolved and yes_price >= 0.95:
                                    gamma_resolved = True
                                    gamma_outcome = "Yes"
                                elif resolved and no_price >= 0.95:
                                    gamma_resolved = True
                                    gamma_outcome = "No"
                                else:
                                    print(f"    [Gamma] NOT resolved yet. YES={yes_price:.2f} NO={no_price:.2f}")
                            except Exception as e:
                                print(f"    [Gamma] price parse error: {e}")
                    else:
                        print(f"    [Gamma] No market found for conditionId={mid[:40]}")
            except Exception as e:
                print(f"    [Gamma] Error: {e}")

        # Try by token_id
        if not gamma_resolved and token_id and len(str(token_id)) > 50:
            try:
                r = httpx.get(f"{GAMMA_API}/markets",
                    params={"clob_token_ids": f'["{token_id}"]', "limit": 3},
                    timeout=10, verify=False)
                if r.status_code == 200:
                    data = r.json()
                    items = data if isinstance(data, list) else data.get("data", [])
                    for m in items:
                        resolved = m.get("resolved", False)
                        resolved_outcome = m.get("resolvedOutcome", "")
                        outcome_prices = m.get("outcomePrices", "")
                        closed = m.get("closed", False)
                        mq = m.get("question", "")[:60]
                        print(f"    [Gamma:token] found: '{mq}' resolved={resolved} closed={closed}")
                        print(f"    [Gamma:token] resolvedOutcome='{resolved_outcome}' outcomePrices={outcome_prices}")
                        if resolved_outcome:
                            gamma_resolved = True
                            gamma_outcome = resolved_outcome
                            break
                        elif resolved and outcome_prices:
                            try:
                                prices = json.loads(outcome_prices) if isinstance(outcome_prices, str) else outcome_prices
                                yes_p = float(prices[0])
                                if yes_p >= 0.95:
                                    gamma_resolved = True
                                    gamma_outcome = "Yes"
                                    break
                                elif float(prices[1]) >= 0.95:
                                    gamma_resolved = True
                                    gamma_outcome = "No"
                                    break
                            except:
                                pass
            except Exception as e:
                print(f"    [Gamma:token] Error: {e}")

        # Also try CLOB
        if token_id and len(str(token_id)) > 50:
            try:
                r = httpx.get(f"https://clob.polymarket.com/book-snapshot",
                    params={"token_id": token_id}, timeout=8, verify=False)
                if r.status_code == 200:
                    bdata = r.json()
                    bids = bdata.get("bids", [])
                    asks = bdata.get("asks", [])
                    midpoint = bdata.get("midpoint")
                    last_price = bdata.get("last_trade_price")
                    print(f"    [CLOB] bids={len(bids)} asks={len(asks)} midpoint={midpoint} last_price={last_price}")
                elif r.status_code == 404:
                    print(f"    [CLOB] 404 - market may be resolved/delisted")
                else:
                    print(f"    [CLOB] status={r.status_code}")
            except Exception as e:
                print(f"    [CLOB] Error: {e}")

        # Final verdict
        if gamma_resolved:
            actual = "YES" if str(gamma_outcome).lower() in ("yes", "true", "1") else "NO"
            trade_won = (side == "YES" and actual == "YES") or (side == "NO" and actual == "NO")
            verdict = "WIN" if trade_won else "LOSS"
            print(f"    >>> VERDICT: Market resolved as {actual}. Trade was {side} = {verdict}")
        else:
            print(f"    >>> VERDICT: Market NOT yet resolved on Polymarket")

if __name__ == "__main__":
    main()