#!/usr/bin/env python3
"""Check what py_clob_client expects for key format."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

priv_key = os.getenv("POLYMARKET_PRIVATE_KEY", "")
print(f"Key from env: {priv_key[:15]}...{priv_key[-8:]}")
print(f"Length: {len(priv_key)}")
print(f"Has 0x: {priv_key.startswith('0x')}")

# Check py_clob_client's key handling
try:
    from py_clob_client.client import ClobClient
    # Check what format it expects by looking at its source
    import inspect
    src = inspect.getsource(ClobClient.__init__)
    print(f"\nClobClient.__init__ source (first 500 chars):")
    print(src[:500])
except Exception as e:
    print(f"Error: {e}")

# Check if there's a key normalization function
try:
    import py_clob_client
    import inspect
    # Look for normalize function
    for name, obj in inspect.getmembers(py_clob_client):
        if 'normal' in name.lower() or 'key' in name.lower():
            print(f"Found: {name}")
except Exception as e:
    pass

# Try to find the actual normalize function in the module
try:
    import py_clob_client.helpers
    src = inspect.getsource(py_clob_client.helpers)
    if 'normalize' in src.lower():
        for line in src.split('\n'):
            if 'normalize' in line.lower() or 'Unknown format' in line:
                print(f"  {line.strip()}")
except:
    pass

# Try creating a client without 0x prefix
clean_key = priv_key.replace("0x", "")
print(f"\nClean key: {clean_key[:15]}...{clean_key[-8:]}")
print(f"Clean length: {len(clean_key)}")

try:
    client = ClobClient(
        host="https://clob.polymarket.com",
        key=clean_key,
        chain_id=137,
        funder=clean_key,
    )
    print("Client created OK with clean_key (no 0x)")
except Exception as e:
    print(f"Client failed with clean_key: {e}")

try:
    client = ClobClient(
        host="https://clob.polymarket.com",
        key=priv_key,
        chain_id=137,
        funder=priv_key,
    )
    print("Client created OK with priv_key (0x)")
except Exception as e:
    print(f"Client failed with priv_key: {e}")