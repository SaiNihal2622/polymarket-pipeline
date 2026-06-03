"""Test py-clob-client-v2 - the official V2 package."""
import os, json, httpx

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

print("Importing py_clob_client_v2...", flush=True)
from py_clob_client_v2 import ClobClient, OrderArgs, PartialCreateOrderOptions
from py_clob_client_v2.order_builder.constants import BUY

print("Creating client...", flush=True)

PRIVATE_KEY = "0xb0984a253593290e99ff725851929c5bed779805d300aa316b9a368727f5498b"
client = ClobClient(
    host="https://clob.polymarket.com",
    key=PRIVATE_KEY,
    chain_id=137,
)

print("Deriving API key...", flush=True)
creds = client.derive_api_key()
print(f"API key: {creds.api_key[:16]}...", flush=True)
client.set_api_creds(creds)

# Get market
r = httpx.get("https://gamma-api.polymarket.com/markets?limit=5&active=true&closed=false&order=volume&ascending=false", timeout=10)
markets = r.json()
token_id = None
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
    print(f"Order created! Type: {type(signed_order).__name__}", flush=True)
    # Check available methods
    methods = [m for m in dir(signed_order) if not m.startswith('_')]
    print(f"Methods: {methods}", flush=True)
    
    result = client.post_order(signed_order, "GTC")
    print(f"\n✅ ORDER RESULT: {result}", flush=True)
except Exception as e:
    print(f"\n❌ Error: {type(e).__name__}: {e}", flush=True)