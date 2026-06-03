"""
proxy_manager.py — Automatically find a working proxy to bypass Polymarket geoblocking.
Fetches free US/EU proxies and tests which ones can reach the CLOB API.
"""
import os
import httpx
import logging

log = logging.getLogger("proxy_manager")

CLOB_TEST_URL = "https://clob.polymarket.com/time"
PROXY_SOURCES = [
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=5000&country=US&ssl=all&anonymity=all",
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=5000&country=GB,DE,FR,NL&ssl=all&anonymity=all",
]

_working_proxy = None


def fetch_proxies():
    """Fetch fresh proxy lists from multiple sources."""
    all_proxies = []
    for url in PROXY_SOURCES:
        try:
            r = httpx.get(url, timeout=10)
            if r.status_code == 200:
                proxies = [p.strip() for p in r.text.strip().split("\n") if p.strip()]
                all_proxies.extend(proxies)
        except Exception:
            pass
    return all_proxies


def test_proxy(proxy_addr):
    """Test if a proxy can reach Polymarket CLOB API."""
    proxy_url = f"http://{proxy_addr}"
    try:
        r = httpx.get(CLOB_TEST_URL, proxy=proxy_url, timeout=10)
        if r.status_code == 200 and len(r.text.strip()) > 5:
            return True
    except Exception:
        pass
    return False


def find_working_proxy():
    """Find and return a working proxy for CLOB API access."""
    global _working_proxy
    if _working_proxy:
        # Test cached proxy
        if test_proxy(_working_proxy):
            return _working_proxy
        _working_proxy = None

    log.info("[proxy] Fetching fresh proxy list...")
    proxies = fetch_proxies()
    log.info(f"[proxy] Found {len(proxies)} proxies to test")

    for p in proxies[:20]:  # Test up to 20 proxies
        if test_proxy(p):
            _working_proxy = p
            log.info(f"[proxy] ✅ Working proxy found: {p}")
            return p

    log.warning("[proxy] ❌ No working proxy found")
    return None


def get_clob_host():
    """Return the CLOB host URL - either direct or through a proxy."""
    explicit_proxy = os.getenv("CLOB_PROXY", "")
    if explicit_proxy:
        return explicit_proxy

    proxy = find_working_proxy()
    if proxy:
        os.environ["HTTPS_PROXY"] = f"http://{proxy}"
        os.environ["HTTP_PROXY"] = f"http://{proxy}"
        return proxy
    return None