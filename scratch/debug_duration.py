import urllib.request, json
from datetime import datetime
url = "https://demo-runner-production-3f90.up.railway.app/api/trades"
with urllib.request.urlopen(url, timeout=15) as resp:
    data = json.loads(resp.read())
resolved = [t for t in data if t.get("result") in ("win", "loss")]
t = resolved[0]
print("created_at:", repr(t.get("created_at")))
print("resolved_at:", repr(t.get("resolved_at")))
ds = t.get("end_date_iso") or t.get("resolved_at")
ca = t.get("created_at")
if ds and ca:
    cd = datetime.fromisoformat(ds.replace("Z", "+00:00")).replace(tzinfo=None)
    ct = datetime.fromisoformat(ca.replace("Z", "+00:00")).replace(tzinfo=None)
    secs = int((cd - ct).total_seconds())
    print("secs:", secs)