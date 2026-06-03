"""Test BrightData residential proxy with various auth formats."""
import httpx

ZONE_PASS = "d942f5e4-c950-4f86-bb43-003ff91ce248"

# Try different BrightData proxy URL formats
formats = [
    f"http://brd-customer-CUSTOMER_ID-zone-residential:{ZONE_PASS}@brd.superproxy.io:22225",
    f"http://brd:{ZONE_PASS}@brd.superproxy.io:22225",
    f"http://lum-customer-customer-zone-residential:{ZONE_PASS}@zproxy.lum-superproxy.io:22225",
]

for i, proxy_url in enumerate(formats):
    print(f"\nFormat {i+1}: {proxy_url[:50]}...")
    try:
        c = httpx.Client(proxy=proxy_url, timeout=10)
        r = c.get("https://api.ipify.org?format=json")
        print(f"  Exit IP: {r.json()['ip']}")
        c.close()
        break
    except Exception as e:
        err = str(e)[:100]
        print(f"  Error: {err}")