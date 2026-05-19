#!/usr/bin/env python3
"""Extract all files from upstream/main into scratch/brody-reference/"""
import subprocess
import os

out_dir = "scratch/brody-reference"
os.makedirs(out_dir, exist_ok=True)

# Get file list from upstream/main
result = subprocess.run(["git", "ls-tree", "--name-only", "upstream/main"], capture_output=True, text=True)
files = result.stdout.strip().split("\n")

for f in files:
    out_path = os.path.join(out_dir, f)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    r = subprocess.run(["git", "show", f"upstream/main:{f}"], capture_output=True)
    with open(out_path, "wb") as fh:
        fh.write(r.stdout)
    print(f"  extracted: {f} ({len(r.stdout)} bytes)")

print(f"\nDone: {len(files)} files extracted to {out_dir}/")