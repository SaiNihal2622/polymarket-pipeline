#!/usr/bin/env python3
"""Fetch the full Google Doc content."""
import urllib.request
import re

doc_id = "155IMYCf9mjP379B4NZVIIz0DBmH-NQtCfwg7cgE_TkU"
url = f"https://docs.google.com/document/d/{doc_id}/export?format=txt"
try:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    r = urllib.request.urlopen(req, timeout=15)
    text = r.read().decode("utf-8", errors="replace")
    # Save to file
    with open("scratch/doc_content.txt", "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Saved {len(text)} chars to scratch/doc_content.txt")
except Exception as e:
    print(f"Error: {e}")