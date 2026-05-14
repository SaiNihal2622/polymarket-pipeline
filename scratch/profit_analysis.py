#!/usr/bin/env python3
"""Full profit analysis from live_trades.json snapshot."""
import json
from collections import Counter

trades = json.load(open("scratch/live_trades.json"))
print(f"Total trades in snapshot: {len(trades)}")

wins = [t for t in trades if t.get("result") == "win"]
losses = [t for t in trades if t.get("result") == "loss"]
pending = [t for t in trades if t.get("result") is None]

resolved = len(wins) + len(losses)
print(f"Resolved: {len(wins)}W / {len(losses)}L | Pending: {len(pending)}")
print(f"Accuracy: {len(wins) / max(resolved, 1) * 100:.1f}%")

total_pnl = sum(t.get("pnl", 0) or 0 for t in trades if t.get("result") in ("win", "loss"))
total_wagered = sum(t.get("amount_usd", 0) for t in trades if t.get("result") in ("win", "loss"))
win_pnl = sum(t.get("pnl", 0) or 0 for t in wins)
loss_pnl = sum(t.get("pnl", 0) or 0 for t in losses)

print(f"\n=== PROFIT SUMMARY ===")
print(f"Total Wagered:  ${total_wagered:.2f}")
print(f"Total PnL:      ${total_pnl:+.2f}")
print(f"Win PnL:        ${win_pnl:+.2f}")
print(f"Loss PnL:       ${loss_pnl:+.2f}")
print(f"ROI:            {total_pnl / max(total_wagered, 1) * 100:+.1f}%")
print(f"Avg Win:        ${win_pnl / max(len(wins), 1):+.2f}")
print(f"Avg Loss:       ${loss_pnl / max(len(losses), 1):+.2f}")

# Date range
dates = sorted(t["created_at"] for t in trades)
print(f"\nDate Range: {dates[0]} to {dates[-1]}")

# Strategy breakdown
print(f"\n=== STRATEGY BREAKDOWN ===")
strat_data = {}
for t in trades:
    st = t.get("strategy", "unknown")
    if st not in strat_data:
        strat_data[st] = {"wins": 0, "losses": 0, "pending": 0, "pnl": 0.0, "wagered": 0.0}
    if t.get("result") == "win":
        strat_data[st]["wins"] += 1
        strat_data[st]["pnl"] += t.get("pnl", 0) or 0
    elif t.get("result") == "loss":
        strat_data[st]["losses"] += 1
        strat_data[st]["pnl"] += t.get("pnl", 0) or 0
    else:
        strat_data[st]["pending"] += 1
    if t.get("result") in ("win", "loss"):
        strat_data[st]["wagered"] += t.get("amount_usd", 0)

for st, d in sorted(strat_data.items()):
    r = d["wins"] + d["losses"]
    acc = d["wins"] / max(r, 1) * 100
    roi = d["pnl"] / max(d["wagered"], 1) * 100
    print(f"  {st:25s}: {d['wins']}W/{d['losses']}L ({acc:.0f}%) | Pending: {d['pending']} | PnL: ${d['pnl']:+.2f} | ROI: {roi:+.0f}%")

# WINS
print(f"\n=== ALL WINS ({len(wins)}) ===")
for t in sorted(wins, key=lambda x: x.get("pnl", 0) or 0, reverse=True):
    print(f"  #{t['id']:4d} ${t.get('pnl',0):+.2f} @{t['market_price']:.2f} | {t['strategy']:20s} | {t['market_question'][:55]}")

# LOSSES
print(f"\n=== ALL LOSSES ({len(losses)}) ===")
for t in sorted(losses, key=lambda x: x.get("pnl", 0) or 0):
    print(f"  #{t['id']:4d} ${t.get('pnl',0):+.2f} @{t['market_price']:.2f} | {t['strategy']:20s} | {t['market_question'][:55]}")

# PENDING
if pending:
    print(f"\n=== PENDING ({len(pending)}) ===")
    for t in pending:
        print(f"  #{t['id']:4d} ${t.get('amount_usd',0):.2f} @{t['market_price']:.2f} | {t['strategy']:20s} | {t['market_question'][:55]}")

# Daily breakdown
print(f"\n=== DAILY PnL ===")
day_data = {}
for t in trades:
    if t.get("result") not in ("win", "loss"):
        continue
    day = t["created_at"][:10]
    if day not in day_data:
        day_data[day] = {"wins": 0, "losses": 0, "pnl": 0.0}
    if t["result"] == "win":
        day_data[day]["wins"] += 1
    else:
        day_data[day]["losses"] += 1
    day_data[day]["pnl"] += t.get("pnl", 0) or 0

for day, d in sorted(day_data.items()):
    r = d["wins"] + d["losses"]
    acc = d["wins"] / max(r, 1) * 100
    print(f"  {day}: {d['wins']}W/{d['losses']}L ({acc:.0f}%) | PnL: ${d['pnl']:+.2f}")

# Price bracket
print(f"\n=== PRICE BRACKET ANALYSIS ===")
bracket_data = {}
for t in trades:
    if t.get("result") not in ("win", "loss"):
        continue
    p = t.get("market_price", 0)
    if p < 0.15:
        br = "0.10-0.14"
    elif p < 0.20:
        br = "0.15-0.19"
    elif p < 0.30:
        br = "0.20-0.29"
    elif p < 0.40:
        br = "0.30-0.39"
    else:
        br = "0.40+"
    if br not in bracket_data:
        bracket_data[br] = {"wins": 0, "losses": 0, "pnl": 0.0}
    if t["result"] == "win":
        bracket_data[br]["wins"] += 1
    else:
        bracket_data[br]["losses"] += 1
    bracket_data[br]["pnl"] += t.get("pnl", 0) or 0

for br, d in sorted(bracket_data.items()):
    r = d["wins"] + d["losses"]
    acc = d["wins"] / max(r, 1) * 100
    print(f"  YES {br}: {d['wins']}W/{d['losses']}L ({acc:.0f}%) | PnL: ${d['pnl']:+.2f}")

# Market categories
print(f"\n=== MARKET CATEGORY ANALYSIS ===")
cat_data = {}
for t in trades:
    if t.get("result") not in ("win", "loss"):
        continue
    q = t["market_question"].lower()
    if any(x in q for x in ["fight", "ko", "tko", "distance", "round"]):
        cat = "Combat Sports (UFC/Boxing)"
    elif any(x in q for x in ["goalscorer", "goal", "assist", "clean sheet"]):
        cat = "Soccer Player Props"
    elif any(x in q for x in ["trump", "biden", "president", "political", "congress"]):
        cat = "Politics"
    elif any(x in q for x in ["ethereum", "bitcoin", "btc", "eth", "price of"]):
        cat = "Crypto"
    elif any(x in q for x in ["idol", "oscar", "grammy", "award"]):
        cat = "Entertainment"
    elif any(x in q for x in ["nyt", "headline", "post", "photograph"]):
        cat = "Media/Events"
    else:
        cat = "Other"
    if cat not in cat_data:
        cat_data[cat] = {"wins": 0, "losses": 0, "pnl": 0.0}
    if t["result"] == "win":
        cat_data[cat]["wins"] += 1
    else:
        cat_data[cat]["losses"] += 1
    cat_data[cat]["pnl"] += t.get("pnl", 0) or 0

for cat, d in sorted(cat_data.items(), key=lambda x: x[1]["pnl"], reverse=True):
    r = d["wins"] + d["losses"]
    acc = d["wins"] / max(r, 1) * 100
    print(f"  {cat:30s}: {d['wins']}W/{d['losses']}L ({acc:.0f}%) | PnL: ${d['pnl']:+.2f}")