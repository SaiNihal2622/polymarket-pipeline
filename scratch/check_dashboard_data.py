import sqlite3
import os

DB = os.path.join(os.path.dirname(__file__), '..', 'trades.db')
conn = sqlite3.connect(DB)
c = conn.cursor()

print("=== TABLES ===")
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
print(c.fetchall())

print("\n=== TRADES TABLE SCHEMA ===")
c.execute("PRAGMA table_info(trades)")
print(c.fetchall())

print("\n=== TOTAL TRADES ===")
c.execute("SELECT COUNT(*) FROM trades")
print(c.fetchone())

print("\n=== TRADES BY STATUS ===")
c.execute("SELECT status, COUNT(*) FROM trades GROUP BY status")
print(c.fetchall())

print("\n=== TRADES SINCE YESTERDAY ===")
c.execute("SELECT COUNT(*) FROM trades WHERE created_at >= datetime('now','-1 day')")
print(c.fetchone())

print("\n=== RECENT TRADES (last 10) ===")
try:
    c.execute("SELECT id, question, side, size, status, pnl, created_at FROM trades ORDER BY id DESC LIMIT 10")
    for r in c.fetchall():
        print(r)
except Exception as e:
    print(f"Error: {e}")

print("\n=== P&L SUMMARY ===")
try:
    c.execute("SELECT SUM(pnl), AVG(pnl), COUNT(*) FROM trades WHERE pnl IS NOT NULL")
    row = c.fetchone()
    print(f"sum_pnl={row[0]}, avg_pnl={row[1]}, count_with_pnl={row[2]}")
except Exception as e:
    print(f"Error: {e}")

print("\n=== SIGNAL ACCURACIES TABLE ===")
try:
    c.execute("SELECT * FROM signal_accuracies LIMIT 5")
    print(c.fetchall())
except Exception as e:
    print(f"No signal_accuracies table: {e}")

print("\n=== RESOLUTIONS TABLE ===")
try:
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%resolv%'")
    print(c.fetchall())
    c.execute("PRAGMA table_info(resolved_trades)")
    print(c.fetchall())
    c.execute("SELECT COUNT(*) FROM resolved_trades")
    print("resolved count:", c.fetchone())
except Exception as e:
    print(f"Error: {e}")

print("\n=== ALL COLUMNS IN TRADES ===")
c.execute("PRAGMA table_info(trades)")
cols = c.fetchall()
for col in cols:
    print(col)

conn.close()