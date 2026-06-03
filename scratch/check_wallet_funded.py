#!/usr/bin/env python3
"""Check wallet balance and POL gas."""
import httpx

addr = "0x79895006eA687e1B9657b2dE06ad9c33D2319Cb9"
USDC_CONTRACT = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"

# Check USDC balance
payload = {
    "jsonrpc": "2.0", "id": 1, "method": "eth_call",
    "params": [{"to": USDC_CONTRACT, "data": f"0x70a08231000000000000000000000000{addr[2:].lower()}"}, "latest"]
}
r = httpx.post("https://polygon-rpc.com", json=payload, timeout=10)
usdc = int(r.json().get("result", "0x0"), 16) / 1e6
print(f"USDC balance: ${usdc:.2f}")

# Check POL balance (native token)
payload2 = {
    "jsonrpc": "2.0", "id": 2, "method": "eth_getBalance",
    "params": [addr, "latest"]
}
r2 = httpx.post("https://polygon-rpc.com", json=payload2, timeout=10)
pol = int(r2.json().get("result", "0x0"), 16) / 1e18
print(f"POL balance: {pol:.4f} POL")

if pol < 0.01:
    print("\n⚠️  WARNING: You need POL for gas fees! Send at least 0.5 POL to the same address.")
else:
    print(f"\n✅ POL gas balance is sufficient")

if usdc >= 20:
    print(f"✅ USDC balance is sufficient for trading")
else:
    print(f"⚠️  USDC balance is low — minimum $20 recommended")