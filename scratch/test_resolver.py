#!/usr/bin/env python3
"""Quick test of the new resolver strategy ordering."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import logging
logging.basicConfig(level=logging.WARNING)

from resolver import run_resolution_check, get_accuracy_stats

print("=== Running resolution check ===")
result = run_resolution_check(verbose=True)

print(f"\n=== STATS ===")
stats = get_accuracy_stats()
print(f"Accuracy: {stats['accuracy_pct']}%")
print(f"Wins: {stats['wins']} | Losses: {stats['losses']} | Pushes: {stats['pushes']}")
print(f"PnL: ${stats['total_pnl']:+.2f}")
print(f"Resolved: {stats['total_resolved']}/{stats['total_logged']}")
print(f"Avg TTR: {stats['avg_ttr_hours']}h")