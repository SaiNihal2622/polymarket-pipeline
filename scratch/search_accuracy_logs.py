import re
from pathlib import Path

# Try common encodings
encodings = ['utf-16', 'utf-16-le', 'utf-8', 'latin-1']
file_path = Path("c:/Users/saini/Desktop/iplclaude/dry_run_out.txt")

for enc in encodings:
    try:
        content = file_path.read_text(encoding=enc)
        print(f"--- Encoding: {enc} ---")
        lines = content.splitlines()
        for i, line in enumerate(lines):
            if "accuracy" in line.lower() or "acc:" in line.lower() or "20%" in line:
                print(f"Line {i+1}: {line.strip()}")
    except Exception as e:
        print(f"Failed with {enc}: {e}")
