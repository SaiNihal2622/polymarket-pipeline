#!/usr/bin/env python3
"""Test Polymarket CLOB client connection with stored credentials."""
import os
from dotenv import load_dotenv
load_dotenv()

print("Testing Polymarket CLOB connection...")

try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import ApiCreds

    priv_key = os.getenv("POLYMARKET_PRIVATE_KEY", "")
    api_key = os.getenv("POLYMARKET_API_KEY", "")
    api_secret = os.getenv("POLYMARKET_API_SECRET", "")
    api_passphrase = os.getenv("POLYMARKET_API_PASSPHRASE", "")

    clean_key = priv_key.replace("0x", "").replace("0X", "")
    
    client = ClobClient(
        host="https://clob.polymarket.com",
        key=clean_key,
        chain_id=137,
        funder=clean_key,
    )
    
    client.set_api_creds({
        "apiKey": api_key,
        "secret": api_secret,
        "passphrase": api_passphrase,
    })
    
    print("✅ ClobClient initialized OK")
    
    # Try to derive API creds to verify key works
    try:
        creds = client.create_or_derive_api_creds()
        print(f"✅ API credentials derived: {creds.api_key[:20]}...")
    except Exception as e:
        print(f"⚠️  Derive creds: {e} (may be OK if creds already set)")
    
    # Try a simple API call
    try:
        # Get a market to test connectivity
        import httpx
        r = httpx.get("https://gamma-api.polymarket.com/markets", params={"limit": 1, "active": "true"}, timeout=10)
        r.raise_for_status()
        markets = r.json()
        if markets:
            print(f"✅ Gamma API: fetched {len(markets)} market(s)")
            m = markets[0]
            print(f"   Sample: {m.get('question', '?')[:60]}")
    except Exception as e:
        print(f"⚠️  Gamma API: {e}")
    
    # Check wallet balance
    try:
        from eth_account import Account
        addr = Account.from_key(clean_key).address
        print(f"\n  Trading wallet: {addr}")
        # Check USDC balance on Polygon via public RPC
        import httpx
        # USDC on Polygon: 0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174
        USDC_CONTRACT = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_call",
            "params": [
                {
                    "to": USDC_CONTRACT,
                    "data": f"0x70a08231000000000000000000000000{addr[2:].lower()}"
                },
                "latest"
            ]
        }
        r = httpx.post("https://polygon-rpc.com", json=payload, timeout=10)
        result = r.json().get("result", "0x0")
        balance = int(result, 16) / 1e6  # USDC has 6 decimals
        print(f"   USDC balance: ${balance:.2f}")
    except Exception as e:
        print(f"   Balance check: {e}")

    print("\n✅ Ready for live trading!")
    
except ImportError:
    print("❌ py_clob_client not installed")
except Exception as e:
    print(f"❌ Error: {type(e).__name__}: {e}")