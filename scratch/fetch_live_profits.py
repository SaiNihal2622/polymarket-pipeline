import urllib.request
import re
import json

urls = [
    "https://demo-runner-production-3f90.up.railway.app/",
    "https://demo-runner-production-3f90.up.railway.app/diagnostics",
]

for url in urls:
    print(f"\n{'='*60}")
    print(f"Fetching: {url}")
    print('='*60)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode()
        
        print(f"Status: {resp.status}")
        print(f"Page length: {len(html)} chars")
        
        # Strip HTML tags and extract readable text
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', '\n', text)
        text = re.sub(r'\n\s*\n', '\n', text)
        text = re.sub(r'[ \t]+', ' ', text)
        
        # Print non-empty lines
        for line in text.split('\n'):
            line = line.strip()
            if line and len(line) > 2:
                print(line)
                
    except Exception as e:
        print(f"Error: {e}")