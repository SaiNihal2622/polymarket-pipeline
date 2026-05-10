import urllib.request, json
r = urllib.request.urlopen("https://demo-runner-production-3f90.up.railway.app/api/trades", timeout=15)
data = json.loads(r.read())
resolved = [t for t in data if t.get("result") in ("win", "loss")]
print(f"Resolved trades: {len(resolved)}")
for t in resolved:
    tid = t.get("id", "?")
    side = t.get("side", "?")
    dur = t.get("resolution_duration", "")
    exp = t.get("expected_profit", 0)
    pnl = t.get("pnl", 0)
    print(f"  #{tid} {side} dur={dur} exp=${exp:.2f} pnl=${pnl:.2f}")

has_dur = sum(1 for t in resolved if t.get("resolution_duration"))
has_exp = sum(1 for t in data if t.get("expected_profit"))
print(f"\nWith resolution_duration: {has_dur}/{len(resolved)}")
print(f"With expected_profit: {has_exp}/{len(data)}")