"""
Check Polymarket CLOB API for actual orders and their resolution status.
"""
import os, json
from dotenv import load_dotenv
load_dotenv()

try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import ApiCreds
    
    host = "https://clob.polymarket.com"
    key = os.getenv("POLY_PRIVATE_KEY", "")
    chain_id = 137  # Polygon mainnet
    
    client = ClobClient(host, key=key, chain_id=chain_id)
    
    # Try to get API creds
    api_key = os.getenv("POLY_API_KEY", "")
    api_secret = os.getenv("POLY_API_SECRET", "")
    api_passphrase = os.getenv("POLY_API_PASSPHRASE", "")
    
    if api_key and api_secret and api_passphrase:
        creds = ApiCreds(
            api_key=api_key,
            api_secret=api_secret,
            api_passphrase=api_passphrase,
        )
        client.set_api_creds(creds)
        
        # Get open orders
        print("=== OPEN ORDERS ===")
        try:
            orders = client.get_orders()
            if orders:
                for o in orders:
                    print(json.dumps(o, indent=2, default=str))
            else:
                print("No open orders")
        except Exception as e:
            print(f"Error getting orders: {e}")
        
        # Get trade history
        print("\n=== TRADE HISTORY ===")
        try:
            trades = client.get_trades()
            if trades:
                for t in trades:
                    print(json.dumps(t, indent=2, default=str))
            else:
                print("No trades found")
        except Exception as e:
            print(f"Error getting trades: {e}")
    else:
        print("Missing API credentials")
        print(f"  POLY_API_KEY: {'SET' if api_key else 'MISSING'}")
        print(f"  POLY_API_SECRET: {'SET' if api_secret else 'MISSING'}")
        print(f"  POLY_API_PASSPHRASE: {'SET' if api_passphrase else 'MISSING'}")
        print(f"  POLY_PRIVATE_KEY: {'SET' if key else 'MISSING'}")
        
except ImportError as e:
    print(f"Import error: {e}")
    print("Need py_clob_client installed")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()