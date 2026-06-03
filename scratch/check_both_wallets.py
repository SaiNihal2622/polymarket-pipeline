#!/usr/bin/env python3
"""Check both wallet addresses for USDC."""
import httpx

wallets = {
    "Trading wallet (0x7989)": "0x79895006eA687e1B9657b2dE06ad9c33D2319Cb9",
    "Brave wallet (0x5778)":  "0x57781718755E38Ffc7FeC11d7904Dc1b7089D59E",
}

USDC_BRIDGED = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
USDC_NATIVE  = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"

for label, addr in wallets.items():
    print(f"\n{label}: {addr}")
    for name, contract in [("USDC.e", USDC_BRIDGED), ("USDC", USDC_NATIVE)]:
        payload = {"jsonrpc":"2.0","id":1,"method":"eth_call",
                   "params":[{"to":contract,"data":f"0x70a08231000000000000000000000000{addr[2:].lower()}"},"latest"]}
        r = httpx.post("https://polygon-rpc.com", json=payload, timeout=10)
        bal = int(r.json().get("result","0x0"), 16) / 1e6
        print(f"  {name}: ${bal:.2f}")
    payload2 = {"jsonrpc":"2.0","id":2,"method":"eth_getBalance","params":[addr,"latest"]}
    r2 = httpx.post("https://polygon-rpc.com", json=payload2, timeout=10)
    pol = int(r2.json().get("result","0x0"), 16) / 1e18
    print(f"  POL: {pol:.6f}")