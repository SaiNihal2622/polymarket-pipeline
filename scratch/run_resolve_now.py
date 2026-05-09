#!/usr/bin/env python3
"""Quick resolution check + accuracy stats."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from resolver import run_resolution_check, get_accuracy_stats

print("=" * 60)
print("RUNNING RESOLUTION CHECK...")
print("=" * 60)
run_resolution_check(verbose=True)

stats = get_accuracy_stats()
print()
print("=" * 60)
print(f"ACCURACY:  {stats['accuracy_pct']}%")
print(f"RECORD:    {stats['wins']}W / {stats['losses']}L / {stats['pushes']}P")
print(f"PnL:       ${stats['total_pnl']:+.2f}")
print(f"RESOLVED:  {stats['total_resolved']} / {stats['total_logged']}")
print(f"PENDING:   {stats['total_logged'] - stats['total_resolved']}")
print(f"AVG TTR:   {stats['avg_ttr_hours']}h")
print(f"READY:     {'YES ✅' if stats['ready_for_live'] else 'NOT YET ❌'}")
print("=" * 60)