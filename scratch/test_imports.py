#!/usr/bin/env python3
"""Quick import test for all new modules."""
import sys
sys.path.insert(0, ".")

results = {}

# Test each module import
modules = [
    "cli",
    "pipeline", 
    "config",
    "risk_manager",
    "arbitrage",
    "ml_predictor",
    "sentiment",
    "onchain_scanner",
    "ai_insights",
    "market_maker",
    "sniper",
    "live_scanner",
    "correlation",
    "multitimeframe",
    "whale",
    "edge",
    "classifier",
    "matcher",
    "markets",
    "scraper",
    "scorer",
    "executor",
    "logger",
    "news_stream",
    "market_watcher",
    "db_tables",
    "bankroll",
    "cashout",
    "cleanup_losers",
    "cleanup_trades",
    "resolve_trades",
    "resolver",
    "price_feeds",
    "orderbook",
    "optimizer",
    "leaderboard",
    "apify_search",
    "tg_scraper",
    "tg_whales",
    "tg_auth",
    "start",
]

for mod in modules:
    try:
        __import__(mod)
        results[mod] = "OK"
    except Exception as e:
        results[mod] = f"FAIL: {type(e).__name__}: {e}"

print("\n=== IMPORT TEST RESULTS ===\n")
ok_count = 0
fail_count = 0
for mod, status in results.items():
    if status == "OK":
        print(f"  ✓ {mod}")
        ok_count += 1
    else:
        print(f"  ✗ {mod}: {status}")
        fail_count += 1

print(f"\n  Total: {ok_count} OK, {fail_count} FAIL out of {len(results)}")