import time
import urllib.request
import json

print("Waiting 90s for Railway deploy...")
time.sleep(90)
print("Checking...")

r = urllib.request.urlopen("https://demo-runner-production-3f90.up.railway.app/api/trades", timeout=15)
data = json.loads(r.read())

pending = [t for t in data if t.get("result") not in ("win", "loss")]
resolved = [t for t in data if t.get("result") in ("win", "loss")]

dur_pending = sum(1 for t in pending if t.get("resolution_duration"))
exp_pending = sum(1 for t in pending if t.get("expected_profit"))
dur_resolved = sum(1 for t in resolved if t.get("resolution_duration"))
exp_resolved = sum(1 for t in resolved if t.get("expected_profit"))

print(f"\nAll trades: {len(data)}")
print(f"Pending: {len(pending)}  with duration={dur_pending}  with exp_profit={exp_pending}")
print(f"Resolved: {len(resolved)}  with duration={dur_resolved}  with exp_profit={exp_resolved}")

print("\nSample pending:")
for t in pending[:3]:
    print(f"  #{t['id']} side={t['side']} dur='{t.get('resolution_duration','')}' exp=${t.get('expected_profit',0):.2f}")

print("\nSample resolved:")
for t in resolved[:3]:
    print(f"  #{t['id']} side={t['side']} dur='{t.get('resolution_duration','')}' exp=${t.get('expected_profit',0):.2f} result={t['result']}")