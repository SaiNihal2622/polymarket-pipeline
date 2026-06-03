#!/usr/bin/env python3
"""Check Polymarket CLOB balance."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()
import config

try:
    from py_clob_client.client import ClobClient

    priv_key = config.POLYMARKET_PRIVATE_KEY
    clean_key = priv_key.replace("0x", "").replace("0X", "")

    client = ClobClient(
        host=config.POLYMARKET_HOST,
        key=clean_key,
        chain_id=137,
        funder=clean_key,
    )
    client.set_api_creds({
        "apiKey": config.POLYMARKET_API_KEY,
        "secret": config.POLYMARKET_API_SECRET,
        "passphrase": config.POLYMARKET_API_PASSPHRASE,
    })

    # Try to get balance/info
    try:
        info = client.get_order_book("0")  # test call
        print(f"Order book test: {info}")
    except Exception as e:
        print(f"Order book test: {e}")

    # Get allowances
    try:
        allowances = client.get_allowances()
        print(f"Allowances: {allowances}")
    except Exception as e:
        print(f"Allowances error: {e}")

    # Get balance
    try:
        balance = client.get_balance_allowance()
        print(f"Balance: {balance}")
    except Exception as e:
        print(f"Balance error: {e}")

except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()