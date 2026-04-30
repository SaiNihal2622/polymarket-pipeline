import os
import httpx
import logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("test_apify")

APIFY_TOKEN = os.getenv("APIFY_TOKEN", "")

def test_apify():
    if not APIFY_TOKEN:
        print("❌ APIFY_TOKEN not set in environment.")
        return

    print(f"Testing Apify with token: {APIFY_TOKEN[:5]}...")
    try:
        resp = httpx.post(
            "https://api.apify.com/v2/acts/apify~google-search-scraper/run-sync-get-dataset-items",
            params={"token": APIFY_TOKEN, "timeout": 15},
            json={
                "queries": "Polymarket crypto news 2026",
                "maxPagesPerQuery": 1,
                "resultsPerPage": 1,
            },
            timeout=20,
        )
        print(f"Status Code: {resp.status_code}")
        if resp.status_code == 402:
            print("❌ 402 Payment Required: Your Apify account has $5 but this actor might require a specific plan or higher balance.")
        elif resp.status_code == 200:
            print("✅ Success! Apify is working.")
        else:
            print(f"Response: {resp.text}")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_apify()
