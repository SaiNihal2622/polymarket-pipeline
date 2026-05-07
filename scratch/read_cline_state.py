import sqlite3
import json

db_path = r"C:\Users\saini\AppData\Roaming\Code\User\globalStorage\state.vscdb"
conn = sqlite3.connect(db_path)
cur = conn.cursor()

cur.execute("SELECT value FROM ItemTable WHERE key = 'saoudrizwan.claude-dev'")
row = cur.fetchone()
if row:
    data = json.loads(row[0])
    print(json.dumps(data, indent=2))
else:
    print("No data found")

conn.close()