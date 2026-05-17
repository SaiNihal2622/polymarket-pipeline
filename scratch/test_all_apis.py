#!/usr/bin/env python3
"""Test all APIs used by the pipeline."""
import httpx
import json
import os
import sys
from pathlib import Path

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

results = {}

# === GAMMA API ===
print("=== GAMMA API ===")
try:
    r = httpx.get("https://gamma-api.polymarket.com/markets",
        params={"limit": 3, "active": "true", "closed": "false"},
        timeout=15, verify=False)
    print(f"Status: {r.status_code}")
    data = r.json()
    items = data if isinstance(data, list) else data.get("data", [])
    print(f"Markets returned: {len(items)}")
    if items:
        q = items[0].get("question", "N/A")
        print(f"Sample market: {q[:80]}")
        print(f"Sample price: {items[0].get('outcomePrices', 'N/A')}")
    results["gamma"] = r.status_code == 200 and len(items) > 0
except Exception as e:
    print(f"ERROR: {e}")
    results["gamma"] = False

# === CLOB API ===
print("\n=== CLOB API ===")
try:
    r = httpx.get("https://clob.polymarket.com/sampling-markets",
        params={"next_cursor": "LTE="}, timeout=15, verify=False)
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        print(f"Keys: {list(data.keys())[:5]}")
        results["clob"] = True
    else:
        print(f"Error: {r.text[:200]}")
        results["clob"] = False
except Exception as e:
    print(f"ERROR: {e}")
    results["clob"] = False

# === Groq API ===
print("\n=== GROQ API ===")
groq_key = os.getenv("GROQ_API_KEY", "")
print(f"GROQ_API_KEY set: {bool(groq_key)}")
if groq_key:
    try:
        r = httpx.post("https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
            json={"model": "llama-3.3-70b-versatile",
                  "messages": [{"role": "user", "content": "Say hello in 3 words"}],
                  "max_tokens": 20},
            timeout=15)
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            content = r.json()["choices"][0]["message"]["content"]
            print(f"Response: {content[:60]}")
            results["groq"] = True
        else:
            print(f"Error: {r.text[:200]}")
            results["groq"] = False
    except Exception as e:
        print(f"ERROR: {e}")
        results["groq"] = False
else:
    print("NOT SET")
    results["groq"] = False

# === Gemini ===
print("\n=== GEMINI API ===")
gemini_key = os.getenv("GEMINI_API_KEY", "")
print(f"GEMINI_API_KEY set: {bool(gemini_key)}")
if gemini_key:
    try:
        r = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={gemini_key}",
            json={"contents": [{"parts": [{"text": "Say hello"}]}]},
            timeout=15)
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            candidates = r.json().get("candidates", [])
            if candidates:
                text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                print(f"Response: {text[:60]}")
            results["gemini"] = True
        else:
            print(f"Error: {r.text[:200]}")
            results["gemini"] = False
    except Exception as e:
        print(f"ERROR: {e}")
        results["gemini"] = False
else:
    print("NOT SET")
    results["gemini"] = False

# === MiMo API ===
print("\n=== MIMO API ===")
mimo_key = os.getenv("MIMO_API_KEY", "")
mimo_base = os.getenv("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1")
print(f"MIMO_API_KEY set: {bool(mimo_key)}")
if mimo_key:
    try:
        r = httpx.post(f"{mimo_base}/chat/completions",
            headers={"Authorization": f"Bearer {mimo_key}", "Content-Type": "application/json"},
            json={"model": "mimo-v2.5-pro",
                  "messages": [{"role": "user", "content": "Say hello"}],
                  "max_tokens": 20},
            timeout=15)
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            content = r.json()["choices"][0]["message"]["content"]
            print(f"Response: {content[:60]}")
            results["mimo"] = True
        else:
            print(f"Error: {r.text[:200]}")
            results["mimo"] = False
    except Exception as e:
        print(f"ERROR: {e}")
        results["mimo"] = False
else:
    print("NOT SET")
    results["mimo"] = False

# === NewsAPI ===
print("\n=== NEWSAPI ===")
news_key = os.getenv("NEWSAPI_KEY", "")
print(f"NEWSAPI_KEY set: {bool(news_key)}")
if news_key:
    try:
        r = httpx.get("https://newsapi.org/v2/top-headlines",
            params={"country": "us", "pageSize": 3},
            headers={"X-Api-Key": news_key},
            timeout=15)
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            articles = r.json().get("articles", [])
            print(f"Articles: {len(articles)}")
            results["newsapi"] = True
        else:
            print(f"Error: {r.text[:200]}")
            results["newsapi"] = False
    except Exception as e:
        print(f"ERROR: {e}")
        results["newsapi"] = False
else:
    print("NOT SET")
    results["newsapi"] = False

# === RSS Feeds ===
print("\n=== RSS FEEDS ===")
try:
    import feedparser
    feed = feedparser.parse("https://feeds.bbci.co.uk/news/world/rss.xml")
    print(f"BBC RSS entries: {len(feed.entries)}")
    if feed.entries:
        print(f"Sample: {feed.entries[0].title[:60]}")
    results["rss"] = len(feed.entries) > 0
except Exception as e:
    print(f"ERROR: {e}")
    results["rss"] = False

# === Telegram Bot ===
print("\n=== TELEGRAM ===")
tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
print(f"TELEGRAM_BOT_TOKEN set: {bool(tg_token)}")
results["telegram"] = bool(tg_token)

# === Summary ===
print("\n" + "=" * 50)
print("API STATUS SUMMARY")
print("=" * 50)
for api, ok in results.items():
    status = "OK" if ok else "FAILED"
    print(f"  {api:15s} : {status}")

all_ok = all(results.values())
print(f"\nAll APIs working: {all_ok}")
if not all_ok:
    failed = [k for k, v in results.items() if not v]
    print(f"Failed: {', '.join(failed)}")