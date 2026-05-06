import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from resolver import get_accuracy_stats, get_pipeline_comparison, get_signal_accuracies

print("=== OVERALL ACCURACY ===")
stats = get_accuracy_stats()
for k, v in stats.items():
    print(f"  {k}: {v}")

print()
print("=== PIPELINE COMPARISON ===")
comp = get_pipeline_comparison()
old = comp["old"]
new = comp["new"]
print(f"  OLD: {old}")
print(f"  NEW: {new}")
print(f"  Categories:")
for cat, data in comp.get("new_categories", {}).items():
    print(f"    {cat}: {data}")

print()
print("=== PER-SIGNAL ACCURACY ===")
for sig, s in get_signal_accuracies().items():
    print(f"  {s['label']:15s}: {s['accuracy_pct']:5.1f}% ({s['wins']}W/{s['losses']}L, conf={s['avg_conf']:.2f})")