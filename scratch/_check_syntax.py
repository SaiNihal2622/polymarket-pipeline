import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    import config
    print(f"config OK: HOURS_WINDOW={config.DEMO_HOURS_WINDOW}, MAT={config.MATERIALITY_THRESHOLD}, CONSENSUS={config.CONSENSUS_PASSES}")
    import demo_runner
    print("demo_runner OK")
    import edge
    print("edge OK")
    print("\nAll imports successful - no syntax errors!")
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)