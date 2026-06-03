"""Test order WITH V2 patches applied."""
import sys
sys.path.insert(0, ".")

# Apply patches FIRST
import patch_clob_v2

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
import inspect

# Verify domain is patched
from py_order_utils.builders import OrderBuilder as UtilsOrderBuilder
src = inspect.getsource(UtilsOrderBuilder._get_domain_separator)
if 'version="2"' in src or "version='2'" in src:
    print("✅ Domain version is '2' (patched)", flush=True)
else:
    print(f"❌ Domain version still '1'!", flush=True)
    print(src[:300], flush=True)

# Create client
client = ClobClient(
    host="https://clob.polymarket.com",
    key="0xb0984a253593290e99ff725851929c5bed779805d300aa316b9a368727f5498b",
    chain_id=137,
)
creds = client.derive_api_key()
client.set_api_creds(creds)
print(f"API key: {creds.api_key[:16]}...", flush=True)

# Get a real token ID from gamma API - handle nested list format
import httpx
r = httpx.get("https://gamma-api.polymarket.com/markets?limit=5&active=true&closed=false&order=volume&ascending=false", timeout=10)
markets = r.json()

import json as _json

token_id = None
for m in markets:
    clob_ids = m.get("clobTokenIds", [])
    if isinstance(clob_ids, str):
        clob_ids = _json.loads(clob_ids)
    if clob_ids and len(clob_ids) >= 1:
        tid = clob_ids[0]
        if isinstance(tid, list):
            tid = tid[0] if tid else None
        if tid and len(str(tid)) > 10:
            token_id = str(tid)
            print(f"\nMarket: {m.get('question', 'N/A')[:60]}", flush=True)
            print(f"Token ID: {token_id[:30]}...", flush=True)
            break

if not token_id:
    print("No valid token ID found!", flush=True)
    sys.exit(1)

# Try creating order
order_args = OrderArgs(price=0.10, size=0.50, side="BUY", token_id=token_id)
try:
    signed_order = client.create_order(order_args)
    d = signed_order.dict()
    print(f"\nOrder dict keys: {list(d.keys())}", flush=True)
    
    # Check order_to_json output
    import py_clob_client.utilities as util
    json_result = util.order_to_json(signed_order, creds.api_key, OrderType.GTC)
    order_body = json_result.get('order', {})
    if 'version' in order_body:
        print(f"✅ version in order body: {order_body['version']}", flush=True)
    else:
        print("❌ NO version in order body!", flush=True)
    
    # Try posting
    result = client.post_order(signed_order, OrderType.GTC)
    print(f"\n✅ ORDER SUCCESS: {result}", flush=True)
except Exception as e:
    print(f"\n❌ Error: {type(e).__name__}: {e}", flush=True)
