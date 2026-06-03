"""
Residential Proxy Setup for Polymarket Trading.

Polymarket blocks ALL cloud/datacenter IPs (Google Cloud, AWS, Cloudflare)
for the /order endpoint. It checks the ASN (Autonomous System Number),
not just the country.

SOLUTION: Use a residential proxy service that routes through real home IPs.

Recommended services (cheapest first):
1. BrightData (~$1/GB residential)
2. SmartProxy (~$4/month for 2GB)
3. Oxylabs (~$10/month for 5GB)
4. PacketStream (~$1/GB)

SETUP:
1. Sign up for any residential proxy service above
2. Get your proxy URL (format: http://user:pass@host:port)
3. Set in Railway: railway variables --set HTTPS_PROXY=http://user:pass@host:port
4. Set in Railway: railway variables --set POLYMARKET_HOST=https://clob.polymarket.com

The pipeline will route ALL Polymarket CLOB requests through the residential proxy.
"""
import os
import httpx
from urllib.parse import urlparse

def get_proxy_config():
    """Get proxy configuration from environment."""
    proxy_url = os.getenv('HTTPS_PROXY') or os.getenv('HTTP_PROXY') or os.getenv('POLYMARKET_PROXY')
    if not proxy_url:
        return None
    
    # Validate proxy URL
    try:
        parsed = urlparse(proxy_url)
        if not parsed.hostname:
            return None
        return {
            'url': proxy_url,
            'host': parsed.hostname,
            'port': parsed.port,
            'username': parsed.username,
            'protocol': parsed.scheme,
        }
    except Exception:
        return None

def create_proxied_client(proxy_url: str = None, timeout: int = 30) -> httpx.Client:
    """Create an httpx client with optional proxy."""
    if not proxy_url:
        proxy_url = os.getenv('HTTPS_PROXY') or os.getenv('HTTP_PROXY') or os.getenv('POLYMARKET_PROXY')
    
    if proxy_url:
        print(f"[proxy] Using residential proxy: {proxy_url[:30]}...")
        return httpx.Client(
            proxy=proxy_url,
            timeout=timeout,
            http2=True,
        )
    else:
        print("[proxy] No proxy configured — using direct connection")
        return httpx.Client(timeout=timeout, http2=True)

def test_proxy():
    """Test if the proxy is working and shows the exit IP."""
    proxy_url = os.getenv('HTTPS_PROXY') or os.getenv('HTTP_PROXY') or os.getenv('POLYMARKET_PROXY')
    
    if not proxy_url:
        print("No proxy configured. Set HTTPS_PROXY or POLYMARKET_PROXY env var.")
        print("Example: export HTTPS_PROXY=http://user:pass@proxy.example.com:8080")
        return
    
    print(f"Testing proxy: {proxy_url[:30]}...")
    
    try:
        client = create_proxied_client(proxy_url)
        
        # Check exit IP
        r = client.get('https://api.ipify.org?format=json', timeout=15)
        ip = r.json()['ip']
        print(f"Exit IP: {ip}")
        
        # Test Polymarket access
        r2 = client.get('https://clob.polymarket.com/time', timeout=15)
        print(f"Polymarket time: {r2.status_code} {r2.text[:50]}")
        
        if r2.status_code == 200:
            print("✅ Proxy works! Polymarket is accessible.")
        else:
            print(f"❌ Polymarket returned {r2.status_code}")
            
        client.close()
    except Exception as e:
        print(f"❌ Proxy test failed: {e}")

if __name__ == "__main__":
    test_proxy()