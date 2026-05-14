"""Query all tables in bot.db for full trade history."""
import sqlite3
import json

con = sqlite3.connect('bot.db')
con.row_factory = sqlite3.Row

# List all tables with row counts
tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print("=" * 70)
print(f"ALL TABLES ({len(tables)})")
print("=" * 70)

for t in tables:
    cols = [r[1] for r in con.execute(f"PRAGMA table_info({t})").fetchall()]
    cnt = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"\n  {t}: {cnt} rows")
    print(f"    Columns: {cols}")

# Deep dive into demo_trades
print("\n" + "=" * 70)
print("DEMO_TRADES - FULL DATA")
print("=" * 70)

try:
    cnt = con.execute("SELECT COUNT(*) FROM demo_trades").fetchone()[0]
    print(f"Total demo trades: {cnt}")
    
    if cnt > 0:
        cols = [r[1] for r in con.execute("PRAGMA table_info(demo_trades)").fetchall()]
        print(f"Columns: {cols}")
        
        rows = con.execute("SELECT * FROM demo_trades ORDER BY rowid DESC LIMIT 200").fetchall()
        
        # Summary stats
        resolved = [dict(r) for r in rows if r['result'] is not None]
        wins = [r for r in resolved if r.get('result') == 'win']
        losses = [r for r in resolved if r.get('result') == 'loss']
        voids = [r for r in resolved if r.get('result') == 'void']
        pending = [dict(r) for r in rows if r['result'] is None]
        
        total_pnl = sum((r.get('pnl') or 0) for r in resolved)
        total_wagered = sum((r.get('amount_usd') or 0) for r in resolved)
        win_pnl = sum((r.get('pnl') or 0) for r in wins)
        loss_pnl = sum((r.get('pnl') or 0) for r in losses)
        
        print(f"\nResolved: {len(resolved)} | Wins: {len(wins)} | Losses: {len(losses)} | Voids: {len(voids)} | Pending: {len(pending)}")
        print(f"Total Wagered: ${total_wagered:.2f}")
        print(f"Total P&L: ${total_pnl:.2f}")
        print(f"Win P&L: ${win_pnl:.2f} | Loss P&L: ${loss_pnl:.2f}")
        if total_wagered > 0:
            print(f"ROI: {total_pnl/total_wagered*100:.1f}%")
        if len(resolved) > 0:
            print(f"Win Rate: {len(wins)/len(resolved)*100:.1f}%")
        
        # By strategy
        from collections import defaultdict
        strats = defaultdict(lambda: {'count': 0, 'wins': 0, 'pnl': 0, 'wagered': 0})
        for r in resolved:
            s = r.get('strategy') or 'unknown'
            strats[s]['count'] += 1
            strats[s]['wagered'] += r.get('amount_usd') or 0
            strats[s]['pnl'] += r.get('pnl') or 0
            if r.get('result') == 'win':
                strats[s]['wins'] += 1
        
        print(f"\nBy Strategy:")
        for s, d in sorted(strats.items()):
            wr = d['wins']/d['count']*100 if d['count'] > 0 else 0
            roi = d['pnl']/d['wagered']*100 if d['wagered'] > 0 else 0
            print(f"  {s}: {d['count']} trades (W:{d['wins']}) | WR:{wr:.1f}% | Wagered:${d['wagered']:.2f} | P&L:${d['pnl']:.2f} | ROI:{roi:.1f}%")
        
        # By date
        dates = defaultdict(lambda: {'count': 0, 'wins': 0, 'pnl': 0})
        for r in resolved:
            d = (r.get('created_at') or '')[:10]
            dates[d]['count'] += 1
            dates[d]['pnl'] += r.get('pnl') or 0
            if r.get('result') == 'win':
                dates[d]['wins'] += 1
        
        print(f"\nBy Date:")
        for d in sorted(dates.keys()):
            dd = dates[d]
            wr = dd['wins']/dd['count']*100 if dd['count'] > 0 else 0
            print(f"  {d}: {dd['count']} trades | WR:{wr:.1f}% | P&L:${dd['pnl']:.2f}")
        
        # Print all resolved trades
        print(f"\n{'='*70}")
        print("ALL RESOLVED TRADES")
        print(f"{'='*70}")
        for r in sorted(resolved, key=lambda x: x.get('created_at', '')):
            print(f"  [{r.get('created_at','')[:16]}] {r.get('market_question','')[:55]}")
            print(f"    Side:{r.get('side')} @ {r.get('market_price')} | P&L:${r.get('pnl',0):.2f} | {r.get('result')} | Strategy:{r.get('strategy')}")
except Exception as e:
    print(f"Error: {e}")

# Check outcomes table
print(f"\n{'='*70}")
print("OUTCOMES TABLE")
print(f"{'='*70}")
try:
    cnt = con.execute("SELECT COUNT(*) FROM outcomes").fetchone()[0]
    print(f"Total outcomes: {cnt}")
    if cnt > 0:
        rows = con.execute("SELECT * FROM outcomes ORDER BY rowid DESC LIMIT 20").fetchall()
        for r in rows:
            print(dict(r))
except Exception as e:
    print(f"Error: {e}")

# Check pipeline_runs
print(f"\n{'='*70}")
print("PIPELINE_RUNS TABLE")
print(f"{'='*70}")
try:
    cnt = con.execute("SELECT COUNT(*) FROM pipeline_runs").fetchone()[0]
    print(f"Total runs: {cnt}")
    if cnt > 0:
        rows = con.execute("SELECT * FROM pipeline_runs ORDER BY rowid DESC LIMIT 10").fetchall()
        for r in rows:
            print(dict(r))
except Exception as e:
    print(f"Error: {e}")

# Check demo_runs
print(f"\n{'='*70}")
print("DEMO_RUNS TABLE")
print(f"{'='*70}")
try:
    cnt = con.execute("SELECT COUNT(*) FROM demo_runs").fetchone()[0]
    print(f"Total demo runs: {cnt}")
    if cnt > 0:
        rows = con.execute("SELECT * FROM demo_runs ORDER BY rowid DESC LIMIT 10").fetchall()
        for r in rows:
            print(dict(r))
except Exception as e:
    print(f"Error: {e}")

con.close()
print("\nDone.")