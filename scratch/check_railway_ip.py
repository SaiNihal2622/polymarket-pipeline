"""Check Railway's public IP and test direct Polymarket access."""
import httpx

# Get public IP
try:
    r = httpx.get('https://api.ipify.org?format=json', timeout=10)
    ip = r.json()['ip']
    print(f'Public IP: {ip}')
except Exception as e:
    print(f'IP check failed: {e}')

# Test direct CLOB access
try:
    r2 = httpx.get('https://clob.polymarket.com/time', timeout=10)
    print(f'Direct CLOB time: {r2.status_code} {r2.text[:50]}')
except Exception as e:
    print(f'Direct CLOB failed: {e}')