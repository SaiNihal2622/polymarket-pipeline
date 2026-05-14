#!/usr/bin/env python3
"""Check all trade data sources across the project"""
import sqlite3
import json
import os
import glob

print("=" * 70)
print("COMPREHENSIVE POLYMARKET PIPELINE PROFIT AUDIT")
print("=" * 70)

# 1. Check trades.db (main)
print("\n[1] MAIN trades.db")
try:
    conn = sqlite3.connect("trades.db")
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in c.fetchall()]
    for t in tables:
        c.execute(f"SELECT COUNT(*) FROM {t}")
        cnt = c.fetchone()[0]
        print(f"  {t}: {cnt} rows")
    conn.close()
except Exception as e:
    print(f"  Error: {e}")

# 2. Check bot.db
print("\n[2] bot.db")
try:
    sz = os.path.getsize("bot.db")
    print(f"  File size: {sz} bytes")
    if sz > 0:
        conn = sqlite3.connect("bot.db")
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in c.fetchall()]
        print(f"  Tables: {tables}")
        conn.close()
except Exception as e:
    print(f"  Error: {e}")

# 3. Check worktree trades.db
print("\n[3] WORKTREE trades.db")
wt_path = ".claude/worktrees/serene-wu/trades.db"
try:
    conn = sqlite3.connect(wt_path)
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in c.fetchall()]
    for t in tables:
        try:
            c.execute(f"SELECT COUNT(*) FROM {t}")
            cnt = c.fetchone()[0]
            print(f"  {t}: {cnt} rows")
            if cnt > 0 and t == 'trades':
                c.execute(f"SELECT id, market_question, side, amount_usd, status, created_at FROM {t} ORDER BY id DESC LIMIT 5")
                for row in c.fetchall():
                    q = (row[1] or 'N/A')[:50]
                    print(f"    #{row[0]} | {q} | {row[2]} ${row[3]} | {row[4]} | {row[5]}")
        except:
            pass
    conn.close()
except Exception as e:
    print(f"  Error: {e}")

# 4. Check live_trades.json
print("\n[4] live_trades.json")
try:
    with open("scratch/live_trades.json") as f:
        data = json.load(f)
    if isinstance(data, list):
        print(f"  {len(data)} trades in JSON")
        total_pnl = sum(t.get('pnl', 0) or 0 for t in data)
        wins = sum(1 for t in data if (t.get('pnl', 0) or 0) > 0)
        losses = sum(1 for t in data if (t.get('pnl', 0) or 0) < 0)
        total_cost = sum(t.get('amount_usd', 0) or t.get('cost', 0) or 0 for t in data)
        print(f"  Total PnL: ${total_pnl:.2f}")
        print(f"  Wins: {wins}, Losses: {losses}")
        print(f"  Total Wagered: ${total_cost:.2f}")
        if total_cost > 0:
            print(f"  ROI: {total_pnl/total_cost*100:.1f}%")
        # Show by strategy
        strats = {}
        for t in data:
            s = t.get('strategy', 'unknown')
            if s not in strats:
                strats[s] = {'cnt': 0, 'pnl': 0, 'wins': 0, 'losses': 0, 'cost': 0}
            strats[s]['cnt'] += 1
            strats[s]['pnl'] += t.get('pnl', 0) or 0
            strats[s]['cost'] += t.get('amount_usd', 0) or t.get('cost', 0) or 0
            if (t.get('pnl', 0) or 0) > 0:
                strats[s]['wins'] += 1
            elif (t.get('pnl', 0) or 0) < 0:
                strats[s]['losses'] += 1
        print("\n  By strategy:")
        for s, v in sorted(strats.items(), key=lambda x: -x[1]['pnl']):
            roi = (v['pnl']/v['cost']*100) if v['cost'] > 0 else 0
            print(f"    {s}: {v['cnt']} trades | {v['wins']}W/{v['losses']}L | PnL=${v['pnl']:.2f} | Cost=${v['cost']:.2f} | ROI={roi:.1f}%")
        # Show all trades
        print("\n  All trades:")
        for t in data:
            q = (t.get('market_question', 'N/A'))[:55]
            pnl = t.get('pnl', 0) or 0
            cost = t.get('amount_usd', 0) or t.get('cost', 0) or 0
            result = t.get('result', t.get('outcome', 'N/A'))
            print(f"    {q} | {t.get('side','')} ${cost:.2f} | pnl=${pnl:.2f} | {t.get('strategy','')} | {result}")
    elif isinstance(data, dict):
        print(f"  Keys: {list(data.keys())[:10]}")
        for k, v in data.items():
            if isinstance(v, list):
                print(f"    {k}: {len(v)} items")
            elif isinstance(v, (int, float)):
                print(f"    {k}: {v}")
except FileNotFoundError:
    print("  File not found")
except Exception as e:
    print(f"  Error: {e}")

# 5. Check any other JSON files with trade data
print("\n[5] Other trade-related files")
for pat in ["scratch/*.json", "*.json"]:
    for f in glob.glob(pat):
        if f == "scratch/live_trades.json":
            continue
        try:
            with open(f) as fh:
                data = json.load(fh)
            if isinstance(data, list) and len(data) > 0:
                if any('pnl' in str(d) or 'trade' in str(d).lower() for d in data[:3]):
                    print(f"  {f}: {len(data)} items")
            elif isinstance(data, dict):
                if 'trades' in data or 'pnl' in data:
                    print(f"  {f}: keys={list(data.keys())[:5]}")
        except:
            pass

# 6. Check log files for PnL info
print("\n[6] Checking logs for trade/PnL info")
try:
    with open("polymarket_bot.log") as f:
        lines = f.readlines()
    pnl_lines = [l.strip() for l in lines if 'pnl' in l.lower() or 'profit' in l.lower() or 'trade placed' in l.lower() or 'resolved' in l.lower()]
    print(f"  Log has {len(lines)} lines, {len(pnl_lines)} trade-related lines")
    for l in pnl_lines[-15:]:
        print(f"    {l[:120]}")
except FileNotFoundError:
    print("  No log file found")
except Exception as e:
    print(f"  Error: {e}")

# 7. Check scan_log.txt
print("\n[7] Checking scan_log.txt")
try:
    with open("scan_log.txt") as f:
        lines = f.readlines()
    print(f"  {len(lines)} lines")
    for l in lines[-10:]:
        print(f"    {l.strip()[:120]}")
except FileNotFoundError:
    print("  No scan_log.txt")
except Exception as e:
    print(f"  Error: {e}")

# 8. Check CONTEXT_HANDOFF.md for profit info
print("\n[8] CONTEXT_HANDOFF.md excerpt")
try:
    with open("CONTEXT_HANDOFF.md") as f:
        content = f.read()
    # Look for profit/financial sections
    for keyword in ['profit', 'PnL', 'pnl', 'total', 'trade', 'wagered', 'win rate', 'ROI']:
        idx = content.lower().find(keyword.lower())
        if idx >= 0:
            start = max(0, idx - 50)
            end = min(len(content), idx + 200)
            print(f"\n  ...{content[start:end]}...")
            break
except FileNotFoundError:
    print("  Not found")

print("\n" + "=" * 70)
print("AUDIT COMPLETE")
print("=" * 70)