"""Test all APIs after dotenv fix."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import config

print(f"LLM Provider: {config.LLM_PROVIDER}")
print(f"Classification Model: {config.CLASSIFICATION_MODEL}")
print(f"NVIDIA Key: {bool(config.NVIDIA_API_KEY)}")
print(f"Groq Key: {bool(config.GROQ_API_KEY)}")
print(f"POLY_API_KEY: {bool(config.POLY_API_KEY)}")
print(f"DB_PATH: {config.DB_PATH}")
print(f"DRY_RUN: {config.DRY_RUN}")
print(f"EDGE_THRESHOLD: {config.EDGE_THRESHOLD}")
print(f"TRADES_PER_DAY: {config.TRADES_PER_DAY}")
print(f"MAX_BET_USD: {config.MAX_BET_USD}")
print()

# Test 1: Polymarket API
print("=" * 60)
print("TEST 1: Polymarket Gamma API")
try:
    import httpx
    resp = httpx.get(
        "https://gamma-api.polymarket.com/markets",
        params={"limit": 5, "active": "true", "closed": "false", "order": "volume", "ascending": "false"},
        timeout=30, verify=False
    )
    data = resp.json()
    items = data if isinstance(data, list) else data.get("data", [])
    print(f"  Status: {resp.status_code}")
    print(f"  Markets: {len(items)}")
    if items:
        print(f"  Sample: {items[0].get('question', 'N/A')[:80]}")
    print("  RESULT: PASS")
except Exception as e:
    print(f"  RESULT: FAIL - {e}")

# Test 2: LLM API (NVIDIA)
print()
print("=" * 60)
print("TEST 2: NVIDIA LLM API")
try:
    from classifier import _call_llm
    result = _call_llm("Say 'API works' in exactly those words", temperature=0.1)
    print(f"  Response: {result[:100]}")
    print("  RESULT: PASS")
except Exception as e:
    print(f"  RESULT: FAIL - {e}")

# Test 3: News API
print()
print("=" * 60)
print("TEST 3: NewsAPI")
try:
    if config.NEWSAPI_KEY:
        resp = httpx.get(
            "https://newsapi.org/v2/top-headlines",
            params={"country": "us", "pageSize": 3, "apiKey": config.NEWSAPI_KEY},
            timeout=10
        )
        data = resp.json()
        print(f"  Status: {resp.status_code}")
        print(f"  Articles: {len(data.get('articles', []))}")
        print("  RESULT: PASS")
    else:
        print("  RESULT: SKIP (no NEWSAPI_KEY)")
except Exception as e:
    print(f"  RESULT: FAIL - {e}")

# Test 4: Database
print()
print("=" * 60)
print("TEST 4: Database")
try:
    from logger import DB_PATH, get_connection
    conn = get_connection()
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    print(f"  DB Path: {DB_PATH}")
    print(f"  Tables: {[t[0] for t in tables]}")
    trades = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    pending = conn.execute("SELECT COUNT(*) FROM trades WHERE status='pending'").fetchone()[0]
    resolved = conn.execute("SELECT COUNT(*) FROM trades WHERE status='resolved'").fetchone()[0]
    print(f"  Total trades: {trades} | Pending: {pending} | Resolved: {resolved}")
    conn.close()
    print("  RESULT: PASS")
except Exception as e:
    print(f"  RESULT: FAIL - {e}")

print()
print("All tests complete!")