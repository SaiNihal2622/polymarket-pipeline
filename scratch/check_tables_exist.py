import sqlite3, os
db = os.getenv("DB_PATH", "trades.db")
if not os.path.exists(db):
    db = "trades.db"
conn = sqlite3.connect(db)
tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print(f"Database: {db}")
print(f"Tables ({len(tables)}): {tables}")

# Check for onchain/alert/sniper/order_flow tables
for t in ["onchain_alerts", "order_flow", "sniper_signals", "sniper_trades", "ai_insights"]:
    exists = t in tables
    print(f"  {t}: {'EXISTS' if exists else 'MISSING'}")
conn.close()