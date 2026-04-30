import httpx
import json

GAMMA_API = "https://gamma-api.polymarket.com"

def test_gamma():
    try:
        r = httpx.get(f"{GAMMA_API}/markets", params={"closed": "true", "limit": 10}, timeout=10)
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            print(f"Count: {len(data)}")
            if data:
                print(f"Sample Question: {data[0].get('question')}")
                print(f"Sample OutcomePrices: {data[0].get('outcomePrices')}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_gamma()
