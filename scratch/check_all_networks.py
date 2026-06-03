#!/usr/bin/env python3
"""Check wallet balance across multiple chains."""
import httpx

addr = "0x79895006eA687e1B9657b2dE06ad9c33D2319Cb9"
USDC = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"

chains = {
    "Polygon PoS":    "https://polygon-rpc.com",
    "Ethereum":       "https://cloudflare-eth.com",
    "Arbitrum":       "https://arb1.arbitrum.io/rpc",
    "Optimism":       "https://mainnet.optimism.io",
    "Base":           "https://mainnet.base.org",
    "BSC":            "https://bsc-dataseed.binance.org",
    "Avalanche C":    "https://api.avax.network/ext/bc/C/rpc",
}

USDC_ADDRESSES = {
    "Polygon PoS":    "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
    "Ethereum":       "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    "Arbitrum":       "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
    "Optimism":       "0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85",
    "Base":           "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    "BSC":            "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
    "Avalanche C":    "0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E",
}

print(f"Checking address: {addr}\n")
print(f"{'Network':<20} {'USDC':<15} {'POL/Native':<15}")
print("-"*50)

for name, rpc in chains.items():
    usdc_contract = USDC_ADDRESSES.get(name, USDC)
    payload = {"jsonrpc":"2.0","id":1,"method":"eth_call",
               "params":[{"to":usdc_contract,"data":f"0x70a08231000000000000000000000000{addr[2:].lower()}"},"latest"]}
    try:
        r = httpx.post(rpc, json=payload, timeout=5)
        bal = int(r.json().get("result","0x0"), 16) / 1e6
    except:
        bal = -1

    # Native coin
    payload2 = {"jsonrpc":"2.0","id":2,"method":"eth_getBalance","params":[addr,"latest"]}
    try:
        r2 = httpx.post(rpc, json=payload2, timeout=5)
        native = int(r2.json().get("result","0x0"), 16) / 1e18
    except:
        native = -1

    print(f"{name:<20} ${bal:<12.2f} {native:<15.6f}")