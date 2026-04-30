import sqlite3
import httpx
import time

GAMMA_API = "https://gamma-api.polymarket.com"

def get_token_id_from_gamma(market_id):
    try:
        # Gamma API for a specific market
        resp = httpx.get(f"{GAMMA_API}/markets", params={"id": market_id}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            # It might be a list or a single object
            m = data[0] if isinstance(data, list) and len(data) > 0 else data
            if isinstance(m, dict):
                clob_token_ids = m.get("clobTokenIds")
                if isinstance(clob_token_ids, str):
                    import json
                    clob_token_ids = json.loads(clob_token_ids)
                if clob_token_ids and len(clob_token_ids) > 0:
                    return clob_token_ids[0] # YES token
    except Exception as e:
        print(f"Error fetching {market_id}: {e}")
    return None

def backfill():
    conn = sqlite3.connect('trades.db')
    conn.row_factory = sqlite3.Row
    trades = conn.execute("SELECT id, market_id FROM trades WHERE token_id IS NULL").fetchall()
    
    print(f"Found {len(trades)} trades to backfill.")
    
    count = 0
    for t in trades:
        tid = get_token_id_from_gamma(t['market_id'])
        if tid:
            conn.execute("UPDATE trades SET token_id = ? WHERE id = ?", (tid, t['id']))
            count += 1
            print(f"Updated trade {t['id']} with token {tid}")
        else:
            print(f"Could not find token for trade {t['id']} (market {t['market_id']})")
        
        conn.commit()
        time.sleep(0.1) # Be nice to the API
        
    conn.close()
    print(f"Finished. Updated {count} trades.")

if __name__ == "__main__":
    backfill()
