"""Check which exchange address is needed."""
import sys, os, json, shutil

for root, dirs, files in os.walk("venv/Lib/site-packages/py_order_utils"):
    for d in dirs:
        if d == "__pycache__":
            shutil.rmtree(os.path.join(root, d), ignore_errors=True)

sys.path.insert(0, ".")
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType, CreateOrderOptions
from py_clob_client.utilities import order_to_json
from py_clob_client.config import get_contract_config
from py_clob_client.headers.headers import create_level_2_headers, RequestArgs
from py_clob_client.endpoints import POST_ORDER
import httpx, json

key = "0xb0984a253593290e99ff725851929c5bed779805d300aa316b9a368727f5498b"

# Get market info
r = httpx.get("https://gamma-api.polymarket.com/markets?limit=10&active=true&closed=false&order=volume&ascending=false", timeout=10)
markets = r.json()

for m in markets[:3]:
    clob_ids = m.get("clobTokenIds", "[]")
    if isinstance(clob_ids, str):
        clob_ids = json.loads(clob_ids)
    if not clob_ids or len(clob_ids) < 1 or len(str(clob_ids[0])) < 10:
        continue
    
    token_id = str(clob_ids[0])
    neg_risk = m.get("negRisk", False)
    question = m.get("question", "")[:60]
    
    print(f"\nMarket: {question}", flush=True)
    print(f"negRisk: {neg_risk} (type: {type(neg_risk)})", flush=True)
    
    # Get contract config for both
    cfg_normal = get_contract_config(137, False)
    cfg_neg = get_contract_config(137, True)
    print(f"Normal exchange: {cfg_normal.exchange}", flush=True)
    print(f"Neg risk exchange: {cfg_neg.exchange}", flush=True)
    
    # Try with neg_risk=True (force neg_risk exchange)
    client = ClobClient(host="https://clob.polymarket.com", key=key, chain_id=137)
    creds = client.derive_api_key()
    client.set_api_creds(creds)
    
    order_args = OrderArgs(price=0.10, size=0.50, side="BUY", token_id=token_id)
    
    # Try with explicit neg_risk=True
    try:
        opts = CreateOrderOptions(tick_size="0.01", neg_risk=True)
        signed_order = client.create_order(order_args, options=opts)
        body = order_to_json(signed_order, creds.api_key, OrderType.GTC, post_only=False)
        body["order"]["version"] = 2
        body["version"] = 2
        headers = create_level_2_headers(client.signer, client.creds, RequestArgs(method="POST", request_path=POST_ORDER, body=body))
        resp = httpx.post(f"https://clob.polymarket.com{POST_ORDER}", headers=headers, json=body, timeout=15)
        print(f"neg_risk=True: {resp.status_code} {resp.text[:200]}", flush=True)
    except Exception as e:
        print(f"neg_risk=True error: {e}", flush=True)
    
    # Try with explicit neg_risk=False
    try:
        opts = CreateOrderOptions(tick_size="0.01", neg_risk=False)
        signed_order = client.create_order(order_args, options=opts)
        body = order_to_json(signed_order, creds.api_key, OrderType.GTC, post_only=False)
        body["order"]["version"] = 2
        body["version"] = 2
        headers = create_level_2_headers(client.signer, client.creds, RequestArgs(method="POST", request_path=POST_ORDER, body=body))
        resp = httpx.post(f"https://clob.polymarket.com{POST_ORDER}", headers=headers, json=body, timeout=15)
        print(f"neg_risk=False: {resp.status_code} {resp.text[:200]}", flush=True)
    except Exception as e:
        print(f"neg_risk=False error: {e}", flush=True)
    
    break  # Only test first valid market