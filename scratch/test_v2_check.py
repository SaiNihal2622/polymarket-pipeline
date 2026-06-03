"""Quick check that base_builder has version=2."""
import sys, os
# Clear pycache
import shutil
for root, dirs, files in os.walk("venv/Lib/site-packages/py_order_utils"):
    for d in dirs:
        if d == "__pycache__":
            shutil.rmtree(os.path.join(root, d), ignore_errors=True)

import py_order_utils.builders.base_builder as bb
import inspect
src = inspect.getsource(bb.BaseBuilder._get_domain_separator)
print("Domain separator source:", src.strip(), flush=True)
if 'version="2"' in src:
    print("✅ Version is '2' in source", flush=True)
else:
    print("❌ Version is NOT '2' in source!", flush=True)

# Also test order creation
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
import httpx, json

client = ClobClient(
    host="https://clob.polymarket.com",
    key="0xb0984a253593290e99ff725851929c5bed779805d300aa316b9a368727f5498b",
    chain_id=137,
)
creds = client.derive_api_key()
client.set_api_creds(creds)

# Get a real token
r = httpx.get("https://gamma-api.polymarket.com/markets?limit=5&active=true&closed=false&order=volume&ascending=false", timeout=10)
markets = r.json()
token_id = None
for m in markets:
    clob_ids = m.get("clobTokenIds", "[]")
    if isinstance(clob_ids, str):
        clob_ids = json.loads(clob_ids)
    if clob_ids and len(clob_ids) >= 1:
        tid = clob_ids[0]
        if tid and len(str(tid)) > 10:
            token_id = str(tid)
            print(f"\nMarket: {m.get('question', '')[:60]}", flush=True)
            print(f"Token: {token_id[:30]}...", flush=True)
            break

if not token_id:
    print("No token found!", flush=True)
    sys.exit(1)

order_args = OrderArgs(price=0.10, size=0.50, side="BUY", token_id=token_id)
try:
    signed_order = client.create_order(order_args)
    result = client.post_order(signed_order, OrderType.GTC)
    print(f"\n✅ ORDER SUCCESS: {result}", flush=True)
except Exception as e:
    print(f"\n❌ Error: {type(e).__name__}: {e}", flush=True)