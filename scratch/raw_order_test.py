"""Test raw HTTP order with different version formats."""
import sys, os, json, shutil

for root, dirs, files in os.walk("venv/Lib/site-packages/py_order_utils"):
    for d in dirs:
        if d == "__pycache__":
            shutil.rmtree(os.path.join(root, d), ignore_errors=True)

sys.path.insert(0, ".")
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.utilities import order_to_json
from py_clob_client.headers.headers import create_level_2_headers, RequestArgs
from py_clob_client.endpoints import POST_ORDER
import httpx, json

key = "0xb0984a253593290e99ff725851929c5bed779805d300aa316b9a368727f5498b"
client = ClobClient(host="https://clob.polymarket.com", key=key, chain_id=137)
creds = client.derive_api_key()
client.set_api_creds(creds)

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
        break

order_args = OrderArgs(price=0.10, size=0.50, side="BUY", token_id=token_id)
signed_order = client.create_order(order_args)
body = order_to_json(signed_order, creds.api_key, OrderType.GTC, post_only=False)

# Test: version=2 as integer inside order dict
print("\n--- Test: version=2 (int) inside order ---", flush=True)
b = json.loads(json.dumps(body))
b["order"]["version"] = 2
headers = create_level_2_headers(client.signer, client.creds, RequestArgs(method="POST", request_path=POST_ORDER, body=b))
resp = httpx.post(f"https://clob.polymarket.com{POST_ORDER}", headers=headers, json=b, timeout=15)
print(f"Status: {resp.status_code} Body: {resp.text[:200]}", flush=True)

# Test: version=2 as string inside order dict
print("\n--- Test: version='2' (str) inside order ---", flush=True)
b2 = json.loads(json.dumps(body))
b2["order"]["version"] = "2"
headers = create_level_2_headers(client.signer, client.creds, RequestArgs(method="POST", request_path=POST_ORDER, body=b2))
resp = httpx.post(f"https://clob.polymarket.com{POST_ORDER}", headers=headers, json=b2, timeout=15)
print(f"Status: {resp.status_code} Body: {resp.text[:200]}", flush=True)

# Test: no version at all
print("\n--- Test: no version field ---", flush=True)
b3 = json.loads(json.dumps(body))
if "version" in b3.get("order", {}):
    del b3["order"]["version"]
if "version" in b3:
    del b3["version"]
headers = create_level_2_headers(client.signer, client.creds, RequestArgs(method="POST", request_path=POST_ORDER, body=b3))
resp = httpx.post(f"https://clob.polymarket.com{POST_ORDER}", headers=headers, json=b3, timeout=15)
print(f"Status: {resp.status_code} Body: {resp.text[:200]}", flush=True)