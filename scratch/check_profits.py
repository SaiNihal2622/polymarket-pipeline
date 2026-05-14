import sqlite3

con = sqlite3.connect("bot.db")
con.row_factory = sqlite3.Row

print("=" * 60)
print("ALL-TIME TRADE SUMMARY")
print("=" * 60)

row = con.execute("""
    SELECT
        COUNT(*) as total,
        SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins,
        SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) as losses,
        SUM(CASE WHEN result='pending' THEN 1 ELSE 0 END) as pending,
        SUM(CASE WHEN result='void' THEN 1 ELSE 0 END) as voids,
        SUM(pnl) as total_pnl,
        AVG(confidence) as avg_conf,
        AVG(entry_price) as avg_entry
    FROM demo_trades
""").fetchone()

total = row["total"]
wins = row["wins"]
losses = row["losses"]
pending = row["pending"]
voids = row["voids"]
resolved = wins + losses
acc = (wins / resolved * 100) if resolved else 0
pnl = row["total_pnl"] or 0
avg_entry = row["avg_entry"] or 0
avg_conf = row["avg_conf"] or 0

print(f"Total trades:   {total}")
print(f"Wins:           {wins}")
print(f"Losses:         {losses}")
print(f"Pending:        {pending}")
print(f"Voids:          {voids}")
print(f"Accuracy:       {acc:.1f}%  ({wins}/{resolved} resolved)")
print(f"Total P&L:      ${pnl:+.2f}")
print(f"Avg entry:      ${avg_entry:.3f}")
print(f"Avg confidence: {avg_conf:.2f}")

print()
print("=" * 60)
print("LAST 24 HOURS")
print("=" * 60)
r24 = con.execute("""
    SELECT
        COUNT(*) as total,
        SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins,
        SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) as losses,
        SUM(CASE WHEN result='pending' THEN 1 ELSE 0 END) as pending,
        SUM(pnl) as total_pnl
    FROM demo_trades
    WHERE created_at >= datetime('now', '-24 hours')
""").fetchone()
r24_w = r24["wins"] or 0
r24_l = r24["losses"] or 0
r24_resolved = r24_w + r24_l
r24_acc = (r24_w / r24_resolved * 100) if r24_resolved else 0
r24_pnl = r24["total_pnl"] or 0
print(f"Trades (24h):   {r24['total']}")
print(f"Wins:           {r24_w}")
print(f"Losses:         {r24_l}")
print(f"Pending:        {r24['pending']}")
print(f"Accuracy:       {r24_acc:.1f}%  ({r24_w}/{r24_resolved})")
print(f"P&L (24h):      ${r24_pnl:+.2f}")

print()
print("=" * 60)
print("LAST 7 DAYS")
print("=" * 60)
r7 = con.execute("""
    SELECT
        COUNT(*) as total,
        SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins,
        SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) as losses,
        SUM(pnl) as total_pnl
    FROM demo_trades
    WHERE created_at >= datetime('now', '-7 days')
""").fetchone()
r7_w = r7["wins"] or 0
r7_l = r7["losses"] or 0
r7_resolved = r7_w + r7_l
r7_acc = (r7_w / r7_resolved * 100) if r7_resolved else 0
r7_pnl = r7["total_pnl"] or 0
print(f"Trades (7d):    {r7['total']}")
print(f"Wins:           {r7_w}")
print(f"Losses:         {r7_l}")
print(f"Accuracy:       {r7_acc:.1f}%  ({r7_w}/{r7_resolved})")
print(f"P&L (7d):       ${r7_pnl:+.2f}")

print()
print("=" * 60)
print("RECENT TRADES (last 20)")
print("=" * 60)
recent = con.execute("""
    SELECT market_question, side, entry_price, result, pnl, created_at
    FROM demo_trades ORDER BY id DESC LIMIT 20
""").fetchall()
for t in recent:
    q = t["market_question"][:60]
    icon = {"win": "✅", "loss": "❌", "pending": "⏳", "void": "⊗"}.get(t["result"], "?")
    print(f'{icon} {t["result"]:8s} | ${t["pnl"]:+.2f} | {t["side"]:3s} @{t["entry_price"]:.2f} | {q}')

print()
print("=" * 60)
print("P&L BY CATEGORY (resolved only)")
print("=" * 60)
cats = con.execute("""
    SELECT strategy,
        COUNT(*) as total,
        SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins,
        SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) as losses,
        SUM(pnl) as total_pnl
    FROM demo_trades
    WHERE result IN ('win','loss')
    GROUP BY strategy
    ORDER BY total_pnl DESC
""").fetchall()
for c in cats:
    resolved_c = (c["wins"] or 0) + (c["losses"] or 0)
    acc_c = (c["wins"] / resolved_c * 100) if resolved_c else 0
    pnl_c = c["total_pnl"] or 0
    print(f'  {c["strategy"] or "unlabeled":20s} | {resolved_c:3d} trades | {acc_c:5.1f}% acc | ${pnl_c:+.2f}')

con.close()