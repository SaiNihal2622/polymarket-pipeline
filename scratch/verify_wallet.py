#!/usr/bin/env python3
"""Verify the private key matches the expected wallet address."""
import os
from dotenv import load_dotenv
load_dotenv()

# Derive address from private key
try:
    from eth_account import Account
    
    priv_key = os.getenv("POLYMARKET_PRIVATE_KEY", "")
    clean = priv_key.replace("0x", "")
    acct = Account.from_key(clean)
    derived_addr = acct.address
    
    expected = "0x57781718755E38Ffc7FeC11d7904Dc1b7089D59E"
    
    print(f"Private key:  {priv_key[:10]}...{priv_key[-8:]}")
    print(f"Derived addr: {derived_addr}")
    print(f"Expected addr: {expected}")
    print(f"Match: {'YES' if derived_addr.lower() == expected.lower() else 'NO'}")
    
except ImportError:
    print("eth_account not installed, trying web3...")
    try:
        from web3 import Account
        priv_key = os.getenv("POLYMARKET_PRIVATE_KEY", "")
        clean = priv_key.replace("0x", "")
        acct = Account.from_key(clean)
        derived_addr = acct.address
        expected = "0x57781718755E38Ffc7FeC11d7904Dc1b7089D59E"
        print(f"Derived addr: {derived_addr}")
        print(f"Expected addr: {expected}")
        print(f"Match: {'YES' if derived_addr.lower() == expected.lower() else 'NO'}")
    except ImportError:
        print("Neither eth_account nor web3 installed.")
        print("Install: pip install eth-account")