import sqlite3
import os

print("=" * 70)
print("BOT.DB ANALYSIS")
print("=" * 70)

if not os.path.exists("bot.db"):
    print("bot.db not found!")
    exit(1)

print(f"File size: {os.path.getsize('bot.db') / 1024:.1f} KB")
conn = sqlite3.connect("bot.db")
conn.row_factory = sqlite3.Row

tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print(f"Tables: {tables}\n")

for t in tables:
    cnt = conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
    print(f"  {t}: {cnt} rows")

# Check trades table schema and data
if "trades" in tables:
    print("\n" + "=" * 70)
    print("TRADES TABLE")
    print("=" * 70)
    
    # Schema
    cols = conn.execute("PRAGMA table_info(trades)").fetchall()
    print("Columns:", [c[1] for c in cols])
    
    rows = conn.execute("SELECT * FROM trades ORDER BY rowid DESC LIMIT 50").fetchall()
    print(f"Last {len(rows)} trades:\n")
    
    for r in rows:
        d = dict(r)
        print(f"  ID={d.get('id','?')} | result={d.get('result','?')} | side={d.get('side','?')} | amount={d.get('amount_usd',0):.2f} | pnl={d.get('pnl',0):.2f} | price={d.get('market_price',0):.3f} | edge={d.get('edge',0):.3f} | strategy={d.get('strategy','?')}")
        q = str(d.get('market_question', d.get('question', '?')))[:70]
        print(f"    Q: {q} | created={d.get('created_at','?')}")
    
    # Summary stats
    print("\n" + "=" * 70)
    print("TRADE SUMMARY")
    print("=" * 70)
    
    total = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    wins = conn.execute("SELECT COUNT(*) FROM trades WHERE result='win'").fetchone()[0]
    losses = conn.execute("SELECT COUNT(*) FROM trades WHERE result='loss'").fetchone()[0]
    pending = conn.execute("SELECT COUNT(*) FROM trades WHERE result='pending' OR result IS NULL").fetchone()[0]
    void = conn.execute("SELECT COUNT(*) FROM trades WHERE result='void'").fetchone()[0]
    
    total_pnl = conn.execute("SELECT COALESCE(SUM(pnl),0) FROM trades").fetchone()[0]
    total_bet = conn.execute("SELECT COALESCE(SUM(amount_usd),0) FROM trades").fetchone()[0]
    win_pnl = conn.execute("SELECT COALESCE(SUM(pnl),0) FROM trades WHERE result='win'").fetchone()[0]
    loss_pnl = conn.execute("SELECT COALESCE(SUM(pnl),0) FROM trades WHERE result='loss'").fetchone()[0]
    
    print(f"  Total trades: {total}")
    print(f"  Wins: {wins}")
    print(f"  Losses: {losses}")
    print(f"  Pending: {pending}")
    print(f"  Void: {void}")
    print(f"  Win Rate: {wins/(wins+losses)*100:.1f}%" if (wins+losses) > 0 else "  Win Rate: N/A")
    print(f"  Total PnL: ${total_pnl:.2f}")
    print(f"  Win PnL: ${win_pnl:.2f}")
    print(f"  Loss PnL: ${loss_pnl:.2f}")
    print(f"  Total Bet: ${total_bet:.2f}")
    if total_bet > 0:
        print(f"  ROI: {total_pnl/total_bet*100:.2f}%")
    
    # By strategy
    print("\n  --- By Strategy ---")
    strat_rows = conn.execute("""
        SELECT strategy, COUNT(*) as cnt, SUM(pnl) as total_pnl, SUM(amount_usd) as total_bet,
               SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins,
               SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) as losses
        FROM trades GROUP BY strategy ORDER BY total_pnl DESC
    """).fetchall()
    for s in strat_rows:
        d = dict(s)
        wr = f"{d['wins']/(d['wins']+d['losses'])*100:.0f}%" if (d['wins']+d['losses']) > 0 else "N/A"
        print(f"    {d['strategy']}: {d['cnt']} trades, PnL=${d['total_pnl']:.2f}, Bet=${d['total_bet']:.2f}, WinRate={wr}")
    
    # By month
    print("\n  --- By Date (last 30 days) ---")
    date_rows = conn.execute("""
        SELECT DATE(created_at) as dt, COUNT(*) as cnt, SUM(pnl) as total_pnl,
               SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins,
               SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) as losses
        FROM trades WHERE created_at IS NOT NULL
        GROUP BY DATE(created_at) ORDER BY dt DESC LIMIT 30
    """).fetchall()
    for s in date_rows:
        d = dict(s)
        wr = f"{d['wins']/(d['wins']+d['losses'])*100:.0f}%" if (d['wins']+d['losses']) > 0 else "N/A"
        print(f"    {d['dt']}: {d['cnt']} trades, PnL=${d['total_pnl']:.2f}, W/L={d['wins']}/{d['losses']} ({wr})")

# Check pipeline_runs
if "pipeline_runs" in tables:
    cnt = conn.execute("SELECT COUNT(*) FROM pipeline_runs").fetchone()[0]
    if cnt > 0:
        print(f"\n  Pipeline runs: {cnt}")
        runs = conn.execute("SELECT * FROM pipeline_runs ORDER BY rowid DESC LIMIT 5").fetchall()
        for r in runs:
            d = dict(r)
            print(f"    {d}")

# Check outcomes
if "outcomes" in tables:
    cnt = conn.execute("SELECT COUNT(*) FROM outcomes").fetchone()[0]
    if cnt > 0:
        print(f"\n  Outcomes: {cnt}")

conn.close()

# Also check scratch/live_trades.json more detail
print("\n" + "=" * 70)
print("SCRATCH/LIVE_TRADES.JSON DETAIL")
print("=" * 70)
import json
if os.path.exists("scratch/live_trades.json"):
    with open("scratch/live_trades.json") as f:
        cached = json.load(f)
    
    total = len(cached)
    wins = [t for t in cached if t.get("result") == "win"]
    losses = [t for t in cached if t.get("result") == "loss"]
    pending = [t for t in cached if t.get("result") in ("pending", None, "")]
    total_pnl = sum(t.get("pnl", 0) or 0 for t in cached)
    total_bet = sum(t.get("amount_usd", 0) or 0 for t in cached)
    
    print(f"Total: {total}, Wins: {len(wins)}, Losses: {len(losses)}, Pending: {len(pending)}")
    print(f"PnL: ${total_pnl:.2f}, Bet: ${total_bet:.2f}")
    if total_bet > 0:
        print(f"ROI: {total_pnl/total_bet*100:.2f}%")
else:
    print("No live_trades.json found")

print("\n" + "=" * 70)
print("DONE")
print("=" * 70)