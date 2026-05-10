import urllib.request, json
r = urllib.request.urlopen("https://demo-runner-production-3f90.up.railway.app/api/trades", timeout=15)
data = json.loads(r.read())
pending = [t for t in data if t.get("result") not in ("win", "loss")]
print(f"Pending: {len(pending)}")
for t in pending[:3]:
    print(f"  #{t['id']} created={t.get('created_at','')} res_dur='{t.get('resolution_duration','')}' exp={t.get('expected_profit',0)}")

# Also check if the latest code is deployed by looking at a resolved trade
resolved = [t for t in data if t.get("result") in ("win", "loss")]
if resolved:
    t = resolved[0]
    print(f"\nResolved #{t['id']}: dur='{t.get('resolution_duration','')}' exp={t.get('expected_profit',0)}")