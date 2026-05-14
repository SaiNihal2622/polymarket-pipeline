#!/usr/bin/env python3
"""Fetch and analyze the live dashboard HTML."""
import urllib.request
import re
import json

BASE = "https://industrious-blessing-production-b110.up.railway.app"

try:
    resp = urllib.request.urlopen(BASE + "/", timeout=15)
    html = resp.read().decode('utf-8', errors='ignore')
    
    # Save full HTML for inspection
    with open("scratch/live_dashboard.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Saved {len(html)} bytes to scratch/live_dashboard.html")
    
    # Extract key stats
    print("\n=== DASHBOARD STATS ===")
    stats = re.findall(r'class="stat-label">(.*?)</span><span class="stat-value[^"]*">(.*?)</span>', html)
    for label, val in stats:
        clean_val = re.sub(r'<[^>]+>', '', val).strip()
        print(f"  {label}: {clean_val}")
    
    # Extract trade rows
    print("\n=== TRADE ROWS ===")
    rows = re.findall(r'<tr>\s*<td class="muted">(.*?)</td>\s*<td class="question-cell"[^>]*>(.*?)</td>\s*<td><span class="pill pill-(\w+)">(.*?)</span></td>\s*<td class="(\w+)">([+-]?[\d.]+%)</td>\s*<td>\$([\d.]+)</td>', html, re.DOTALL)
    
    if not rows:
        # Try simpler pattern
        rows = re.findall(r'<td class="muted">([\d:]+)</td>', html)
        print(f"  Found {len(rows)} time entries")
    
    # Check for trade table data
    trade_data = re.findall(r'<tr>\s*<td[^>]*>(.*?)</td>.*?<td[^>]*>(.*?)</td>.*?<td[^>]*>(.*?)</td>', html, re.DOTALL)
    print(f"  Total table rows with data: {len(trade_data)}")
    
    # Check for dates/timestamps
    dates = re.findall(r'2026-\d{2}-\d{2}', html)
    if dates:
        print(f"\n=== DATES FOUND ===")
        for d in sorted(set(dates)):
            print(f"  {d}")
    
    # Check what the dashboard says about DB state
    print("\n=== DB DIAGNOSTICS ===")
    db_info = re.findall(r'Counts.*?{.*?}', html)
    for info in db_info:
        print(f"  {info}")
    
    # Check for any "last trade" or "last update" info
    last_info = re.findall(r'(?:last|Last|latest|Latest).*?(?:trade|Trade|update|Update).*?</\w+>', html)
    for info in last_info:
        print(f"  {info}")
    
    # Check for signal/trade data embedded in page
    print("\n=== LOOKING FOR TRADE DETAILS ===")
    trade_details = re.findall(r'\$[\d.]+.*?(?:WIN|LOSS|pending)', html[:5000])
    for td in trade_details[:10]:
        clean = re.sub(r'<[^>]+>', '', td).strip()
        print(f"  {clean[:100]}")
        
except Exception as e:
    print(f"Error: {e}")