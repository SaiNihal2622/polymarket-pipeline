"""Check trade resolution status on live Railway deployment."""
import urllib.request
import json

url = "https://polymarket-pipeline-production.up.railway.app/api/dashboard"
try:
    req = urllib.request.Request(url)
    resp = urllib.request.urlopen(req, timeout=12)
    d = json.loads(resp.read())
    trades = d.get("recent_trades", [])
    print(f"Total trades from API: {len(trades)}")
    for t in trades:
        tid = t.get("id", "?")
        q = t.get("market_question", "")[:65]
        side = t.get("side", "?")
        result = t.get("result", "pending")
        status = t.get("status", "?")
        mid = str(t.get("market_id", ""))[:35]
        print(f"  #{tid} | {q} | {side} | result={result} | status={status} | mkt={mid}")
except Exception as e:
    print(f"Error: {e}")