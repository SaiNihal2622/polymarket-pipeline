"""Test order creation and JSON serialization."""
import patch_clob_v2
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType

# Create client
client = ClobClient(
    host="https://clob.polymarket.com",
    key="0xb0984a253593290e99ff725851929c5bed779805d300aa316b9a368727f5498b",
    chain_id=137,
)

# Derive API key
creds = client.derive_api_key()
client.set_api_creds(creds)
print(f"API key: {creds.api_key[:16]}...", flush=True)

# Create order args
order_args = OrderArgs(
    price=0.10,
    size=1.0,
    side="BUY",
    token_id="10319655728999853551737427685505636582259939484088749613478803798426472638411",
)

# Create order
signed_order = client.create_order(order_args)
print(f"\nSigned order type: {type(signed_order)}", flush=True)
print(f"Signed order dict: {signed_order.dict()}", flush=True)

# Check if version is in the dict
d = signed_order.dict()
if 'version' in d:
    print(f"\n✅ version field found: {d['version']}", flush=True)
else:
    print(f"\n❌ version field NOT in order.dict()", flush=True)

# Now test order_to_json
import py_clob_client.utilities as util
json_result = util.order_to_json(signed_order, creds.api_key, OrderType.GTC)
print(f"\norder_to_json result: {json_result}", flush=True)
if 'version' in json_result.get('order', {}):
    print(f"\n✅ version in JSON: {json_result['order']['version']}", flush=True)
else:
    print(f"\n❌ version NOT in JSON order body", flush=True)