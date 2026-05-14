import json
import os

# Load live_trades.json
with open("scratch/live_trades.json") as f:
    trades = json.load(f)

print(f"{'='*70}")
print(f"POLYMARKET PIPELINE — COMPLETE PROFIT ANALYSIS")
print(f"{'='*70}")

# Basic stats
total = len(trades)
wins = [t for t in trades if t.get("result") == "win"]
losses = [t for t in trades if t.get("result") == "loss"]
pending = [t for t in trades if t.get("result") is None]

total_invested = sum(t.get("amount_usd", 0) for t in trades)
total_wagered_resolved = sum(t.get("amount_usd", 0) for t in trades if t.get("result") in ("win", "loss"))
total_pnl = sum(t.get("pnl", 0) or 0 for t in trades if t.get("pnl") is not None)
total_wins_pnl = sum(t.get("pnl", 0) or 0 for t in wins)
total_losses_pnl = sum(t.get("pnl", 0) or 0 for t in losses)

win_count = len(wins)
loss_count = len(losses)
pending_count = len(pending)
resolved = win_count + loss_count

accuracy = (win_count / resolved * 100) if resolved > 0 else 0

print(f"\n{'─'*70}")
print(f"OVERALL SUMMARY")
print(f"{'─'*70}")
print(f"Total trades placed:     {total}")
print(f"  └─ Resolved:           {resolved} ({win_count}W / {loss_count}L)")
print(f"  └─ Pending:            {pending_count}")
print(f"  └─ Unresolved:         {len([t for t in trades if t.get('result') == 'void'])}")
print(f"")
print(f"Accuracy:                {accuracy:.1f}% ({win_count}/{resolved})")
print(f"")
print(f"Total money invested:    ${total_invested:.2f}")
print(f"Total P&L (all trades):  ${total_pnl:+.2f}")
print(f"  └─ Wins profit:        ${total_wins_pnl:+.2f}")
print(f"  └─ Losses cost:        ${total_losses_pnl:+.2f}")
print(f"")
print(f"Average bet size:        ${total_invested/total:.2f}" if total else "")
print(f"Average P&L per trade:   ${total_pnl/resolved:+.2f}" if resolved else "")
print(f"ROI on resolved trades:  {(total_pnl/total_wagered_resolved*100):+.1f}%" if total_wagered_resolved else "")

# Date range
dates = [t.get("created_at", "") for t in trades if t.get("created_at")]
if dates:
    print(f"\nDate range:              {min(dates)[:10]} to {max(dates)[:10]}")

# Strategy breakdown
print(f"\n{'─'*70}")
print(f"BY STRATEGY")
print(f"{'─'*70}")
strategies = {}
for t in trades:
    s = t.get("strategy", "unknown")
    if s not in strategies:
        strategies[s] = {"total": 0, "wins": 0, "losses": 0, "pending": 0, "pnl": 0, "invested": 0}
    strategies[s]["total"] += 1
    strategies[s]["invested"] += t.get("amount_usd", 0)
    if t.get("result") == "win":
        strategies[s]["wins"] += 1
        strategies[s]["pnl"] += t.get("pnl", 0) or 0
    elif t.get("result") == "loss":
        strategies[s]["losses"] += 1
        strategies[s]["pnl"] += t.get("pnl", 0) or 0
    elif t.get("result") is None:
        strategies[s]["pending"] += 1

print(f"{'Strategy':<25} {'Trades':>6} {'W':>4} {'L':>4} {'P':>4} {'Acc%':>6} {'P&L':>10} {'ROI':>8}")
print(f"{'─'*70}")
for s, d in sorted(strategies.items(), key=lambda x: x[1]["pnl"], reverse=True):
    r = d["wins"] + d["losses"]
    acc = (d["wins"] / r * 100) if r > 0 else 0
    roi = (d["pnl"] / d["invested"] * 100) if d["invested"] > 0 else 0
    print(f"{s:<25} {d['total']:>6} {d['wins']:>4} {d['losses']:>4} {d['pending']:>4} {acc:>5.1f}% ${d['pnl']:>+8.2f} {roi:>+7.1f}%")

# Win details
print(f"\n{'─'*70}")
print(f"WINNING TRADES")
print(f"{'─'*70}")
for t in sorted(wins, key=lambda x: x.get("pnl", 0) or 0, reverse=True):
    q = t.get("market_question", "")[:55]
    pnl = t.get("pnl", 0) or 0
    amt = t.get("amount_usd", 0)
    price = t.get("market_price", 0)
    roi = (pnl / amt * 100) if amt > 0 else 0
    print(f"  ${pnl:+.2f} (${amt:.2f} @{price:.3f}, ROI:{roi:+.0f}%) | {t.get('strategy','?'):<20} | {q}")

# Loss details
print(f"\n{'─'*70}")
print(f"LOSING TRADES (top 15 by loss)")
print(f"{'─'*70}")
for t in sorted(losses, key=lambda x: x.get("pnl", 0) or 0)[:15]:
    q = t.get("market_question", "")[:55]
    pnl = t.get("pnl", 0) or 0
    amt = t.get("amount_usd", 0)
    price = t.get("market_price", 0)
    print(f"  ${pnl:+.2f} (${amt:.2f} @{price:.3f}) | {t.get('strategy','?'):<20} | {q}")

# Pending trades
if pending:
    print(f"\n{'─'*70}")
    print(f"PENDING TRADES ({pending_count})")
    print(f"{'─'*70}")
    for t in pending:
        q = t.get("market_question", "")[:60]
        amt = t.get("amount_usd", 0)
        created = t.get("created_at", "")[:16]
        print(f"  ${amt:.2f} | {created} | {t.get('strategy','?'):<20} | {q}")

# Streak analysis
print(f"\n{'─'*70}")
print(f"STREAK ANALYSIS")
print(f"{'─'*70}")
resolved_trades = [t for t in trades if t.get("result") in ("win", "loss")]
resolved_trades.sort(key=lambda x: x.get("created_at", ""))

max_win_streak = 0
max_loss_streak = 0
current_win_streak = 0
current_loss_streak = 0

for t in resolved_trades:
    if t.get("result") == "win":
        current_win_streak += 1
        current_loss_streak = 0
        max_win_streak = max(max_win_streak, current_win_streak)
    else:
        current_loss_streak += 1
        current_win_streak = 0
        max_loss_streak = max(max_loss_streak, current_loss_streak)

print(f"Max win streak:          {max_win_streak}")
print(f"Max loss streak:         {max_loss_streak}")
print(f"Current streak:          {'W'*current_win_streak if current_win_streak else 'L'*current_loss_streak}")

# Edge analysis
print(f"\n{'─'*70}")
print(f"EDGE ANALYSIS")
print(f"{'─'*70}")
edges = [t.get("edge", 0) for t in trades if t.get("edge")]
if edges:
    print(f"Average edge:            {sum(edges)/len(edges):.3f}")
    print(f"Max edge:                {max(edges):.3f}")
    print(f"Min edge:                {min(edges):.3f}")

# Bet size analysis
print(f"\n{'─'*70}")
print(f"BET SIZE ANALYSIS")
print(f"{'─'*70}")
amounts = [t.get("amount_usd", 0) for t in trades]
if amounts:
    print(f"Min bet:                 ${min(amounts):.2f}")
    print(f"Max bet:                 ${max(amounts):.2f}")
    print(f"Avg bet:                 ${sum(amounts)/len(amounts):.2f}")

# Market price distribution
print(f"\n{'─'*70}")
print(f"ENTRY PRICE DISTRIBUTION")
print(f"{'─'*70}")
prices = [t.get("market_price", 0) for t in trades if t.get("market_price")]
cheap = [p for p in prices if p <= 0.20]
mid = [p for p in prices if 0.20 < p <= 0.40]
high = [p for p in prices if p > 0.40]
print(f"Cheap (≤20¢):            {len(cheap)} trades ({len(cheap)/len(prices)*100:.0f}%)" if prices else "")
print(f"Mid (21-40¢):            {len(mid)} trades ({len(mid)/len(prices)*100:.0f}%)" if prices else "")
print(f"High (>40¢):             {len(high)} trades ({len(high)/len(prices)*100:.0f}%)" if prices else "")

# Profit by price range
for label, lo, hi in [("Cheap ≤20¢", 0, 0.20), ("Mid 21-40¢", 0.20, 0.40), ("High >40¢", 0.40, 1.01)]:
    rng = [t for t in trades if lo < (t.get("market_price") or 0) <= hi or (lo == 0 and (t.get("market_price") or 0) <= 0.20)]
    rng_resolved = [t for t in rng if t.get("result") in ("win", "loss")]
    rng_pnl = sum(t.get("pnl", 0) or 0 for t in rng_resolved)
    rng_w = len([t for t in rng_resolved if t.get("result") == "win"])
    rng_r = len(rng_resolved)
    rng_acc = (rng_w / rng_r * 100) if rng_r > 0 else 0
    print(f"  {label}: {rng_r} resolved, {rng_acc:.0f}% acc, ${rng_pnl:+.2f} P&L")

# Summary verdict
print(f"\n{'='*70}")
print(f"VERDICT")
print(f"{'='*70}")
if total_pnl > 0:
    print(f"✅ PROFITABLE: ${total_pnl:+.2f} total P&L on {resolved} resolved trades")
elif total_pnl < 0:
    print(f"❌ LOSING: ${total_pnl:+.2f} total P&L on {resolved} resolved trades")
else:
    print(f"⚠️ BREAK EVEN: $0.00 total P&L")

print(f"   Accuracy: {accuracy:.1f}% (need >53% to be profitable at these odds)")
print(f"   Bankroll: $30 starting capital")
print(f"   Status: DEMO (virtual money, no real trades)")