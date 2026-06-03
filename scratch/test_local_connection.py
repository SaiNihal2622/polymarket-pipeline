"""Test local connection to Polymarket from residential IP."""
import httpx

# Check local IP
try:
    r = httpx.get('https://api.ipify.org?format=json', timeout=10)
    ip = r.json()["ip"]
    print(f"Local IP: {ip}")
except Exception as e:
    print(f"IP check failed: {e}")

# Test Polymarket CLOB directly
try:
    r2 = httpx.get('https://clob.polymarket.com/time', timeout=10)
    print(f"Polymarket /time: {r2.status_code} {r2.text[:100]}")
except Exception as e:
    print(f"Polymarket direct failed: {e}")

# Test derive_api_key endpoint (should return 200 or 400, NOT 403)
try:
    r3 = httpx.get('https://clob.polymarket.com/derive-api-key', timeout=10)
    print(f"Polymarket /derive-api-key: {r3.status_code}")
except Exception as e:
    print(f"derive-api-key failed: {e}")

print("\nIf /time returns 200 and /derive-api-key returns 200 or 400 (not 403),")
print("your residential IP works for order placement.")