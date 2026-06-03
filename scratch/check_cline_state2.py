import sqlite3
import json

db_path = r"C:\Users\saini\AppData\Roaming\Code\User\globalStorage\state.vscdb"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Search for ANY key containing api, model, provider, context, window, max, token
cursor.execute("SELECT key FROM ItemTable WHERE key LIKE '%api%' OR key LIKE '%model%' OR key LIKE '%provider%' OR key LIKE '%context%' OR key LIKE '%token%' OR key LIKE '%profile%'")
keys = cursor.fetchall()
print("API/Model related keys:")
for k in keys:
    print(f"  {k[0]}")

# Also check for ALL keys in the saoudrizwan namespace
cursor.execute("SELECT key FROM ItemTable WHERE key LIKE '%saoudrizwan%' OR key LIKE '%claude-dev%'")
keys = cursor.fetchall()
print("\nAll saoudrizwan/claude-dev keys:")
for k in keys:
    print(f"  {k[0]}")

# Dump ALL keys to find any that might be relevant
cursor.execute("SELECT key FROM ItemTable")
all_keys = cursor.fetchall()
print(f"\nTotal keys: {len(all_keys)}")
for k in all_keys:
    if any(term in k[0].lower() for term in ['api', 'model', 'provider', 'context', 'token', 'profile', 'openai', 'cline']):
        cursor.execute("SELECT value FROM ItemTable WHERE key = ?", (k[0],))
        val = cursor.fetchone()
        if val:
            try:
                data = json.loads(val[0])
                print(f"\n{k[0]}:")
                print(json.dumps(data, indent=2)[:3000])
            except:
                print(f"\n{k[0]}: {val[0][:1000]}")

conn.close()