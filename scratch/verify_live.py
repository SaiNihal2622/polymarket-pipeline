import urllib.request, json
url = "https://demo-runner-production-3f90.up.railway.app/api/trades"
with urllib.request.urlopen(url, timeout=15) as resp:
    data = json.loads(resp.read())

has_dur = sum(1 for t in data if t.get("resolution_duration"))
has_exp = sum(1 for t in data if t.get("expected_profit"))
print(f"Trades with resolution_duration: {has_dur}/{len(data)}")
print(f"Trades with expected_profit: {has_exp}/{len(data)}")

# Show first resolved trade
resolved = [t for t in data if t.get("result") in ("win", "loss")]
if resolved:
    t = resolved[0]
    print(f"\nResolved trade #{t['id']}:")
    print(f"  resolution_duration: {t.get('resolution_duration')!r}")
    print(f"  expected_profit: {t.get('expected_profit')!r}")
    print(f"  time_to_resolve: {t.get('time_to_resolve')!r}")