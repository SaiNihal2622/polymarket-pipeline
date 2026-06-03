import urllib.request, json, ssl

ctx = ssl.create_default_context()

# Check various endpoints
urls = [
    "https://polymarket-pipeline-production.up.railway.app/",
    "https://polymarket-pipeline-production.up.railway.app/api/trades",
    "https://polymarket-pipeline-production.up.railway.app/api/profits",
]

for url in urls:
    try:
        r = urllib.request.urlopen(url, timeout=15, context=ctx)
        data = r.read().decode()[:500]
        print(f"OK {url}")
        print(f"  {data[:300]}")
    except Exception as e:
        code = getattr(e, 'code', None)
        body = ""
        if hasattr(e, 'read'):
            try:
                body = e.read().decode()[:200]
            except:
                pass
        print(f"ERR {url}: {e}")
        if body:
            print(f"  body: {body}")
    print()