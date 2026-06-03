"""Verify domain separator is actually version=2 at runtime."""
import sys, os, shutil

for root, dirs, files in os.walk("venv/Lib/site-packages/py_order_utils"):
    for d in dirs:
        if d == "__pycache__":
            shutil.rmtree(os.path.join(root, d), ignore_errors=True)

sys.path.insert(0, ".")
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import importlib
import py_order_utils.builders.base_builder as bb
importlib.reload(bb)
import inspect

src = inspect.getsource(bb.BaseBuilder._get_domain_separator)
has_v2 = 'version="2"' in src
print(f"After reload, version=2 in source: {has_v2}", flush=True)

from py_order_utils.signer import Signer as US
from eth_account import Account as EA
from eth_utils import keccak as k

key = "0xb0984a253593290e99ff725851929c5bed779805d300aa316b9a368727f5498b"
acct = EA.from_key(key)
signer = US(acct._key_obj)

bb2 = bb.BaseBuilder("0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E", 137, signer, lambda: 123)
ds = bb2.domain_separator

print(f"Domain values: {ds.values}", flush=True)

# Manual domain hash for version=2
type_hash = k(b"EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)")
name_hash = k(b"Polymarket CTF Exchange")
version2_hash = k(b"2")
version1_hash = k(b"1")
chain_id_bytes = (137).to_bytes(32, "big")
addr_bytes = bytes.fromhex("4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E").rjust(32, b"\x00")

domain2_hash = k(type_hash + name_hash + version2_hash + chain_id_bytes + addr_bytes)
domain1_hash = k(type_hash + name_hash + version1_hash + chain_id_bytes + addr_bytes)
print(f"Domain hash (v2): {domain2_hash.hex()}", flush=True)
print(f"Domain hash (v1): {domain1_hash.hex()}", flush=True)

# Now create a test order and sign it, check the signature
from py_order_utils.model.order import OrderData
from py_order_utils.model.sides import BUY
from py_order_utils.model.signatures import EOA

data = OrderData(
    maker="0x79895006eA687e1B9657b2dE06ad9c33D2319Cb9",
    taker="0x0000000000000000000000000000000000000000",
    tokenId="101668802868249989104210390736408299967862831563234336634402961281754466689473",
    makerAmount="50000",
    takerAmount="500000",
    side=BUY,
    feeRateBps="1000",
    nonce="0",
    signer="0x79895006eA687e1B9657b2dE06ad9c33D2319Cb9",
    expiration="0",
    signatureType=EOA,
)

from py_order_utils.builders.order_builder import OrderBuilder
order_builder = OrderBuilder("0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E", 137, signer, lambda: 123)
order = order_builder.build_order(data)
sig = order_builder.build_order_signature(order)
print(f"\nSignature: {sig[:30]}...", flush=True)

# Now test posting through the actual client
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
import httpx, json

client = ClobClient(
    host="https://clob.polymarket.com",
    key=key,
    chain_id=137,
)
creds = client.derive_api_key()
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
        print(f"\nMarket: {m.get('question', '')[:60]}", flush=True)
        break

order_args = OrderArgs(price=0.10, size=0.50, side="BUY", token_id=token_id)
try:
    signed_order = client.create_order(order_args)
    result = client.post_order(signed_order, OrderType.GTC)
    print(f"\nSUCCESS: {result}", flush=True)
except Exception as e:
    print(f"\nFAILED: {type(e).__name__}: {e}", flush=True)