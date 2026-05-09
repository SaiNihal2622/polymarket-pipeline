#!/usr/bin/env python3
"""Full audit of all trades and outcomes."""
import sqlite3, os
DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "trades.db")
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

print("=" * 80)
print("FULL TRADE DATABASE AUDIT")
print("=" * 80)

# 1. All trades
print("\n--- ALL TRADES ---")
for r in conn.execute("""
    SELECT id, market_id, substr(market_question,1,70) as q, 
           claude_score, market_price, edge, side, amount_usd, 
           status, strategy, created_at
    FROM trades ORDER BY id
""").fetchall():
    print(f"  #{r['id']:3d} | {r['side']:3s} | score={r['claude_score']:.2f} price={r['market_price']:.3f} edge={r['edge']:.3f} | ${r['amount_usd']:.0f} | {r['status']:8s} | {r['strategy'] or 'N/A':10s} | {r['q']}")
    print(f"        market_id={r['market_id'][:40]}... created={r['created_at']}")

# 2. All outcomes
print("\n--- ALL OUTCOMES ---")
for r in conn.execute("""
    SELECT o.id, o.trade_id, o.result, o.pnl, o.resolved_at,
           t.market_question, t.side, t.market_price, t.edge
    FROM outcomes o JOIN trades t ON o.trade_id=t.id ORDER BY o.id
""").fetchall():
    print(f"  Outcome #{r['id']}: trade #{r['trade_id']} | {r['side']} | result={r['result']} | PnL=${r['pnl']:+.2f} | price={r['market_price']:.3f} edge={r['edge']:.3f}")
    print(f"    Q: {r['market_question'][:70]}")
    print(f"    Resolved: {r['resolved_at']}")

# 3. Stats
print("\n--- STATISTICS ---")
row = conn.execute("""
    SELECT 
        count(*) as total,
        sum(case when result='win' then 1 else 0 end) as wins,
        sum(case when result='loss' then 1 else 0 end) as losses,
        sum(case when result='void' then 1 else 0 end) as voids,
        sum(case when result='timeout' then 1 else 0 end) as timeouts,
        round(sum(pnl),2) as total_pnl,
        round(avg(pnl),2) as avg_pnl,
        round(avg(case when result='win' then pnl end),2) as avg_win,
        round(avg(case when result='loss' then pnl end),2) as avg_loss
    FROM outcomes
""").fetchone()
print(f"  Total outcomes: {row['total']}")
print(f"  Wins: {row['wins']}, Losses: {row['losses']}, Voids: {row['voids']}, Timeouts: {row['timeouts']}")
print(f"  Total PnL: ${row['total_pnl']}")
print(f"  Avg PnL per trade: ${row['avg_pnl']}")
print(f"  Avg Win: ${row['avg_win']}, Avg Loss: ${row['avg_loss']}")
if row['wins'] and row['losses']:
    acc = row['wins'] / (row['wins'] + row['losses']) * 100
    print(f"  Accuracy: {acc:.1f}%")

# 4. Why trades lost
print("\n--- LOSS ANALYSIS ---")
for r in conn.execute("""
    SELECT t.market_question, t.side, t.market_price, t.edge, t.claude_score,
           o.result, o.pnl, t.strategy
    FROM trades t JOIN outcomes o ON t.id=o.trade_id
    WHERE o.result='loss'
""").fetchall():
    print(f"  LOST: {r['side']} @ {r['market_price']:.3f} (score={r['claude_score']:.2f}, edge={r['edge']:.3f})")
    print(f"    Q: {r['market_question'][:80]}")
    print(f"    Strategy: {r['strategy']}")
    # If YES at high price, or NO at low price = bad bet
    if r['side'] == 'YES' and r['market_price'] > 0.7:
        print(f"    ⚠️ Bought YES at {r['market_price']:.1%} - paid too much, needed market to go higher")
    elif r['side'] == 'NO' and r['market_price'] < 0.3:
        print(f"    ⚠️ Bought NO at {r['market_price']:.1%} - very cheap YES means event unlikely, NO payout tiny")
    print()

# 5. Win analysis  
print("\n--- WIN ANALYSIS ---")
for r in conn.execute("""
    SELECT t.market_question, t.side, t.market_price, t.edge, t.claude_score,
           o.result, o.pnl, t.strategy
    FROM trades t JOIN outcomes o ON t.id=o.trade_id
    WHERE o.result='win'
""").fetchall():
    print(f"  WON: {r['side']} @ {r['market_price']:.3f} (score={r['claude_score']:.2f}, edge={r['edge']:.3f})")
    print(f"    Q: {r['market_question'][:80]}")
    print(f"    Strategy: {r['strategy']}, PnL: ${r['pnl']:+.2f}")
    print()

# 6. Pipeline runs
print("\n--- PIPELINE RUNS ---")
for r in conn.execute("SELECT * FROM pipeline_runs ORDER BY id DESC LIMIT 5").fetchall():
    print(f"  Run #{r['id']}: {dict(r)}")

conn.close()