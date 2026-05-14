#!/usr/bin/env python3
"""Dump live_trades.json raw data."""
import json

with open("scratch/live_trades.json") as f:
    raw = json.load(f)

data = raw if isinstance(raw, list) else raw.get("data", raw)

# Show first 3 records with all keys
for i, row in enumerate(data[:3]):
    print(f"\n--- Record {i} ---")
    if isinstance(row, dict):
        for k, v in row.items():
            print(f"  {k}: {repr(v)}")
    else:
        print(f"  RAW: {repr(row)}")

print(f"\nTotal records: {len(data)}")