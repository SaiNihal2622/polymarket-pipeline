"""Direct CLOB order placement bypassing py_clob_client's broken order builder."""
import os, json, time, httpx
from dotenv import load_dotenv
load_dotenv()
from eth_account import Account
from eth_account.messages import encode_defunct

priv = os.getenv('POLYMARKET_PRIVATE_KEY')
if not priv.startswith('0x'): priv = '0x' + priv
acct = Account.from_key(priv)
wallet = acct.address
print(f'Wallet: {wallet}')

PROXY = 'https://vercel-proxy-nine-rose.vercel.app'

# Step 1: Derive API key
msg = encode_defunct(text=str(int(time.time())))
sig = acct.sign_message(msg)

# Actually use the proper L1 auth
from py_clob_client.signing.eip712 import sign_clob_auth_message
from py_clob_client.signer import Signer as ClobSigner

signer = ClobSigner(priv, 137)
timestamp = int(time.time())
l1_sig = sign_clob_auth_message(signer, timestamp, 0)

l1_headers = {
    'POLY_ADDRESS': wallet,
    'POLY_SIGNATURE': l1_sig,
    'POLY_TIMESTAMP': str(timestamp),
    'POLY_NONCE': '0',
    'Content-Type': 'application/json',
}

r = httpx.get(f'{PROXY}/auth/derive-api-key', headers=l1_headers, timeout=15)
print(f'derive_api_key: {r.status_code} {r.text[:200]}')
creds = r.json()

# Step 2: Build order manually
token_id = '74636610772409469817718475200152067076720965641263785464662938420699072982790'
exchange = '0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E'  # CTF Exchange V2

# Build order struct
import secrets
salt = secrets.randbits(192)
maker_amount = 50000  # $0.05 USDC (6 decimals)
taker_amount = 500000  # 0.5 tokens at 0.10 price

order = {
    'salt': salt,
    'maker': wallet,
    'signer': wallet,
    'taker': '0x0000000000000000000000000000000000000000',
    'tokenId': token_id,
    'makerAmount': str(maker_amount),
    'takerAmount': str(taker_amount),
    'expiration': '0',
    'nonce': '0',
    'feeRateBps': '0',
    'side': 'BUY',
    'signatureType': 0,  # EOA
}

# Step 3: Sign with EIP-712 domain
from poly_eip712_structs import make_domain, EIP712Struct, Uint, Address
from eth_utils import keccak
from py_order_utils.utils import prepend_zx

# Try with version 1 first (what the original library uses)
domain = make_domain(
    name='Polymarket CTF Exchange',
    version='1',
    chainId='137',
    verifyingContract=exchange,
)

class Order(EIP712Struct):
    salt = Uint(256)
    maker = Address()
    signer = Address()
    taker = Address()
    tokenId = Uint(256)
    makerAmount = Uint(256)
    takerAmount = Uint(256)
    expiration = Uint(256)
    nonce = Uint(256)
    feeRateBps = Uint(256)
    side = Uint(8)
    signatureType = Uint(8)

o = Order(
    salt=order['salt'],
    maker=order['maker'],
    signer=order['signer'],
    taker=order['taker'],
    tokenId=int(order['tokenId']),
    makerAmount=int(order['makerAmount']),
    takerAmount=int(order['takerAmount']),
    expiration=int(order['expiration']),
    nonce=int(order['nonce']),
    feeRateBps=int(order['feeRateBps']),
    side=0,
    signatureType=order['signatureType'],
)

struct_hash = keccak(o.signable_bytes(domain=domain)).hex()
sig_result = acct.sign_message(encode_defunct(hexstr=prepend_zx(struct_hash)))
signature = sig_result.signature.hex()
if not signature.startswith('0x'):
    signature = '0x' + signature

# Step 4: Post order
body = {
    'order': {**order, 'signature': signature},
    'owner': wallet,
    'orderType': 'GTC',
    'postOnly': False,
}

# L2 auth
from py_clob_client.signing.hmac import build_hmac_signature

body_str = json.dumps(body, separators=(',', ':'), ensure_ascii=False)
ts = int(time.time())
hmac = build_hmac_signature(creds['secret'], ts, 'POST', '/order', body_str)

l2_headers = {
    'POLY_ADDRESS': wallet,
    'POLY_SIGNATURE': hmac,
    'POLY_TIMESTAMP': str(ts),
    'POLY_API_KEY': creds['apiKey'],
    'POLY_PASSPHRASE': creds['passphrase'],
    'Content-Type': 'application/json',
}

r2 = httpx.post(f'{PROXY}/order', content=body_str.encode(), headers=l2_headers, timeout=15)
print(f'post_order: {r2.status_code} {r2.text[:500]}')