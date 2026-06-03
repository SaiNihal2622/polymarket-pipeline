#!/usr/bin/env python3
"""Check deployed trades status and which should have resolved."""
import urllib.request, json
from datetime import datetime, timezone

url = "https://industrious-blessing-production-b110.up.railway.app/api/trades"
try:
    resp = urllib.request.urlopen(url, timeout=15)
    data = json.loads(resp.read())
    trades = data.get("trades", [])
    total = len(trades)
    pending = sum(1 for t in trades if t.get("result") == "pending")
    won = sum(1 for t in trades if t.get("result") in ("won", "WIN", "win"))
    lost = sum(1 for t in trades if t.get("result") in ("lost", "LOSS", "lost"))
    other = total - pending - won - lost
    print(f"Total: {total}, Pending: {pending}, Won: {won}, Lost: {lost}, Other: {other}")

    # Show non-pending trades
    for t in trades:
        if t.get("result") != "pending":
            print(f"  ID={t['id']} Q={t['market_question'][:60]} result={t['result']} pnl={t.get('pnl',0)}")

    # Show trades that should have closed by now
    now = datetime.now(timezone.utc)
    print(f"\nNow (UTC): {now.isoformat()}")
    expired = []
    for t in trades:
        ct = t.get("close_time", "")
        if ct and ct < now.isoformat() and t.get("result") == "pending":
            expired.append(t)
    print(f"\nTrades past close_time but still pending: {len(expired)}")
    for t in expired:
        print(f"  ID={t['id']} Q={t['market_question'][:70]} close={ct} side={t['side']} entry={t['entry_price']}")
except Exception as e:
    print(f"Error: {e}")