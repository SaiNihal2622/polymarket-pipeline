"""
BrightData Residential Proxy Setup for Polymarket Pipeline.

Run this script after creating your BrightData residential proxy zone
to validate the proxy URL and set it on Railway.

STEPS:
1. Go to https://brightdata.com/cp/zone/residential
2. Create a new zone (or use the default "residential" zone)
3. Go to "Access parameters" tab
4. Copy: Host, Port, Username, Password
5. Run this script with the proxy URL:
   python scratch/setup_brightdata_proxy.py "http://USERNAME:PASSWORD@brd.superproxy.io:22225"

Or set it manually:
   railway variables --set "POLYMARKET_PROXY=http://brd-customer-XXXXX-zone-residential:PASSWORD@brd.superproxy.io:22225"
"""
import sys
import os
import httpx

def validate_proxy(proxy_url: str) -> bool:
    """Test proxy connectivity and Polymarket access."""
    print(f"\n{'='*60}")
    print(f"Testing proxy: {proxy_url[:50]}...")
    print(f"{'='*60}\n")
    
    try:
        client = httpx.Client(proxy=proxy_url, timeout=20, http2=False)
        
        # 1. Check exit IP
        print("[1/3] Checking exit IP...")
        r = client.get("https://api.ipify.org?format=json", timeout=15)
        ip = r.json()["ip"]
        print(f"  Exit IP: {ip}")
        
        # 2. Test Polymarket /time
        print("[2/3] Testing Polymarket /time...")
        r2 = client.get("https://clob.polymarket.com/time", timeout=15)
        print(f"  Status: {r2.status_code} | Response: {r2.text[:100]}")
        
        # 3. Test derive-api-key (should return 200 or 400, NOT 403)
        print("[3/3] Testing Polymarket /derive-api-key...")
        r3 = client.get("https://clob.polymarket.com/derive-api-key", timeout=15)
        print(f"  Status: {r3.status_code}")
        
        client.close()
        
        if r2.status_code == 200 and r3.status_code != 403:
            print(f"\n✅ PROXY WORKS! Polymarket is accessible.")
            print(f"\nSet this on Railway:")
            print(f'  railway variables --set "POLYMARKET_PROXY={proxy_url}"')
            return True
        elif r3.status_code == 403:
            print(f"\n❌ BLOCKED: Polymarket returned 403 (trading restricted)")
            print(f"   This proxy IP may be on a blocklist. Try a different zone/geo.")
            return False
        else:
            print(f"\n⚠️  Unexpected status codes. Check proxy configuration.")
            return False
            
    except httpx.ConnectTimeout:
        print(f"\n❌ Connection timed out. Check proxy host/port.")
        return False
    except httpx.ProxyError as e:
        print(f"\n❌ Proxy error: {e}")
        print(f"   Check username/password in proxy URL.")
        return False
    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {e}")
        return False


def set_railway_proxy(proxy_url: str):
    """Set POLYMARKET_PROXY on Railway."""
    import subprocess
    print(f"\nSetting POLYMARKET_PROXY on Railway...")
    cmd = f'railway variables --set "POLYMARKET_PROXY={proxy_url}"'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
    if result.returncode == 0:
        print(f"✅ POLYMARKET_PROXY set on Railway successfully!")
        print(f"Railway will redeploy automatically.")
    else:
        print(f"❌ Failed to set on Railway: {result.stderr}")
        print(f"\nManual command:")
        print(f'  {cmd}')


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nUsage:")
        print('  python scratch/setup_brightdata_proxy.py "http://user:pass@host:port"')
        print("\nBrightData standard residential proxy format:")
        print("  http://brd-customer-XXXXX-zone-residential:PASSWORD@brd.superproxy.io:22225")
        print("\nReplace XXXXX with your customer ID and PASSWORD with your zone password.")
        print("Get these from: https://brightdata.com/cp/zone/residential → Access parameters")
        sys.exit(1)
    
    proxy_url = sys.argv[1]
    
    if validate_proxy(proxy_url):
        # Ask to set on Railway
        answer = input("\nSet POLYMARKET_PROXY on Railway? (y/n): ").strip().lower()
        if answer == 'y':
            set_railway_proxy(proxy_url)
        else:
            print(f"\nManual command:")
            print(f'  railway variables --set "POLYMARKET_PROXY={proxy_url}"')