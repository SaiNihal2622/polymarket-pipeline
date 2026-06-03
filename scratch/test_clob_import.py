import sys
print("Python:", sys.version, flush=True)
try:
    from py_clob_client.client import ClobClient
    print("ClobClient imported OK", flush=True)
    from py_clob_client.clob_types import OrderArgs, OrderType
    print("OrderArgs, OrderType imported OK", flush=True)
    
    # Test creating a client
    client = ClobClient(
        host="https://clob.polymarket.com",
        key="0xb0984a253593290e99ff725851929c5bed779805d300aa316b9a368727f5498b",
        chain_id=137,
    )
    print(f"ClobClient created: {client}", flush=True)
    
    # Test derive_api_key
    creds = client.derive_api_key()
    print(f"API key derived: {creds.api_key[:16]}...", flush=True)
    print("SUCCESS: Full CLOB client chain works!", flush=True)
except ImportError as e:
    print(f"ImportError: {e}", flush=True)
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}", flush=True)