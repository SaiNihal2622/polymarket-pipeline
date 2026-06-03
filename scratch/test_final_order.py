"""Final test - post order with all V2 fixes applied."""
import sys, os, json, shutil

# Clear pycache
for root, dirs, files in os.walk("venv/Lib/site-packages/py_order_utils"):
    for d in dirs:
        if d == "__pycache__":
            shutil.rmtree(os.path.join(root, d), ignore_errors=True)
for root, dirs, files in os.walk("venv/Lib/site-packages/py_clob_client"):
    for d in dirs:
        if d == "__pycache__":
            shutil.rmtree(os.path.join(root, d), ignore_errors=True)

sys.path.insert(0, ".")

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
import httpx

# Create client
client = ClobClient(
    host="https://clob.polymarket.com",
    key="0xb0984a253593290e99ff725851929c5bed779805d300aa316b9a368727f5498b",
    chain_id=137,
)
creds = client.derive_api_key()
client.set_api_creds(creds)
print(f"API key: {creds.api_key[:16]}...", flush=True)

# Get market
r = httpx.get("https://gamma-api.polymarket.com/markets?limit=5&active=true&closed=false&order=volume&ascending=false", timeout=10)
markets = r.json()
for m in markets:
    clob_ids = m.get("clobTokenIds", "[]")
    if isinstance(clob_ids, str):
        clob_ids = json.loads(clob_ids)
    if clob_ids and len(clob_ids) >= 1 and len(str(clob_ids[0])) > 10:
        token_id = str(clob_ids[0])
        print(f"Market: {m.get('question', '')[:60]}", flush=True)
        print(f"Token: {token_id[:30]}...", flush=True)
        break

# Create and post order
order_args = OrderArgs(price=0.10, size=0.50, side="BUY", token_id=token_id)
try:
    signed_order = client.create_order(order_args)
    result = client.post_order(signed_order, OrderType.GTC)
    print(f"\n✅ ORDER SUCCESS!", flush=True)
    print(f"Result: {result}", flush=True)
except Exception as e:
    err_msg = str(e)
    print(f"\n❌ Error: {type(e).__name__}: {err_msg[:200]}", flush=True)
    # If it's order_version_mismatch, the signature is wrong
    if "order_version_mismatch" in err_msg:
        print("\nThe signature is still being computed with version=1 domain.", flush=True)
        print("Need to ensure the cached domain_separator is cleared.", flush=True)