from pathlib import Path

file_path = Path("c:/Users/saini/Desktop/iplclaude/ipl_live.log")
if not file_path.exists():
    print("File not found")
    exit()

content = file_path.read_text(errors='ignore')
lines = content.splitlines()
for i, line in enumerate(lines):
    if "20%" in line or "accuracy" in line.lower():
        print(f"Line {i+1}: {line}")
