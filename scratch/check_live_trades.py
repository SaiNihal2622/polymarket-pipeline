#!/usr/bin/env python3
"""Quick check of live trades from Railway deployment."""
import urllib.request
import json

url = "https://polymarket-pipeline-production.up.railway.app/api/trades"
try:
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
        trades = data if isinstance(data, list) else data.get("trades", [])
        print(f"Total trades: {len(trades)}")
        for t in trades:
            tid = t.get("id", "?")
            result = t.get("result", "?")
            question = str(t.get("market_question", ""))[:70]
            side = t.get("side", "?")
            entry = t.get("entry_price", "?")
            pnl = t.get("pnl", "?")
            outcome = t.get("market_outcome", "?")
            resolved_at = t.get("resolved_at", "?")
            token_id = str(t.get("token_id", ""))[:40]
            print(f"ID={tid} | result={result} | question={question} | side={side} | entry={entry} | pnl={pnl} | outcome={outcome} | resolved_at={resolved_at} | token_id={token_id}")
except Exception as e:
    print(f"Error: {e}")