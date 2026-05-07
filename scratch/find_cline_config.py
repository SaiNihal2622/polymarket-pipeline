import sqlite3
import json

db_path = r"C:\Users\saini\AppData\Roaming\Code\User\globalStorage\state.vscdb"
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# Find all keys related to cline/claude-dev
cur.execute("SELECT key FROM ItemTable WHERE key LIKE '%cline%' OR key LIKE '%claude-dev%'")
keys = cur.fetchall()
print("=== Cline-related keys ===")
for k in keys:
    print(k[0])

# Also check for api provider config
cur.execute("SELECT key FROM ItemTable WHERE key LIKE '%api%' OR key LIKE '%provider%' OR key LIKE '%model%'")
keys2 = cur.fetchall()
print("\n=== API/Provider/Model keys ===")
for k in keys2:
    print(k[0])

conn.close()