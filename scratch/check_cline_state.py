import sqlite3
import json

db_path = r"C:\Users\saini\AppData\Roaming\Code\User\globalStorage\state.vscdb"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Find all Cline-related keys
cursor.execute("SELECT key FROM ItemTable WHERE key LIKE '%saoudrizwan%' OR key LIKE '%cline%' OR key LIKE '%claude%'")
keys = cursor.fetchall()
print("Found keys:")
for k in keys:
    print(f"  {k[0]}")

print("\n--- Values ---")
for k in keys:
    cursor.execute("SELECT value FROM ItemTable WHERE key = ?", (k[0],))
    val = cursor.fetchone()
    if val:
        try:
            data = json.loads(val[0])
            print(f"\n{k[0]}:")
            print(json.dumps(data, indent=2)[:2000])
        except:
            print(f"\n{k[0]}: {val[0][:500]}")

conn.close()