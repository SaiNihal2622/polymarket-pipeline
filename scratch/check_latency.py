import sys
import os
sys.path.append(os.getcwd())
import logger
import json

stats = logger.get_latency_stats()
news_events = logger.get_recent_news_events(limit=5)
trades = logger.get_recent_trades(limit=5)

print("Latency Stats:")
print(json.dumps(stats, indent=2))

print("\nRecent News Events:")
for event in news_events:
    print(f"  {event['received_at']} | {event['latency_ms']}ms | {event['headline'][:60]}")

print("\nRecent Trades:")
for trade in trades:
    print(f"  {trade['created_at']} | Class: {trade['classification_latency_ms']}ms | Total: {trade['total_latency_ms']}ms | {trade['market_question'][:60]}")
