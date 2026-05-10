import time
import urllib.request
import json

print("Waiting 120s for Railway build + deploy...")
time.sleep(120)
print("Checking...")

try:
    r = urllib.request.urlopen("https://demo-runner-production-3f90.up.railway.app/api/trades", timeout=15)
    data = json.loads(r.read())
except Exception as e:
    print(f"ERROR: {e}")
    exit(1)

pending = [t for t in data if t.get("result") not in ("win", "loss")]
resolved = [t for t in data if t.get("result") in ("win", "loss")]

dur_pending = sum(1 for t in pending if t.get("resolution_duration"))
exp_pending = sum(1 for t in pending if t.get("expected_profit"))
dur_resolved = sum(1 for t in resolved if t.get("resolution_duration"))
exp_resolved = sum(1 for t in resolved if t.get("expected_profit"))

print(f"\nAll trades: {len(data)}")
print(f"Pending: {len(pending)}  with_duration={dur_pending}  with_exp_profit={exp_pending}")
print(f"Resolved: {len(resolved)}  with_duration={dur_resolved}  with_exp_profit={exp_resolved}")

# Check if pending trades now have "elapsed" in duration
elapsed_count = sum(1 for t in pending if "elapsed" in str(t.get("resolution_duration", "")))
print(f"Pending with 'elapsed' in duration: {elapsed_count}")

print("\nSample pending trades:")
for t in pending[:5]:
    print(f"  #{t['id']} side={t['side']} dur='{t.get('resolution_duration','')}' exp=${t.get('expected_profit',0):.2f}")

print("\nSample resolved trades:")
for t in resolved[:3]:
    print(f"  #{t['id']} side={t['side']} dur='{t.get('resolution_duration','')}' exp=${t.get('expected_profit',0):.2f} result={t['result']}")

# Success criteria
ok = dur_pending > 0 and exp_pending > 0 and dur_resolved > 0 and exp_resolved > 0
print(f"\n{'PASS' if ok else 'FAIL'}: All columns populated")