"""Test py-clob-client-v2 using exact official README pattern."""
import os, json, httpx
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

from py_clob_client_v2 import ApiCreds, ClobClient, OrderArgs, OrderType, PartialCreateOrderOptions, Side

host = "https://clob.polymarket.com"
chain_id = 137
key = "0xb0984a253593290e99ff725851929c5bed779805d300aa316b9a368727f5498b"

# Step 1: derive API credentials
print("Step 1: Deriving API creds...", flush=True)
client = ClobClient(host=host, chain_id=chain_id, key=key)
creds = client.create_or_derive_api_key()
print(f"API key: {creds.api_key[:16]}...", flush=True)

# Step 2: fully-authenticated client
client = ClobClient(host=host, chain_id=chain_id, key=key, creds=creds)

# Check wallet address
address = client.get_address()
print(f"Wallet address: {address}", flush=True)

# Get balance
try:
    balance = client.get_balance_allowance()
    print(f"Balance: {balance}", flush=True)
except Exception as e:
    print(f"Balance check error: {e}", flush=True)

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
        tick = m.get("minimumTickSize", "0.01")
        print(f"Tick size: {tick}", flush=True)
        break

# Step 3: create and post order (exact README format)
print("\nStep 3: Creating order...", flush=True)
try:
    resp = client.create_and_post_order(
        order_args=OrderArgs(
            token_id=token_id,
            price=0.10,
            side=Side.BUY,
            size=0.50,
        ),
        options=PartialCreateOrderOptions(tick_size="0.01"),
        order_type=OrderType.GTC,
    )
    print(f"\n✅ ORDER SUCCESS: {resp}", flush=True)
except Exception as e:
    print(f"\n❌ Error: {type(e).__name__}: {e}", flush=True)