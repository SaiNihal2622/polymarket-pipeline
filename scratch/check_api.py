import urllib.request, json
url = "https://demo-runner-production-3f90.up.railway.app/api/trades"
try:
    with urllib.request.urlopen(url, timeout=10) as resp:
        data = json.loads(resp.read())
    print("=== ALL TRADES ===")
    for t in data[:10]:
        tid = t.get("id", "?")
        ep = t.get("expected_profit", "N/A")
        rd = t.get("resolution_duration", "N/A")
        ttr = t.get("time_to_resolve", "N/A")
        result = t.get("result", "N/A")
        q = (t.get("market_question") or "")[:40]
        print(f"  #{tid}: {q} | result={result} | ep={ep} | dur={rd} | ttr={ttr}")
    
    print("\n=== RESOLVED TRADES ===")
    resolved = [t for t in data if t.get("result") in ("win", "loss")]
    for t in resolved[:5]:
        tid = t.get("id", "?")
        ep = t.get("expected_profit", "N/A")
        rd = t.get("resolution_duration", "N/A")
        ttr = t.get("time_to_resolve", "N/A")
        result = t.get("result", "?")
        pnl = t.get("pnl", "?")
        q = (t.get("market_question") or "")[:40]
        print(f"  #{tid}: {q} | {result} pnl={pnl} | ep={ep} | dur={rd} | ttr={ttr}")
except Exception as e:
    print(f"Error: {e}")
