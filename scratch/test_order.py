"""Test placing a CLOB order through the Vercel proxy."""
import sys
# Clear cached modules
for mod_name in list(sys.modules.keys()):
    if 'py_order_utils' in mod_name or 'py_clob_client' in mod_name:
        del sys.modules[mod_name]

import os, json, httpx
from dotenv import load_dotenv
load_dotenv()
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.utilities import order_to_json
from eth_account import Account as EthAccount

priv = os.getenv('POLYMARKET_PRIVATE_KEY')
if not priv.startswith('0x'):
    priv = '0x' + priv
acct = EthAccount.from_key(priv)
wallet = acct.address
print(f'Wallet: {wallet}')

proxy_url = 'https://vercel-proxy-nine-rose.vercel.app'
print(f'Proxy: {proxy_url}')

client = ClobClient(host=proxy_url, key=priv, chain_id=137, funder=wallet)
creds = client.derive_api_key()
client.set_api_creds(creds)
print(f'API Key: {creds.api_key[:12]}...')

order_args = OrderArgs(
    price=0.10, size=0.50, side='BUY',
    token_id='74636610772409469817718475200152067076720965641263785464662938420699072982790',
)
signed = client.create_order(order_args)

# Get the body that would be sent
body = order_to_json(signed, creds.api_key, OrderType.GTC, False)
print(f'Body keys: {list(body.keys())}')
print(f'Body version: {body.get("version", "MISSING")}')

# Try using client.post_order
try:
    resp = client.post_order(signed, OrderType.GTC)
    print(f'SUCCESS! Order result: {resp}')
except Exception as e:
    print(f'ERROR: {e}')
    
    # Try manual POST with httpx
    print("\nTrying manual POST...")
    serialized = json.dumps(body, separators=(',', ':'), ensure_ascii=False)
    print(f'Serialized body (first 500 chars): {serialized[:500]}')
    
    # Create L2 headers manually
    import time
    from py_clob_client.http_helpers.helpers import overloadHeaders
    from py_clob_client.clob_types import RequestArgs
    
    request_args = RequestArgs(
        method='POST', request_path='/order',
        body=body, serialized_body=serialized,
    )
    
    # Try importing the correct function
    from py_clob_client.headers import create_level_2_headers
    headers = create_level_2_headers(client.signer, client.creds, request_args)
    headers['Content-Type'] = 'application/json'
    
    endpoint = f'{proxy_url}/order'
    r = httpx.post(endpoint, content=serialized.encode('utf-8'), headers=headers, timeout=15)
    print(f'Manual POST result: {r.status_code} {r.text[:300]}')