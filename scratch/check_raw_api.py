import urllib.request, json
url = "https://demo-runner-production-3f90.up.railway.app/api/trades"
with urllib.request.urlopen(url, timeout=10) as resp:
    data = json.loads(resp.read())

# Show all fields for first resolved trade
resolved = [t for t in data if t.get("result") in ("win", "loss")]
if resolved:
    t = resolved[0]
    print("=== RAW FIELDS FOR RESOLVED TRADE ===")
    for k, v in sorted(t.items()):
        if k != "signals_parsed":
            print(f"  {k}: {v!r}")