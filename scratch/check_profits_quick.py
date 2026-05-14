#!/usr/bin/env python3
"""Quick profit analysis of the polymarket pipeline."""
import sqlite3
import sys
import os

DB = "trades.db"
if not os.path.exists(DB):
    print(f"ERROR: {DB} not found")
    sys.exit(1)

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

print("=== Tables ===")
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
for t in tables:
    print(f"  {t['name']}")

# Check which tables have data
print("\n=== Table Row Counts ===")
for t in tables:
    cnt = conn.execute(f"SELECT COUNT(*) as c FROM [{t['name']}]").fetchone()["c"]
    print(f"  {t['name']}: {cnt} rows")

# Try demo_trades first, then trades
trade_table = None
for candidate in ['demo_trades', 'trades']:
    try:
        cnt = conn.execute(f"SELECT COUNT(*) as c FROM [{candidate}]").fetchone()["c"]
        if cnt > 0:
            trade_table = candidate
            break
    except:
        pass

if not trade_table:
    print("\nNo trade data found in any table!")
    conn.close()
    sys.exit(0)

print(f"\nUsing trade table: {trade_table}")
print(f"Schema: {[row[1] for row in conn.execute(f'PRAGMA table_info([{trade_table}])').fetchall()]}")

# Determine column names
cols = {row[1] for row in conn.execute(f"PRAGMA table_info([{trade_table}])").fetchall()}
print(f"\nAvailable columns: {sorted(cols)}")

# Find result/outcome column
result_col = None
for c in ['result', 'outcome', 'status']:
    if c in cols:
        result_col = c
        break

# Find pnl column
pnl_col = None
for c in ['pnl', 'profit', 'profit_usd', 'net_pnl']:
    if c in cols:
        pnl_col = c
        break

# Find amount column
amount_col = None
for c in ['bet_amount', 'amount_usd', 'stake', 'amount']:
    if c in cols:
        amount_col = c
        break

print(f"\nResult column: {result_col}")
print(f"PnL column: {pnl_col}")
print(f"Amount column: {amount_col}")

# Stats
total = conn.execute(f"SELECT COUNT(*) as c FROM [{trade_table}]").fetchone()["c"]
print(f"\n=== Overall Stats ===")
print(f"  Total trades: {total}")

if result_col:
    rows = conn.execute(f"SELECT [{result_col}], COUNT(*) as c FROM [{trade_table}] GROUP BY [{result_col}]").fetchall()
    for r in rows:
        print(f"  {r[result_col]}: {r['c']}")

if pnl_col:
    total_pnl = conn.execute(f"SELECT COALESCE(SUM([{pnl_col}]),0) as p FROM [{trade_table}]").fetchone()["p"]
    print(f"  Total PnL: ${total_pnl:.2f}")
    
    if result_col:
        rows = conn.execute(f"""
            SELECT [{result_col}], COUNT(*) as c, 
                   COALESCE(SUM([{pnl_col}]),0) as total_pnl,
                   COALESCE(AVG([{pnl_col}]),0) as avg_pnl
            FROM [{trade_table}] GROUP BY [{result_col}]
        """).fetchall()
        print(f"\n=== PnL by Result ===")
        for r in rows:
            print(f"  {r[result_col]}: {r['c']} trades, PnL=${r['total_pnl']:.2f}, Avg=${r['avg_pnl']:.2f}")

if amount_col:
    total_bet = conn.execute(f"SELECT COALESCE(SUM([{amount_col}]),0) as b FROM [{trade_table}]").fetchone()["b"]
    print(f"  Total Bet Amount: ${total_bet:.2f}")

# Strategy breakdown
if 'strategy' in cols:
    print(f"\n=== By Strategy ===")
    q = f"SELECT strategy, COUNT(*) as c"
    if pnl_col:
        q += f", COALESCE(SUM([{pnl_col}]),0) as total_pnl, COALESCE(AVG([{pnl_col}]),0) as avg_pnl"
    q += f" FROM [{trade_table}] GROUP BY strategy"
    rows = conn.execute(q).fetchall()
    for r in rows:
        extra = f", PnL=${r['total_pnl']:.2f}, Avg=${r['avg_pnl']:.2f}" if pnl_col and 'total_pnl' in r.keys() else ""
        print(f"  {r['strategy']}: {r['c']} trades{extra}")

# Side breakdown
if 'side' in cols:
    print(f"\n=== By Side (YES vs NO) ===")
    q = f"SELECT side, COUNT(*) as c"
    if pnl_col:
        q += f", COALESCE(SUM([{pnl_col}]),0) as total_pnl"
    q += f" FROM [{trade_table}] GROUP BY side"
    rows = conn.execute(q).fetchall()
    for r in rows:
        extra = f", PnL=${r['total_pnl']:.2f}" if pnl_col and 'total_pnl' in r.keys() else ""
        print(f"  {r['side']}: {r['c']} trades{extra}")

# Top wins and losses
if pnl_col and result_col:
    print(f"\n=== Top 10 Wins ===")
    q_col = 'market_question' if 'market_question' in cols else 'market_id'
    rows = conn.execute(f"""
        SELECT *, [{pnl_col}] as pnl_val FROM [{trade_table}] 
        WHERE [{result_col}]='win' ORDER BY [{pnl_col}] DESC LIMIT 10
    """).fetchall()
    for r in rows:
        q = str(r[q_col])[:60] if r[q_col] else "?"
        print(f"  #{r['id']} ${r['pnl_val']:+.2f} | {q}")

    print(f"\n=== Top 10 Losses ===")
    rows = conn.execute(f"""
        SELECT *, [{pnl_col}] as pnl_val FROM [{trade_table}] 
        WHERE [{result_col}]='loss' ORDER BY [{pnl_col}] ASC LIMIT 10
    """).fetchall()
    for r in rows:
        q = str(r[q_col])[:60] if r[q_col] else "?"
        print(f"  #{r['id']} ${r['pnl_val']:+.2f} | {q}")

# Weekly PnL
if pnl_col and result_col:
    date_col = 'created_at' if 'created_at' in cols else 'timestamp'
    if date_col in cols:
        print(f"\n=== PnL Over Time (by week) ===")
        rows = conn.execute(f"""
            SELECT strftime('%Y-W%W', [{date_col}]) as week, COUNT(*) as trades,
                   COALESCE(SUM([{pnl_col}]),0) as total_pnl,
                   SUM(CASE WHEN [{result_col}]='win' THEN 1 ELSE 0 END) as wins
            FROM [{trade_table}] 
            WHERE [{result_col}] IS NOT NULL AND [{result_col}] != 'pending'
            GROUP BY week ORDER BY week
        """).fetchall()
        for r in rows:
            wr = f"{r['wins']/r['trades']*100:.0f}%" if r['trades'] > 0 else "N/A"
            print(f"  {r['week']}: {r['trades']} trades, PnL=${r['total_pnl']:.2f}, WinRate={wr}")

# Recent trades
print(f"\n=== Recent 20 Trades ===")
q_col = 'market_question' if 'market_question' in cols else 'market_id'
rows = conn.execute(f"SELECT * FROM [{trade_table}] ORDER BY id DESC LIMIT 20").fetchall()
for r in rows:
    rdict = dict(r)
    q = str(rdict.get(q_col, '?'))[:50]
    result_str = rdict.get(result_col, 'unknown') if result_col else 'unknown'
    pnl_str = f"${rdict[pnl_col]:+.2f}" if pnl_col and rdict.get(pnl_col) is not None else "—"
    amt_str = f"${rdict[amount_col]:.2f}" if amount_col and rdict.get(amount_col) is not None else "—"
    print(f"  #{r['id']} [{str(result_str):>7}] {pnl_str:>8} {amt_str:>8} | {q}")

# Sample full row
print(f"\n=== Sample Row ===")
rows = conn.execute(f"SELECT * FROM [{trade_table}] ORDER BY id DESC LIMIT 1").fetchall()
if rows:
    for k, v in dict(rows[0]).items():
        print(f"  {k}: {v}")

conn.close()
print("\nDone!")