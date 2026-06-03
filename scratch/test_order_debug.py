"""Debug order creation to see what's being sent."""
import sys
sys.path.insert(0, ".")

# Patch FIRST
import patch_clob_v2

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
import py_clob_client.client as client_mod
import py_clob_client.utilities as util

# Verify patch is applied
print(f"client_mod.order_to_json name: {client_mod.order_to_json.__name__}", flush=True)
print(f"util.order_to_json name: {util.order_to_json.__name__}", flush=True)

# Create client
client = ClobClient(
    host="https://clob.polymarket.com",
    key="0xb0984a253593290e99ff725851929c5bed779805d300aa316b9a368727f5498b",
    chain_id=137,
)
creds = client.derive_api_key()
client.set_api_creds(creds)

# Create a test order with a real token ID from the last scan
token_id = "10319655728999853551737427685505636582259939484088749613478803798426472638411"
order_args = OrderArgs(price=0.10, size=0.50, side="BUY", token_id=token_id)

# Create signed order  
signed_order = client.create_order(order_args)
print(f"\nsigned_order type: {type(signed_order)}", flush=True)
d = signed_order.dict()
print(f"signed_order.dict() keys: {list(d.keys())}", flush=True)
print(f"signed_order.dict(): {d}", flush=True)

# Test order_to_json manually  
json_result = util.order_to_json(signed_order, creds.api_key, OrderType.GTC)
print(f"\njson_result keys: {list(json_result.keys())}", flush=True)
print(f"json_result['order'] keys: {list(json_result['order'].keys())}", flush=True)
if 'version' in json_result['order']:
    print(f"✅ version in order: {json_result['order']['version']}", flush=True)
else:
    print(f"❌ version NOT in order", flush=True)

# Also check the body that would be posted
import json
print(f"\nFull JSON body that would be sent:")
print(json.dumps(json_result, indent=2, default=str)[:3000], flush=True)