"""
Monkey-patch py_clob_client (V1 or V2) to route ALL CLOB requests through a residential proxy.

Usage:
  Set POLYMARKET_PROXY=http://user:pass@host:port in Railway env vars.
  This module will be imported at startup and patch the HTTP client.

Recommended proxy services (cheapest):
  - BrightData: https://brightdata.com ($1/GB pay-as-you-go)
  - SmartProxy: https://smartproxy.com ($4/month)
  - PacketStream: https://packetstream.io ($1/GB)
"""
import os
import httpx

_proxy_url = os.getenv('POLYMARKET_PROXY') or os.getenv('HTTPS_PROXY')

if _proxy_url:
    # Try V2 SDK first, then fall back to V1
    _patched = False
    try:
        import py_clob_client_v2.http_helpers.helpers as _helpers
        _helpers._http_client = httpx.Client(
            proxy=_proxy_url,
            http2=True,
            timeout=30,
        )
        print(f"[proxy] V2 CLOB traffic routed through residential proxy: {_proxy_url[:40]}...")
        _patched = True
    except Exception as e:
        print(f"[proxy] V2 proxy patch failed: {e}")

    if not _patched:
        try:
            import py_clob_client.http_helpers.helpers as _helpers
            _helpers._http_client = httpx.Client(
                proxy=_proxy_url,
                http2=True,
                timeout=30,
            )
            print(f"[proxy] V1 CLOB traffic routed through residential proxy: {_proxy_url[:40]}...")
        except Exception as e:
            print(f"[proxy] WARNING: Could not patch CLOB proxy: {e}")
else:
    print("[proxy] No POLYMARKET_PROXY set — using direct connection (may be blocked)")