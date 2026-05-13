"""Remote profit audit - run on Railway to get full profit analysis."""
import sqlite3
import os
from datetime import datetime, timezone, timedelta

# Try multiple possible DB paths
DB_PATHS = ["trades.db", "/app/trades.db", "/data/trades.db", "bot.db"]

def find_db():
    for p in DB_PATHS:
        if os.path.exists(p) and os.path.getsize(p) > 0:
            return p
    # Search for any .db file
    for root, dirs, files in os.walk("/app", topdown=True):
        dirs[:] = [d for d in dirs if d not in ['node_modules', '.git', '__pycache__', '.venv', 'venv']]
        for f in files:
            if f.endswith('.db') and os.path.getsize(os.path.join(root, f)) > 100:
                return os.path.join(root, f)
    # Check cwd
    for f in os.listdir('.'):
        if f.endswith('.db') and os.path.getsize(f) > 100:
            return f
    return None

db_path = find_db()
if not db_path:
    print("ERROR: No database file found!")
    print(f"CWD: {os.getcwd()}")
    print(f"Files: {[f for f in os.listdir('.') if f.endswith('.db')]}")
    exit(1)

print(f"Using database: {db_path} ({os.path.getsize(db_path)} bytes)")
con = sqlite3.connect(db_path)
con.row_factory = sqlite3.Row

# List tables
tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print(f"Tables: {tables}")

# Check demo_trades
if 'demo_trades' in tables:
    total = con.execute("SELECT COUNT(*) FROM demo_trades").fetchone()[0]
    print(f"\ndemo_trades: {total} rows")
    
    if total > 0:
        # Results breakdown
        results = con.execute("""
            SELECT result, COUNT(*) as c FROM demo_trades GROUP BY result
        """).fetchall()
        print("\n=== RESULTS BREAKDOWN ===")
        for r in results:
            print(f"  {r['result']}: {r['c']}")
        
        # PnL
        pnl = con.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN result='win' THEN pnl ELSE 0 END), 0) as gross_win,
                COALESCE(SUM(CASE WHEN result='loss' THEN pnl ELSE 0 END), 0) as gross_loss,
                COALESCE(SUM(CASE WHEN result IN ('win','loss') THEN pnl ELSE 0 END), 0) as net_pnl,
                COALESCE(SUM(bet_amount), 0) as total_wagered,
                COUNT(CASE WHEN result='win' THEN 1 END) as wins,
                COUNT(CASE WHEN result='loss' THEN 1 END) as losses,
                COUNT(CASE WHEN result='void' THEN 1 END) as voids,
                COUNT(CASE WHEN result='pending' THEN 1 END) as pending
            FROM demo_trades
        """).fetchone()
        
        print(f"\n=== PROFIT & LOSS ===")
        print(f"  Total wagered:  ${pnl['total_wagered']:.2f}")
        print(f"  Gross wins:     +${pnl['gross_win']:.2f}")
        print(f"  Gross losses:   {pnl['gross_loss']:.2f}")
        print(f"  NET PnL:        ${pnl['net_pnl']:+.2f}")
        
        resolved = pnl['wins'] + pnl['losses']
        if resolved > 0:
            acc = pnl['wins'] / resolved * 100
            print(f"  Win rate:       {acc:.1f}% ({pnl['wins']}W / {resolved}R)")
            avg_win = pnl['gross_win'] / pnl['wins'] if pnl['wins'] > 0 else 0
            avg_loss = abs(pnl['gross_loss'] / pnl['losses']) if pnl['losses'] > 0 else 0
            print(f"  Avg win:        +${avg_win:.2f}")
            print(f"  Avg loss:       -${avg_loss:.2f}")
            if avg_loss > 0:
                print(f"  Risk/Reward:    1:{avg_win/avg_loss:.2f}")
        
        # By strategy
        print(f"\n=== BY STRATEGY ===")
        strats = con.execute("""
            SELECT strategy,
                COUNT(*) as total,
                SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as w,
                SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) as l,
                SUM(CASE WHEN result='pending' THEN 1 ELSE 0 END) as p,
                COALESCE(SUM(CASE WHEN result IN ('win','loss') THEN pnl ELSE 0 END), 0) as pnl
            FROM demo_trades GROUP BY strategy ORDER BY pnl DESC
        """).fetchall()
        for s in strats:
            res = s['w'] + s['l']
            win_pct = s['w'] / res * 100 if res > 0 else 0
            print(f"  {s['strategy']:<20} {s['total']:>3}T | {s['w']}W/{s['l']}L/{s['p']}P | ${s['pnl']:>+7.2f} | {win_pct:.0f}%")
        
        # By side
        print(f"\n=== BY SIDE ===")
        for side in ['YES', 'NO']:
            row = con.execute("""
                SELECT COUNT(*) as total,
                    SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as w,
                    SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) as l,
                    COALESCE(SUM(CASE WHEN result IN ('win','loss') THEN pnl ELSE 0 END), 0) as pnl
                FROM demo_trades WHERE side=?
            """, (side,)).fetchone()
            res = row['w'] + row['l']
            wp = row['w'] / res * 100 if res > 0 else 0
            print(f"  {side}: {row['total']}T | {wp:.0f}% win | PnL: ${row['pnl']:+.2f}")
        
        # By price range
        print(f"\n=== BY ENTRY PRICE ===")
        ranges = [(0.01, 0.15), (0.15, 0.25), (0.25, 0.35), (0.35, 0.50), (0.50, 0.70), (0.70, 1.00)]
        for lo, hi in ranges:
            row = con.execute("""
                SELECT COUNT(*) as total,
                    SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as w,
                    SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) as l,
                    COALESCE(SUM(CASE WHEN result IN ('win','loss') THEN pnl ELSE 0 END), 0) as pnl
                FROM demo_trades WHERE entry_price >= ? AND entry_price < ?
            """, (lo, hi)).fetchone()
            if row['total'] > 0:
                res = row['w'] + row['l']
                wp = row['w'] / res * 100 if res > 0 else 0
                print(f"  ${lo:.2f}-${hi:.2f}: {row['total']:>3}T | {wp:.0f}% win | ${row['pnl']:>+7.2f}")
        
        # Pending trades
        pending = con.execute("""
            SELECT id, market_question, side, bet_amount, entry_price, strategy, created_at
            FROM demo_trades WHERE result='pending' ORDER BY created_at DESC
        """).fetchall()
        if pending:
            print(f"\n=== PENDING TRADES ({len(pending)}) ===")
            total_risk = sum(t['bet_amount'] for t in pending)
            for t in pending[:20]:
                q = (t['market_question'] or '')[:60]
                created = (t['created_at'] or '')[:16]
                print(f"  #{t['id']} {t['side']} ${t['bet_amount']:.2f}@{t['entry_price']:.2f} {t['strategy']:<18} {created} | {q}")
            if len(pending) > 20:
                print(f"  ... and {len(pending)-20} more")
            print(f"  Total capital at risk: ${total_risk:.2f}")
        
        # Daily timeline
        print(f"\n=== DAILY TIMELINE ===")
        days = con.execute("""
            SELECT DATE(created_at) as day, COUNT(*) as c,
                SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as w,
                SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) as l,
                SUM(CASE WHEN result='pending' THEN 1 ELSE 0 END) as p,
                COALESCE(SUM(CASE WHEN result IN ('win','loss') THEN pnl ELSE 0 END), 0) as pnl
            FROM demo_trades GROUP BY DATE(created_at) ORDER BY day
        """).fetchall()
        for d in days:
            print(f"  {d['day']}: {d['c']:>3}T ({d['w']}W/{d['l']}L/{d['p']}P) ${d['pnl']:>+7.2f}")
        
        # S13 specific
        print(f"\n=== S13_DEADZONE_NO DETAIL ===")
        s13 = con.execute("""
            SELECT result, COUNT(*) as c,
                COALESCE(SUM(CASE WHEN result IN ('win','loss') THEN pnl ELSE 0 END), 0) as pnl,
                AVG(entry_price) as avg_price,
                AVG(bet_amount) as avg_bet
            FROM demo_trades WHERE strategy='S13_deadzone_no' GROUP BY result
        """).fetchall()
        if s13:
            for s in s13:
                print(f"  {s['result']}: {s['c']} | PnL: ${s['pnl']:+.2f} | Avg price: ${s['avg_price']:.2f} | Avg bet: ${s['avg_bet']:.2f}")
        else:
            print("  No S13 trades found")
        
        # Bankroll
        if 'bankroll' in tables:
            br = con.execute("SELECT * FROM bankroll ORDER BY updated_at DESC LIMIT 1").fetchone()
            br_init = con.execute("SELECT * FROM bankroll ORDER BY updated_at ASC LIMIT 1").fetchone()
            if br:
                print(f"\n=== BANKROLL ===")
                print(f"  Current: ${br['amount']:.2f}")
                if br_init:
                    change = br['amount'] - br_init['amount']
                    print(f"  Initial: ${br_init['amount']:.2f}")
                    print(f"  Change:  ${change:+.2f} ({change/br_init['amount']*100:+.1f}%)")
        
        # Resolved trades with Polymarket links
        print(f"\n=== RECENT RESOLVED TRADES ===")
        resolved_list = con.execute("""
            SELECT id, market_question, side, bet_amount, entry_price, result, pnl, 
                   strategy, market_slug, created_at, resolved_at
            FROM demo_trades 
            WHERE result IN ('win','loss') 
            ORDER BY resolved_at DESC LIMIT 20
        """).fetchall()
        for t in resolved_list:
            sym = "✅" if t['result'] == 'win' else "❌"
            q = (t['market_question'] or '')[:55]
            slug = t['market_slug'] or ''
            print(f"  {sym} #{t['id']} {t['side']} ${t['bet_amount']:.2f}@{t['entry_price']:.2f} → ${t['pnl']:+.2f} | {t['strategy']}")
            print(f"      {q}")
            if slug:
                print(f"      https://polymarket.com/event/{slug}")

# Also check trades table (live trades)
if 'trades' in tables:
    t_count = con.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    print(f"\n=== LIVE TRADES TABLE: {t_count} rows ===")
    if t_count > 0:
        statuses = con.execute("SELECT status, COUNT(*) as c FROM trades GROUP BY status").fetchall()
        for s in statuses:
            print(f"  {s['status']}: {s['c']}")
        # Show recent live trades
        recent = con.execute("""
            SELECT id, market_question, side, amount_usd, market_price, status, strategy, created_at
            FROM trades ORDER BY created_at DESC LIMIT 10
        """).fetchall()
        for t in recent:
            q = (t['market_question'] or '')[:55]
            print(f"  #{t['id']} {t['side']} ${t['amount_usd']:.2f}@{t['market_price']:.2f} [{t['status']}] {t['strategy']} | {q}")

if 'outcomes' in tables:
    o_count = con.execute("SELECT COUNT(*) FROM outcomes").fetchone()[0]
    print(f"\n=== OUTCOMES TABLE: {o_count} rows ===")
    if o_count > 0:
        outcomes = con.execute("""
            SELECT o.result, o.pnl, t.market_question, t.side
            FROM outcomes o JOIN trades t ON o.trade_id = t.id
            ORDER BY o.resolved_at DESC LIMIT 10
        """).fetchall()
        for o in outcomes:
            q = (o['market_question'] or '')[:55]
            print(f"  {o['result']} ${o['pnl']:+.2f} {o['side']} | {q}")

con.close()
print("\n=== AUDIT COMPLETE ===")