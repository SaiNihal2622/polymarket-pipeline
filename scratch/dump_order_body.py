"""Dump the exact JSON body sent to Polymarket."""
import sys, os, json, shutil

# Clear pycache
for root, dirs, files in os.walk("venv/Lib/site-packages/py_order_utils"):
    for d in dirs:
        if d == "__pycache__":
            shutil.rmtree(os.path.join(root, d), ignore_errors=True)

sys.path.insert(0, ".")

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.utilities import order_to_json
import httpx

# Don't use patches - test raw
client = ClobClient(
    host="https://clob.polymarket.com",
    key="0xb0984a253593290e99ff725851929c5bed779805d300aa316b9a368727f5498b",
    chain_id=137,
)
creds = client.derive_api_key()
client.set_api_creds(creds)

# Get market
r = httpx.get("https://gamma-api.polymarket.com/markets?limit=5&active=true&closed=false&order=volume&ascending=false", timeout=10)
markets = r.json()
for m in markets:
    clob_ids = m.get("clobTokenIds", "[]")
    if isinstance(clob_ids, str):
        clob_ids = json.loads(clob_ids)
    if clob_ids and len(clob_ids) >= 1 and len(str(clob_ids[0])) > 10:
        token_id = str(clob_ids[0])
        neg_risk = m.get("negRisk", False)
        print(f"Market: {m.get('question', '')[:60]}", flush=True)
        print(f"Token: {token_id[:30]}...", flush=True)
        print(f"negRisk: {neg_risk}", flush=True)
        break

# Create order
order_args = OrderArgs(price=0.10, size=0.50, side="BUY", token_id=token_id)
signed_order = client.create_order(order_args)

# Dump the body
body = order_to_json(signed_order, creds.api_key, OrderType.GTC, post_only=False)
print(f"\nRaw body from order_to_json:", flush=True)
print(json.dumps(body, indent=2, default=str), flush=True)

# Check neg_risk
print(f"\nClient neg_risk handling:", flush=True)
from py_clob_client.client import ClobClient as CC
import inspect
# Check create_order
src = inspect.getsource(CC.create_order)
# Search for neg_risk
for i, line in enumerate(src.split('\n')):
    if 'neg_risk' in line or 'neg' in line.lower():
        print(f"  Line {i}: {line.strip()}", flush=True)

# Check get_neg_risk
try:
    neg = client.get_neg_risk(token_id)
    print(f"\nget_neg_risk({token_id[:20]}...): {neg}", flush=True)
except Exception as e:
    print(f"\nget_neg_risk error: {e}", flush=True)