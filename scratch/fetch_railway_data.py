"""Fetch live trade data from Railway deployment."""
import urllib.request
import json
import re

URLS = {
    "trades_api": "https://industrious-blessing-production.up.railway.app/api/trades",
    "root": "https://industrious-blessing-production.up.railway.app/",
    "diagnostics": "https://industrious-blessing-production.up.railway.app/diagnostics",
}

def fetch(url, label):
    print(f"\n{'='*60}")
    print(f"FETCHING: {label}")
    print(f"URL: {url}")
    print("="*60)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read().decode()
        
        print(f"Status: {resp.status}")
        print(f"Content-Type: {resp.headers.get('content-type', 'unknown')}")
        print(f"Length: {len(data)} chars")
        
        # Try JSON parse
        try:
            j = json.loads(data)
            print(f"\nJSON Response:")
            print(json.dumps(j, indent=2, default=str)[:5000])
        except:
            # HTML - strip tags
            text = re.sub(r'<script[^>]*>.*?</script>', '', data, flags=re.DOTALL)
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
            text = re.sub(r'<[^>]+>', '\n', text)
            text = re.sub(r'\n\s*\n', '\n', text)
            text = re.sub(r'[ \t]+', ' ', text)
            
            print(f"\nExtracted text:")
            for line in text.split('\n'):
                line = line.strip()
                if line and len(line) > 2:
                    print(f"  {line}")
    except Exception as e:
        print(f"Error: {e}")

def main():
    for key, url in URLS.items():
        fetch(url, key)
    
    # Also try specific API endpoints
    extra_urls = [
        "https://industrious-blessing-production.up.railway.app/api/stats",
        "https://industrious-blessing-production.up.railway.app/api/pnl",
        "https://industrious-blessing-production.up.railway.app/api/summary",
    ]
    for url in extra_urls:
        fetch(url, url.split('/')[-1])

if __name__ == "__main__":
    main()