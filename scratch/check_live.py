import urllib.request, json, sys
url = sys.argv[1] if len(sys.argv) > 1 else "https://industrious-blessing-production-b110.up.railway.app"
# Check stats
try:
    r = urllib.request.urlopen(f"{url}/api/stats", timeout=10)
    stats = json.loads(r.read())
    print("=== STATS ===")
    for k,v in stats.items():
        print(f"  {k}: {v}")
except Exception as e:
    print(f"Stats error: {e}")
# Check trades
try:
    r = urllib.request.urlopen(f"{url}/api/trades", timeout=10)
    trades = json.loads(r.read())
    print(f"\n=== TRADES ({len(trades.get('trades',[]))}) ===")
    for t in trades.get('trades', []):
        print(f"  #{t['id']} {t['market_question'][:60]} | {t['side']} @{t['entry_price']} ${t['bet_amount']} | {t['result']} | score={t['composite_score']}")
except Exception as e:
    print(f"Trades error: {e}")
# Check logs
try:
    r = urllib.request.urlopen(f"{url}/api/logs", timeout=10)
    data = json.loads(r.read())
    logs = data.get('logs', [])
    print(f"\n=== LAST 20 LOGS ({len(logs)} total) ===")
    for l in logs[-20:]:
        if isinstance(l, dict):
            print(f"  {l.get('message','')[:150]}")
        else:
            print(f"  {str(l)[:150]}")
except Exception as e:
    print(f"Logs error: {e}")