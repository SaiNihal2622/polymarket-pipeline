#!/usr/bin/env python3
"""Fetch the Google Doc content."""
import urllib.request
import re

# Convert to export URL
doc_id = "155IMYCf9mjP379B4NZVIIz0DBmH-NQtCfwg7cgE_TkU"
url = f"https://docs.google.com/document/d/{doc_id}/export?format=txt"
try:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    r = urllib.request.urlopen(req, timeout=15)
    text = r.read().decode("utf-8", errors="replace")
    print(text[:5000])
    if len(text) > 5000:
        print(f"\n... (truncated, total {len(text)} chars)")
except Exception as e:
    print(f"Error: {e}")
    # Try mobile URL
    try:
        url2 = f"https://docs.google.com/document/d/{doc_id}/mobilebasic"
        req2 = urllib.request.Request(url2, headers={"User-Agent": "Mozilla/5.0"})
        r2 = urllib.request.urlopen(req2, timeout=15)
        html = r2.read().decode("utf-8", errors="replace")
        # Strip HTML tags
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+', ' ', text).strip()
        print(text[:5000])
        if len(text) > 5000:
            print(f"\n... (truncated, total {len(text)} chars)")
    except Exception as e2:
        print(f"Error2: {e2}")