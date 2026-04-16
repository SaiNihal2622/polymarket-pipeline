"""
One-shot cleanup: void all long-dated trades that won't resolve within 7 days.
Run once on Railway, then delete this file.
"""
import sqlite3, os
from pathlib import Path

db = Path(os.getenv("DB_PATH", "/data/trades.db"))
conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row

total = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
print(f"Total trades before cleanup: {total}")

JUNK_KEYWORDS = [
    "2027", "world series", "french open", "governor", "senator",
    "champions league winner", "premier league winner", "nba champion",
    "super bowl", "afc championship", "nfc championship", "eurovision",
    "lpl 2026 season", "ipl champion", "grammy", "oscar", "nobel",
    "election", "president", "congress", "republican", "democrat",
    "tom begich", "judy shelton", "fed chair",
    "yankees win", "dodgers win", "chargers win", "chiefs win",
    "djokovic win the 2026", "alcaraz win the 2026",
    "rbc heritage",  # golf tournament weeks away
]

rows = conn.execute("SELECT id, market_question FROM trades WHERE status IN ('demo','dry_run')").fetchall()
void_ids = []
for r in rows:
    q = r["market_question"].lower()
    if any(k in q for k in JUNK_KEYWORDS):
        void_ids.append(r["id"])

print(f"Voiding {len(void_ids)} long-dated trades...")
for i in void_ids:
    print(f"  #{i}: {conn.execute('SELECT market_question FROM trades WHERE id=?',(i,)).fetchone()[0][:60]}")

if void_ids:
    conn.execute(f"UPDATE trades SET status='voided' WHERE id IN ({','.join('?'*len(void_ids))})", void_ids)
    conn.commit()

remaining = conn.execute("SELECT COUNT(*) FROM trades WHERE status IN ('demo','dry_run')").fetchone()[0]
print(f"\nDone. Active trades remaining: {remaining}")
conn.close()
