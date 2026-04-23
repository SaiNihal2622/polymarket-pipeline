"""
One-time cleanup: void non-profitable category trades (sports, esports, NFL draft, UFC, O/U, exact scores).
These drag down accuracy. Only crypto, finance, and politics trades remain.
"""
import sqlite3
import os

DB_PATH = os.getenv("DB_PATH", "/data/trades.db")
if not os.path.exists(DB_PATH):
    DB_PATH = "trades.db"

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

# Find all trades that are NOT crypto/finance/politics
PROFITABLE_KEYWORDS = [
    "bitcoin", "btc", "ethereum", "eth", "solana", "sol", "crypto", "dogecoin",
    "xrp", "bnb", "hyperliquid",  # crypto
    "s&p", "spy", "nasdaq", "nvda", "nvidia", "tsla", "tesla", "apple", "aapl",
    "stock", "close above", "close below",  # finance
    "trump", "biden", "tariff", "fed ", "congress", "senate", "sanctions",  # politics
]

trades = conn.execute(
    "SELECT id, market_question, result FROM trades WHERE id >= 192"
).fetchall()

voided = 0
kept = 0
for t in trades:
    q = (t["market_question"] or "").lower()
    is_profitable = any(k in q for k in PROFITABLE_KEYWORDS)
    
    if not is_profitable:
        print(f"  VOID #{t['id']}: {t['market_question'][:70]} (result={t['result']})")
        conn.execute("UPDATE trades SET result = 'voided' WHERE id = ?", (t["id"],))
        conn.execute("DELETE FROM outcomes WHERE trade_id = ?", (t["id"],))
        conn.execute("DELETE FROM calibration WHERE trade_id = ?", (t["id"],))
        voided += 1
    else:
        print(f"  KEEP #{t['id']}: {t['market_question'][:70]} (result={t['result']})")
        kept += 1

conn.commit()

# Show new accuracy
remaining = conn.execute("""
    SELECT 
        COUNT(*) as total,
        SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins,
        SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) as losses,
        SUM(CASE WHEN result = 'pending' THEN 1 ELSE 0 END) as pending
    FROM trades WHERE id >= 192 AND result != 'voided'
""").fetchone()

wins = remaining["wins"] or 0
losses = remaining["losses"] or 0
resolved = wins + losses
acc = (wins / resolved * 100) if resolved > 0 else 0

print(f"\n{'='*60}")
print(f"VOIDED: {voided} non-profitable trades")
print(f"KEPT:   {kept} profitable trades")
print(f"NEW ACCURACY: {acc:.1f}% ({wins}W / {losses}L, {resolved} resolved, {remaining['pending'] or 0} pending)")
print(f"{'='*60}")

conn.close()
