"""
cleanup_trades.py — void trades whose markets close more than 7 days away.
Queries Gamma API to get real end_date per market.
Run once at startup via Procfile, then Procfile reverts.
"""
import sqlite3, os, httpx, json
from pathlib import Path
from datetime import datetime, timezone, timedelta

db = Path(os.getenv("DB_PATH", "/data/trades.db"))
conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row

rows = conn.execute(
    "SELECT id, market_id, market_question FROM trades WHERE status IN ('demo','dry_run')"
).fetchall()
print(f"Total active trades: {len(rows)}")

cutoff = datetime.now(timezone.utc) + timedelta(days=7)
void_ids = []

for r in rows:
    mid = r["market_id"]
    if not mid:
        continue
    try:
        resp = httpx.get(
            "https://gamma-api.polymarket.com/markets",
            params={"conditionIds": mid, "limit": 1},
            timeout=8,
        )
        data = resp.json()
        items = data if isinstance(data, list) else data.get("data", [])
        if not items:
            void_ids.append(r["id"])
            print(f"  VOID #{r['id']} (no market data): {r['market_question'][:55]}")
            continue
        m = items[0]
        end_str = m.get("endDate") or m.get("end_date_iso") or ""
        if end_str:
            end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
            if end_dt > cutoff:
                void_ids.append(r["id"])
                print(f"  VOID #{r['id']} (closes {end_dt.date()}): {r['market_question'][:55]}")
    except Exception as e:
        print(f"  SKIP #{r['id']}: {e}")

print(f"\nVoiding {len(void_ids)} long-dated trades...")
if void_ids:
    conn.execute(
        f"UPDATE trades SET status='voided' WHERE id IN ({','.join('?'*len(void_ids))})",
        void_ids,
    )
    conn.commit()

remaining = conn.execute(
    "SELECT COUNT(*) FROM trades WHERE status IN ('demo','dry_run')"
).fetchone()[0]
print(f"Active trades remaining: {remaining}")
conn.close()
