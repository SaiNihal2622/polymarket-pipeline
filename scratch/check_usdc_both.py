#!/usr/bin/env python3
"""Check both USDC contracts on Polygon."""
import httpx

addr = "0x79895006eA687e1B9657b2dE06ad9c33D2319Cb9"

# USDC.e (bridged) = 0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174
# USDC (native)    = 0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359
contracts = {
    "USDC.e (bridged)": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
    "USDC (native)":    "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359",
}

for name, contract in contracts.items():
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "eth_call",
        "params": [{"to": contract, "data": f"0x70a08231000000000000000000000000{addr[2:].lower()}"}, "latest"]
    }
    r = httpx.post("https://polygon-rpc.com", json=payload, timeout=10)
    bal = int(r.json().get("result", "0x0"), 16) / 1e6
    print(f"  {name}: ${bal:.2f}")

# Check POL balance
payload2 = {"jsonrpc": "2.0", "id": 2, "method": "eth_getBalance", "params": [addr, "latest"]}
r2 = httpx.post("https://polygon-rpc.com", json=payload2, timeout=10)
pol = int(r2.json().get("result", "0x0"), 16) / 1e18
print(f"  POL (gas): {pol:.6f}")