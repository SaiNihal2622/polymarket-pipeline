"""
Free Proxy Finder for Polymarket Order Placement.

Tests multiple free approaches to bypass ISP block and Polymarket geo-restriction:
1. Cloudflare WARP (free, unlimited)
2. Free SOCKS5/HTTP proxies (scraped from public lists)
3. Tor (if installed)
4. Local SOCKS5 proxy detection (e.g., from VPN apps)

Usage:
    python scratch/free_proxy_finder.py
"""
import httpx
import json
import time
import socket
import subprocess
import sys
import os

POLYMARKET_TIME = "https://clob.polymarket.com/time"
POLYMARKET_DERIVE = "https://clob.polymarket.com/derive-api-key"
IP_CHECK = "https://api.ipify.org?format=json"
TIMEOUT = 12

def test_endpoint(client, url, label):
    """Test a URL and return (status_code, body_preview, error)."""
    try:
        r = client.get(url, timeout=TIMEOUT)
        return r.status_code, r.text[:200], None
    except httpx.ConnectTimeout:
        return None, None, "ConnectTimeout"
    except httpx.ConnectError as e:
        return None, None, f"ConnectError"
    except httpx.ProxyError as e:
        return None, None, f"ProxyError"
    except Exception as e:
        return None, None, f"{type(e).__name__}"


def test_proxy(proxy_url, label="proxy"):
    """Test if a proxy can reach Polymarket and place orders."""
    print(f"\n{'='*60}")
    print(f"Testing: {label}")
    print(f"URL: {proxy_url[:60]}...")
    print(f"{'='*60}")
    
    try:
        if proxy_url.startswith("socks"):
            # SOCKS proxy needs httpx[socks]
            try:
                import socksio
                client = httpx.Client(proxy=proxy_url, timeout=TIMEOUT)
            except ImportError:
                print("  ⚠️  SOCKS support not installed. Install: pip install httpx[socks]")
                return None
        else:
            client = httpx.Client(proxy=proxy_url, timeout=TIMEOUT)
        
        # Step 1: Check exit IP
        status, body, err = test_endpoint(client, IP_CHECK, "Exit IP")
        if err:
            print(f"  ❌ Exit IP check failed: {err}")
            client.close()
            return None
        exit_ip = json.loads(body)["ip"]
        print(f"  📍 Exit IP: {exit_ip}")
        
        # Step 2: Test Polymarket /time
        status, body, err = test_endpoint(client, POLYMARKET_TIME, "Polymarket time")
        if err:
            print(f"  ❌ Polymarket /time failed: {err}")
            client.close()
            return None
        print(f"  ⏰ Polymarket /time: {status} {body[:50]}")
        
        # Step 3: Test derive-api-key (CRITICAL - this is what orders hit)
        status, body, err = test_endpoint(client, POLYMARKET_DERIVE, "derive-api-key")
        if err:
            print(f"  ❌ derive-api-key failed: {err}")
            client.close()
            return None
        print(f"  🔑 derive-api-key: {status}")
        
        client.close()
        
        if status == 403:
            print(f"  ❌ BLOCKED (403) - IP is on Polymarket's blocklist")
            return None
        elif status in (200, 400, 401, 404):
            print(f"  ✅ WORKS! Status {status} means Polymarket accepts this IP")
            print(f"  📋 Use this proxy: {proxy_url}")
            return proxy_url
        else:
            print(f"  ⚠️  Unexpected status: {status}")
            return None
            
    except Exception as e:
        print(f"  ❌ Error: {type(e).__name__}: {e}")
        return None


def check_cloudflare_warp():
    """Check if Cloudflare WARP is available."""
    print("\n" + "="*60)
    print("CHECKING: Cloudflare WARP")
    print("="*60)
    
    # Check if warp-cli exists
    try:
        r = subprocess.run(["warp-cli", "--version"], capture_output=True, text=True, timeout=5)
        print(f"  WARP CLI found: {r.stdout.strip()}")
        
        # Check connection status
        r2 = subprocess.run(["warp-cli", "status"], capture_output=True, text=True, timeout=5)
        print(f"  Status: {r2.stdout.strip()}")
        
        if "Connected" in r2.stdout:
            print("  WARP is connected! Testing Polymarket...")
            # Test direct (WARP should be intercepting)
            try:
                client = httpx.Client(timeout=TIMEOUT)
                r = client.get(IP_CHECK, timeout=10)
                ip = r.json()["ip"]
                print(f"  WARP exit IP: {ip}")
                
                r2 = client.get(POLYMARKET_DERIVE, timeout=10)
                print(f"  Polymarket derive-api-key: {r2.status_code}")
                client.close()
                
                if r2.status_code != 403:
                    print("  ✅ WARP works for Polymarket!")
                    return True
                else:
                    print("  ❌ WARP IP is blocked by Polymarket (403)")
                    return False
            except Exception as e:
                print(f"  ❌ WARP test failed: {e}")
                return False
        else:
            print("  WARP is not connected.")
            print("  To connect: warp-cli connect")
            return False
            
    except FileNotFoundError:
        print("  WARP CLI not installed.")
        print("  Install from: https://1.1.1.1/ or run:")
        print("  winget install Cloudflare.Warp")
        return False
    except Exception as e:
        print(f"  Error: {e}")
        return False


def scrape_free_proxies():
    """Scrape free proxy lists."""
    print("\n" + "="*60)
    print("SCRAPING FREE PROXIES...")
    print("="*60)
    
    proxies = []
    
    # Source 1: proxyscrape.com
    try:
        r = httpx.get(
            "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=5000&country=US&ssl=yes&anonymity=all",
            timeout=10
        )
        if r.status_code == 200:
            lines = r.text.strip().split('\n')
            for line in lines[:20]:
                line = line.strip()
                if ':' in line and '.' in line:
                    proxies.append(f"http://{line}")
            print(f"  proxyscrape.com: {len(proxies)} proxies")
    except Exception as e:
        print(f"  proxyscrape.com failed: {e}")
    
    # Source 2: geonode.com
    try:
        r = httpx.get(
            "https://proxylist.geonode.com/api/proxy-list?limit=20&page=1&sort_by=lastChecked&sort_type=desc&protocols=http%2Chttps&country=US",
            timeout=10
        )
        if r.status_code == 200:
            data = r.json()
            for p in data.get("data", []):
                ip = p.get("ip")
                port = p.get("port")
                if ip and port:
                    proxies.append(f"http://{ip}:{port}")
            print(f"  geonode.com: added more proxies")
    except Exception as e:
        print(f"  geonode.com failed: {e}")
    
    # Source 3: free-proxy-list.net
    try:
        r = httpx.get("https://api.openproxylist.xyz/http.txt", timeout=10)
        if r.status_code == 200:
            for line in r.text.strip().split('\n')[:30]:
                line = line.strip()
                if ':' in line:
                    proxies.append(f"http://{line}")
            print(f"  openproxylist.xyz: added more proxies")
    except Exception as e:
        print(f"  openproxylist.xyz failed: {e}")
    
    print(f"  Total proxies to test: {len(proxies)}")
    return proxies


def check_local_vpn_proxy():
    """Check for local VPN/proxy software running."""
    print("\n" + "="*60)
    print("CHECKING: Local VPN/Proxy Software")
    print("="*60)
    
    common_ports = {
        1080: "SOCKS5 (common VPN)",
        7890: "Clash",
        7891: "Clash (alt)",
        10808: "V2Ray",
        10809: "V2Ray (alt)",
        1087: "Shadowsocks",
        8080: "HTTP proxy",
        3128: "Squid proxy",
        9050: "Tor SOCKS",
        9051: "Tor control",
        40000: "NordVPN",
        40001: "NordVPN (alt)",
    }
    
    found = []
    for port, name in common_ports.items():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            if s.connect_ex(('127.0.0.1', port)) == 0:
                print(f"  ✅ Port {port} open: {name}")
                found.append((port, name))
            s.close()
        except:
            pass
    
    if not found:
        print("  No local proxy/VPN detected")
    
    return found


def main():
    print("="*60)
    print("FREE PROXY FINDER FOR POLYMARKET")
    print("="*60)
    
    working_proxy = None
    
    # 1. Check Cloudflare WARP
    if check_cloudflare_warp():
        working_proxy = "warp"
    
    # 2. Check local VPN/proxy
    if not working_proxy:
        local_proxies = check_local_vpn_proxy()
        for port, name in local_proxies:
            if "SOCKS" in name.upper():
                result = test_proxy(f"socks5://127.0.0.1:{port}", f"Local {name}")
            else:
                result = test_proxy(f"http://127.0.0.1:{port}", f"Local {name}")
            if result:
                working_proxy = result
                break
    
    # 3. Scrape and test free proxies
    if not working_proxy:
        free_proxies = scrape_free_proxies()
        # Test up to 15 proxies
        for i, proxy in enumerate(free_proxies[:15]):
            result = test_proxy(proxy, f"Free proxy #{i+1}")
            if result:
                working_proxy = result
                break
            time.sleep(0.5)  # Be nice to proxy servers
    
    # Summary
    print("\n" + "="*60)
    print("RESULTS")
    print("="*60)
    
    if working_proxy:
        print(f"\n✅ FOUND WORKING PROXY: {working_proxy}")
        print(f"\nTo use with Railway:")
        print(f'  railway variables --set "POLYMARKET_PROXY={working_proxy}"')
        print(f"\nTo test locally:")
        print(f'  set POLYMARKET_PROXY={working_proxy}')
        print(f'  python demo_runner.py --once')
    else:
        print("\n❌ No free working proxy found.")
        print("\nRECOMMENDED OPTIONS (cheapest first):")
        print("  1. BrightData $2 balance (already funded) — create zone at:")
        print("     https://brightdata.com/cp/zone/residential")
        print("  2. Smartproxy free trial (3 days, 100MB):")
        print("     https://smartproxy.com")
        print("  3. Oxylabs free trial (7 days):")
        print("     https://oxylabs.io")
        print("  4. Install Cloudflare WARP and try:")
        print("     winget install Cloudflare.Warp")
        print("     warp-cli connect")
        print("  5. Use phone mobile data as hotspot (mobile IPs = residential)")


if __name__ == "__main__":
    main()