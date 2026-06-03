import sys
for m in list(sys.modules.keys()):
    if 'py_order_utils' in m or 'py_clob_client' in m:
        del sys.modules[m]
import os
from dotenv import load_dotenv
load_dotenv()
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from eth_account import Account as EthAccount
priv = os.getenv('POLYMARKET_PRIVATE_KEY')
if not priv.startswith('0x'): priv = '0x'+priv
wallet = EthAccount.from_key(priv).address
cf = 'https://poly-clob-proxy.sainihal-poly.workers.dev'
print(f'Using CF proxy: {cf}')
try:
    c = ClobClient(host=cf, key=priv, chain_id=137, funder=wallet)
    cr = c.derive_api_key()
    c.set_api_creds(cr)
    print(f'API Key: {cr.api_key[:12]}...')
    o = OrderArgs(price=0.10, size=0.50, side='BUY', token_id='74636610772409469817718475200152067076720965641263785464662938420699072982790')
    s = c.create_order(o)
    r = c.post_order(s, OrderType.GTC)
    print(f'SUCCESS: {r}')
except Exception as e:
    print(f'ERROR: {type(e).__name__}: {e}')