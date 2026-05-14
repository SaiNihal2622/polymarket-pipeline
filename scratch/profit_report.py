#!/usr/bin/env python3
"""Comprehensive profit analysis of the Polymarket Pipeline."""
import json
import sqlite3
from collections import defaultdict

print("=" * 70)
print("  POLYMARKET PIPELINE — PROFIT AUDIT REPORT")
print("=" * 70)

# ── 1. LIVE TRADES DATA (from live_trades.json) ──────────────────────────
print("\n1. LIVE TRADES DATA (live_trades.json)")
print("-" * 70)

with open("scratch/live_trades.json") as f:
    raw = json.load(f)

data = raw if isinstance(raw, list) else raw.get("data", raw)
trades = [row for row in data if isinstance(row, dict)]

total = len(trades)
wins = [t for t in trades if t.get("result") == "win"]
losses = [t for t in trades if t.get("result") == "loss"]
pending = [t for t in trades if t.get("result") == "pending"]
voided = [t for t in trades if t.get("result") == "void"]
other = [t for t in trades if t.get("result") not in ("win", "loss", "pending", "void")]

total_pnl = sum(float(t.get("pnl") or 0) for t in trades)
total_wagered = sum(float(t.get("amount_usd") or 0) for t in trades)

resolved = len(wins) + len(losses)
acc = (len(wins) / resolved * 100) if resolved else 0
roi = (total_pnl / total_wagered * 100) if total_wagered else 0

print(f"  Total Trades:     {total}")
print(f"  Wins:             {len(wins)}")
print(f"  Losses:           {len(losses)}")
print(f"  Pending:          {len(pending)}")
print(f"  Voided:           {len(voided)}")
print(f"  Other/Unknown:    {len(other)}")
print(f"  Resolved:         {resolved}")
print(f"  Win Rate:         {acc:.1f}%")
print(f"  Total Wagered:    ${total_wagered:.2f}")
print(f"  Net P&L:          ${total_pnl:+.2f}")
print(f"  ROI:              {roi:+.1f}%")

# Trade details
print(f"\n  {'ID':<4} {'Question':<40} {'Side':<4} {'Price':>6} {'Amount':>7} {'P&L':>8} {'Status':<7}")
print(f"  {'─'*4} {'─'*40} {'─'*4} {'─'*6} {'─'*7} {'─'*8} {'─'*7}")
for t in sorted(trades, key=lambda x: x.get("created_at", "")):
    tid = str(t.get("id", "?"))[-4:]
    q = str(t.get("market_question", "?"))[:38]
    side = t.get("side", "?")
    price = float(t.get("market_price") or 0)
    amt = float(t.get("amount_usd") or 0)
    pnl = float(t.get("pnl") or 0)
    res = t.get("result", "?")
    marker = "✅" if res == "win" else "❌" if res == "loss" else "⏳" if res == "pending" else "⚪"
    pnl_str = f"${pnl:+.2f}" if res in ("win", "loss") else f"${amt:.2f}"
    print(f"  {tid:<4} {q:<40} {side:<4} {price:>6.3f} ${amt:>6.2f} {pnl_str:>8} {marker} {res}")

# ── 2. P&L BY STRATEGY ──────────────────────────────────────────────────
print(f"\n2. P&L BY STRATEGY")
print("-" * 70)
strats = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0, "wagered": 0, "count": 0})
for t in trades:
    s = strats[t.get("strategy", "unknown")]
    s["count"] += 1
    s["wagered"] += float(t.get("amount_usd") or 0)
    if t.get("result") == "win":
        s["wins"] += 1
        s["pnl"] += float(t.get("pnl") or 0)
    elif t.get("result") == "loss":
        s["losses"] += 1
        s["pnl"] += float(t.get("pnl") or 0)

for name, s in sorted(strats.items(), key=lambda x: x[1]["pnl"], reverse=True):
    res = s["wins"] + s["losses"]
    acc = (s["wins"] / res * 100) if res else 0
    roi = (s["pnl"] / s["wagered"] * 100) if s["wagered"] else 0
    print(f"  {name:<22} | {s['count']:>2} trades | {s['wins']}W/{s['losses']}L | "
          f"Acc: {acc:>5.1f}% | P&L: ${s['pnl']:>+7.2f} | Wagered: ${s['wagered']:.2f} | ROI: {roi:>+6.1f}%")

# ── 3. P&L BY SIDE ──────────────────────────────────────────────────────
print(f"\n3. P&L BY SIDE (YES vs NO)")
print("-" * 70)
sides = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0, "wagered": 0})
for t in trades:
    s = sides[t.get("side", "?")]
    s["wagered"] += float(t.get("amount_usd") or 0)
    if t.get("result") == "win":
        s["wins"] += 1
        s["pnl"] += float(t.get("pnl") or 0)
    elif t.get("result") == "loss":
        s["losses"] += 1
        s["pnl"] += float(t.get("pnl") or 0)

for name, s in sorted(sides.items()):
    res = s["wins"] + s["losses"]
    acc = (s["wins"] / res * 100) if res else 0
    roi = (s["pnl"] / s["wagered"] * 100) if s["wagered"] else 0
    print(f"  {name:<5} | {s['wins']}W/{s['losses']}L | Acc: {acc:>5.1f}% | "
          f"P&L: ${s['pnl']:>+7.2f} | Wagered: ${s['wagered']:.2f} | ROI: {roi:>+6.1f}%")

# ── 4. P&L BY MARKET CATEGORY ──────────────────────────────────────────
print(f"\n4. P&L BY MARKET CATEGORY")
print("-" * 70)
def categorize(q):
    ql = q.lower()
    if any(w in ql for w in ["ufc", "fight", "ko", "tko", "round", "distance"]):
        return "UFC/MMA"
    elif any(w in ql for w in ["ipl", "cricket", "run", "wicket", "overs"]):
        return "Cricket/IPL"
    elif any(w in ql for w in ["bitcoin", "btc", "ethereum", "eth", "price", "solana", "sol", "crypto", "xrp"]):
        return "Crypto"
    elif any(w in ql for w in ["nba", "basketball", "lakers", "celtics"]):
        return "NBA"
    elif any(w in ql for w in ["trump", "biden", "election", "president", "tariff"]):
        return "Politics"
    elif any(w in ql for w in ["fed", "rate", "gdp", "inflation", "recession"]):
        return "Economics"
    else:
        return "Other"

cats = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0, "wagered": 0, "count": 0})
for t in trades:
    cat = categorize(t.get("market_question", ""))
    s = cats[cat]
    s["count"] += 1
    s["wagered"] += float(t.get("amount_usd") or 0)
    if t.get("result") == "win":
        s["wins"] += 1
        s["pnl"] += float(t.get("pnl") or 0)
    elif t.get("result") == "loss":
        s["losses"] += 1
        s["pnl"] += float(t.get("pnl") or 0)

for name, s in sorted(cats.items(), key=lambda x: x[1]["pnl"], reverse=True):
    res = s["wins"] + s["losses"]
    acc = (s["wins"] / res * 100) if res else 0
    roi = (s["pnl"] / s["wagered"] * 100) if s["wagered"] else 0
    print(f"  {name:<12} | {s['count']:>2} trades | {s['wins']}W/{s['losses']}L | "
          f"Acc: {acc:>5.1f}% | P&L: ${s['pnl']:>+7.2f} | Wagered: ${s['wagered']:.2f} | ROI: {roi:>+6.1f}%")

# ── 5. BEST/WORST TRADES ────────────────────────────────────────────────
print(f"\n5. BEST & WORST TRADES")
print("-" * 70)
resolved_trades = [t for t in trades if t.get("result") in ("win", "loss")]
if resolved_trades:
    best = max(resolved_trades, key=lambda t: float(t.get("pnl") or 0))
    worst = min(resolved_trades, key=lambda t: float(t.get("pnl") or 0))
    print(f"  Best:  {best.get('market_question', '?')[:55]}")
    print(f"         P&L: ${float(best.get('pnl', 0)):+.2f} | Strategy: {best.get('strategy')}")
    print(f"         Edge: {best.get('edge')} | Claude Score: {best.get('claude_score')}")
    print(f"  Worst: {worst.get('market_question', '?')[:55]}")
    print(f"         P&L: ${float(worst.get('pnl', 0)):+.2f} | Strategy: {worst.get('strategy')}")
    print(f"         Edge: {worst.get('edge')} | Claude Score: {worst.get('claude_score')}")

# ── 6. TRADE TIMING ────────────────────────────────────────────────────
print(f"\n6. TRADE TIMING")
print("-" * 70)
durations = [t.get("resolution_duration", "?") for t in resolved_trades]
print(f"  First trade:  {min(t.get('created_at','') for t in trades)}")
print(f"  Last trade:   {max(t.get('created_at','') for t in trades)}")
print(f"  Resolution times: {', '.join(durations)}")

# ── 7. SIGNAL ANALYSIS ──────────────────────────────────────────────────
print(f"\n7. SIGNAL ANALYSIS")
print("-" * 70)
for t in trades:
    sp = t.get("signals_parsed", {})
    rrf = sp.get("rrf", "N/A") if sp else "N/A"
    ai = sp.get("ai", "N/A") if sp else "N/A"
    res = t.get("result", "?")
    q = str(t.get("market_question", "?"))[:40]
    marker = "✅" if res == "win" else "❌" if res == "loss" else "⏳"
    print(f"  {marker} {q:<40} RRF: {rrf:<18} AI: {ai}")

# ── 8. HISTORICAL DATABASE STATS ────────────────────────────────────────
print(f"\n8. HISTORICAL DATABASE STATS (sqlite_sequence)")
print("-" * 70)
conn = sqlite3.connect("trades.db")
cur = conn.cursor()
try:
    rows = cur.execute("SELECT name, seq FROM sqlite_sequence").fetchall()
    for name, seq in rows:
        print(f"  {name:<20} {seq:>6} records existed historically")
except:
    print("  No sqlite_sequence data")
conn.close()

# ── 9. DEPLOYMENT CONTEXT ──────────────────────────────────────────────
print(f"\n9. DEPLOYMENT CONTEXT (from CONTEXT_HANDOFF.md)")
print("-" * 70)
print(f"  Old Railway project (3f90): 62 trades accumulated")
print(f"  New project: Fresh deployment with /data volume")
print(f"  Railway volume: /data/demo_runner.db (persistent)")
print(f"  Current status: Deployment OFFLINE (404)")
print(f"  Bankroll: $30 USD configured")
print(f"  Bet sizing: $1.19 - $1.65 per trade (actual)")
print(f"  Scan interval: 5 min, Resolve interval: 5 min")
print(f"  Strategy: S8_rrf_highconv (all trades)")

# ── 10. FINAL SUMMARY ───────────────────────────────────────────────────
print(f"\n{'=' * 70}")
print(f"  FINAL PROFIT SUMMARY")
print(f"{'=' * 70}")
print(f"")
print(f"  📊 LIVE TRADES (12 trades from live_trades.json, May 10 2026):")
print(f"     Total Trades:     {total}")
print(f"     Win Rate:         {acc:.1f}% ({len(wins)}W / {len(losses)}L)")
print(f"     Total Wagered:    ${total_wagered:.2f}")
print(f"     Net P&L:          ${total_pnl:+.2f}")
print(f"     ROI:              {roi:+.1f}%")
print(f"")
print(f"  📈 Historical Context:")
print(f"     542 trades existed across the pipeline's lifetime")
print(f"     62 trades on the old Railway project (3f90)")
print(f"     Full historical P&L data is on the Railway server (now offline)")
print(f"")
print(f"  ⚠️  CURRENT STATUS: Railway deployment is OFFLINE")
print(f"     The live profit data can only be accessed from the Railway")
print(f"     deployment's persistent volume at /data/demo_runner.db")
print(f"")
print(f"  💡 Based on available data ({total} trades):")
print(f"     The pipeline LOST ${abs(total_pnl):.2f} on ${total_wagered:.2f} wagered")
print(f"     Win rate of {acc:.1f}% ({len(wins)}W/{len(losses)}L) is very poor")
print(f"     Each loss costs ~$1.19-$1.65, the single win earned $2.98")
print(f"     Strategy S8_rrf_highconv needs significant recalibration")
print(f"")

# Best/worst case for pending
if pending:
    pending_risk = sum(float(t.get("amount_usd") or 0) for t in pending)
    best_pending = total_pnl + pending_risk * 2
    worst_pending = total_pnl - pending_risk
    print(f"  📊 Pending Trade Scenarios:")
    print(f"     If all pending WINS:  ${best_pending:+.2f} total P&L")
    print(f"     If all pending LOSE:  ${worst_pending:+.2f} total P&L")
    print(f"")

print("=" * 70)