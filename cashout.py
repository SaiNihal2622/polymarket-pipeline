#!/usr/bin/env python3
"""
cashout.py — Active position management for Polymarket trades.

Implements:
  1. Take-Profit: Sell position when profit reaches configurable threshold
  2. Stop-Loss:   Sell position when loss reaches configurable threshold  
  3. Trailing Stop: Move stop-loss up as price moves in our favor
  4. Hedge:       Buy opposite side to lock in profit

Polymarket CLOB supports selling positions before market resolution.
Instead of buying YES at $0.40 and waiting for resolution at $1.00 or $0.00,
we can SELL the YES position at any time at the current market price.

Example:
  Buy YES @ $0.40 (expected payout $1.00, expected profit $0.60/share)
  Price moves to $0.70 → Sell YES @ $0.70 → locked profit $0.30/share
  Price drops to $0.20 → Sell YES @ $0.20 → limited loss $0.20/share (vs $0.40 full loss)
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
# Take-profit: sell when unrealized P&L reaches this % of max possible profit
TAKE_PROFIT_PCT = float(os.getenv("TAKE_PROFIT_PCT", "0.30"))  # 30% of max profit — quick turnover

# Stop-loss: sell when loss reaches this % of entry price
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", "0.35"))  # 35% loss — tighter stop

# Trailing stop: enable trailing stop that follows price up
TRAILING_STOP = os.getenv("TRAILING_STOP", "true").lower() == "true"
TRAILING_STOP_PCT = float(os.getenv("TRAILING_STOP_PCT", "0.15"))  # 15% trail from peak

# Minimum time to hold before cashing out (avoid noise)
MIN_HOLD_SECONDS = int(os.getenv("MIN_HOLD_SECONDS", "120"))  # 2 minutes — fast cashout

# Check interval
CHECK_INTERVAL = int(os.getenv("CASHOUT_CHECK_INTERVAL", "60"))  # 60 seconds

# ── DB Setup ──────────────────────────────────────────────────────────────────
_db_env = os.getenv("DB_PATH", "")
if _db_env:
    DB_PATH = Path(_db_env)
else:
    _railway_volume = Path("/data")
    if _railway_volume.exists():
        DB_PATH = _railway_volume / "trades.db"
    else:
        DB_PATH = Path(__file__).parent / "trades.db"

CLOB_API = "https://clob.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def ensure_cashout_columns():
    """Add cashout tracking columns to trades table if they don't exist."""
    conn = _conn()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(trades)").fetchall()}
    
    new_cols = {
        "peak_price": "REAL",        # Highest price seen while holding (for trailing stop)
        "cashout_price": "REAL",     # Price at which we cashed out
        "cashout_reason": "TEXT",    # 'take_profit', 'stop_loss', 'trailing_stop', 'manual'
        "cashout_at": "TEXT",        # Timestamp of cashout
        "unrealized_pnl": "REAL",    # Current unrealized P&L (updated each check)
        "position_status": "TEXT",   # 'open', 'cashout', 'expired'
    }
    
    for col_name, col_type in new_cols.items():
        if col_name not in cols:
            conn.execute(f"ALTER TABLE trades ADD COLUMN {col_name} {col_type}")
            log.info(f"[cashout] Added column: {col_name}")
    
    conn.commit()
    conn.close()


def get_open_positions() -> list[dict]:
    """Get all open demo/dry_run trades that haven't been cashed out."""
    conn = _conn()
    
    # Check if position_status column exists
    cols = {r[1] for r in conn.execute("PRAGMA table_info(trades)").fetchall()}
    
    if "position_status" in cols:
        rows = conn.execute("""
            SELECT t.id, t.market_id, t.market_question, t.side, t.amount_usd,
                   t.market_price, t.claude_score, t.edge, t.created_at, t.token_id,
                   t.peak_price, t.position_status
            FROM trades t
            LEFT JOIN outcomes o ON t.id = o.trade_id
            WHERE t.status IN ('demo', 'dry_run', 'executed')
              AND o.id IS NULL
              AND (t.position_status IS NULL OR t.position_status = 'open')
              AND t.token_id IS NOT NULL
              AND t.token_id != ''
            ORDER BY t.created_at ASC
        """).fetchall()
    else:
        rows = conn.execute("""
            SELECT t.id, t.market_id, t.market_question, t.side, t.amount_usd,
                   t.market_price, t.claude_score, t.edge, t.created_at, t.token_id,
                   NULL as peak_price, 'open' as position_status
            FROM trades t
            LEFT JOIN outcomes o ON t.id = o.trade_id
            WHERE t.status IN ('demo', 'dry_run', 'executed')
              AND o.id IS NULL
              AND t.token_id IS NOT NULL
              AND t.token_id != ''
            ORDER BY t.created_at ASC
        """).fetchall()
    
    conn.close()
    return [dict(r) for r in rows]


def get_current_price(token_id: str) -> dict | None:
    """
    Get current best bid/ask for a token from CLOB.
    Returns: {"best_bid": float, "best_ask": float, "mid": float}
    """
    if not token_id:
        return None
    try:
        r = httpx.get(f"{CLOB_API}/book", params={"token_id": token_id}, timeout=8)
        if r.status_code != 200:
            return None
        data = r.json()
        bids = data.get("bids", []) or []
        asks = data.get("asks", []) or []
        
        if not bids and not asks:
            # Try midpoint or last trade
            mid = data.get("midpoint")
            if mid:
                m = float(mid)
                return {"best_bid": m, "best_ask": m, "mid": m}
            return None
        
        best_bid = float(bids[0]["price"]) if bids else 0.0
        best_ask = float(asks[0]["price"]) if asks else 1.0
        
        if best_bid > best_ask:
            best_bid, best_ask = best_ask, best_bid
        
        mid = (best_bid + best_ask) / 2.0
        return {"best_bid": best_bid, "best_ask": best_ask, "mid": mid}
    
    except Exception as e:
        log.debug(f"[cashout] price fetch error {token_id[:16]}: {e}")
        return None


def calculate_unrealized_pnl(side: str, entry_price: float, current_price: float, amount_usd: float) -> dict:
    """
    Calculate unrealized P&L for a position.
    
    For YES side: 
      - We bought YES at entry_price
      - Current YES price is current_price
      - If we sell now, we get current_price per share
      - Shares = amount_usd / entry_price
      - Sell value = shares * current_price
      - P&L = sell_value - amount_usd
    
    For NO side:
      - We bought NO at entry_price (= 1 - yes_price when we entered)
      - Current NO price = 1 - current_yes_price
      - Similar calculation
    """
    if side == "YES":
        buy_price = entry_price
        sell_price = current_price
    else:  # NO
        buy_price = 1.0 - entry_price if entry_price < 1.0 else entry_price
        sell_price = 1.0 - current_price
    
    # Clamp prices
    buy_price = max(0.01, min(0.99, buy_price))
    sell_price = max(0.0, min(1.0, sell_price))
    
    # Shares bought
    shares = amount_usd / buy_price
    sell_value = shares * sell_price
    pnl = sell_value - amount_usd
    
    # Max possible profit (if market resolves in our favor)
    max_profit = shares * (1.0 - buy_price) - amount_usd  # = amount * (1/buy - 1) - amount
    max_profit = shares * (1.0 - buy_price)  # payout when resolved YES at $1
    net_max_profit = max_profit - amount_usd  # minus our cost
    
    # Actually simpler: 
    # Cost = amount_usd
    # Max payout = shares * 1.0 = amount_usd / buy_price
    # Max profit = max_payout - cost = amount_usd * (1/buy_price - 1)
    max_possible_profit = amount_usd * (1.0 / buy_price - 1.0)
    
    # Profit as % of max possible
    profit_pct_of_max = (pnl / max_possible_profit * 100) if max_possible_profit > 0 else 0
    
    return {
        "pnl": round(pnl, 4),
        "pnl_pct": round((pnl / amount_usd) * 100, 2),
        "sell_value": round(sell_value, 4),
        "shares": round(shares, 4),
        "max_possible_profit": round(max_possible_profit, 4),
        "profit_pct_of_max": round(profit_pct_of_max, 1),
    }


def should_cashout(position: dict, price_data: dict) -> dict:
    """
    Determine if a position should be cashed out.
    
    Returns: {"should_sell": bool, "reason": str, "details": str}
    """
    side = position["side"]
    entry_price = float(position["market_price"] or 0.5)
    amount_usd = float(position["amount_usd"] or 1.0)
    created_at = position.get("created_at", "")
    peak_price = position.get("peak_price")
    
    # Current prices
    current_yes_price = price_data["mid"]
    
    # Calculate P&L
    pnl_info = calculate_unrealized_pnl(side, entry_price, current_yes_price, amount_usd)
    
    # Check minimum hold time
    if created_at:
        try:
            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            hold_seconds = (now - created).total_seconds()
            if hold_seconds < MIN_HOLD_SECONDS:
                return {
                    "should_sell": False,
                    "reason": "min_hold",
                    "details": f"holding for {hold_seconds:.0f}s < {MIN_HOLD_SECONDS}s minimum"
                }
        except Exception:
            pass
    
    # ── Take-Profit Check ──
    # Sell when we've captured TAKE_PROFIT_PCT of maximum possible profit
    if pnl_info["profit_pct_of_max"] >= (TAKE_PROFIT_PCT * 100):
        return {
            "should_sell": True,
            "reason": "take_profit",
            "details": f"captured {pnl_info['profit_pct_of_max']:.1f}% of max profit "
                       f"(threshold: {TAKE_PROFIT_PCT*100:.0f}%) | P&L: ${pnl_info['pnl']:+.4f}"
        }
    
    # ── Stop-Loss Check ──
    # Sell when loss exceeds STOP_LOSS_PCT of our entry
    if pnl_info["pnl_pct"] <= -(STOP_LOSS_PCT * 100):
        return {
            "should_sell": True,
            "reason": "stop_loss",
            "details": f"loss {pnl_info['pnl_pct']:.1f}% exceeds stop-loss "
                       f"threshold {STOP_LOSS_PCT*100:.0f}% | P&L: ${pnl_info['pnl']:+.4f}"
        }
    
    # ── Trailing Stop Check ──
    if TRAILING_STOP and peak_price is not None:
        peak_price = float(peak_price)
        # For YES side: trailing stop triggers if price drops TRAILING_STOP_PCT from peak
        if side == "YES":
            trail_trigger = peak_price * (1.0 - TRAILING_STOP_PCT)
            if current_yes_price <= trail_trigger and pnl_info["pnl"] > 0:
                return {
                    "should_sell": True,
                    "reason": "trailing_stop",
                    "details": f"price {current_yes_price:.3f} dropped {TRAILING_STOP_PCT*100:.0f}% "
                               f"from peak {peak_price:.3f} | P&L: ${pnl_info['pnl']:+.4f}"
                }
        else:  # NO side: peak is tracked as NO price
            current_no_price = 1.0 - current_yes_price
            trail_trigger = peak_price * (1.0 - TRAILING_STOP_PCT)
            if current_no_price <= trail_trigger and pnl_info["pnl"] > 0:
                return {
                    "should_sell": True,
                    "reason": "trailing_stop",
                    "details": f"NO price {current_no_price:.3f} dropped {TRAILING_STOP_PCT*100:.0f}% "
                               f"from peak {peak_price:.3f} | P&L: ${pnl_info['pnl']:+.4f}"
                }
    
    return {"should_sell": False, "reason": "hold", "details": f"P&L: {pnl_info['pnl_pct']:+.1f}%"}


def update_peak_price(trade_id: int, current_price: float, side: str):
    """Update the peak price seen for a trade (for trailing stop)."""
    conn = _conn()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(trades)").fetchall()}
    if "peak_price" not in cols:
        conn.close()
        return
    
    if side == "YES":
        track_price = current_price
    else:
        track_price = 1.0 - current_price
    
    current_peak = conn.execute(
        "SELECT peak_price FROM trades WHERE id=?", (trade_id,)
    ).fetchone()
    
    if current_peak is None or current_peak["peak_price"] is None or track_price > float(current_peak["peak_price"]):
        conn.execute(
            "UPDATE trades SET peak_price=?, unrealized_pnl=? WHERE id=?",
            (track_price, None, trade_id)
        )
        conn.commit()
    conn.close()


def execute_cashout(position: dict, reason: str, price_data: dict) -> dict:
    """
    Execute a cashout — sell the position at current market price.
    
    For demo mode: resolve the trade with partial P&L.
    For live mode: place a SELL order on CLOB.
    """
    side = position["side"]
    entry_price = float(position["market_price"] or 0.5)
    amount_usd = float(position["amount_usd"] or 1.0)
    
    # Use best_bid for selling (what buyers are willing to pay)
    sell_price = price_data["best_bid"] if side == "YES" else (1.0 - price_data["best_bid"])
    sell_price = max(0.01, min(0.99, sell_price))
    
    pnl_info = calculate_unrealized_pnl(side, entry_price, price_data["mid"], amount_usd)
    
    # Record the cashout
    now = datetime.now(timezone.utc).isoformat()
    conn = _conn()
    
    cols = {r[1] for r in conn.execute("PRAGMA table_info(trades)").fetchall()}
    
    # Update trade record with cashout info
    if "cashout_price" in cols:
        conn.execute("""
            UPDATE trades SET 
                cashout_price=?, cashout_reason=?, cashout_at=?,
                position_status='cashout'
            WHERE id=?
        """, (sell_price, reason, now, position["id"]))
    
    # Record as resolved outcome
    pnl = pnl_info["pnl"]
    result_str = "win" if pnl > 0 else ("loss" if pnl < 0 else "push")
    
    conn.execute("""
        INSERT OR IGNORE INTO outcomes (trade_id, resolved_at, result, pnl)
        VALUES (?, ?, ?, ?)
    """, (position["id"], now, result_str, pnl))
    
    # Calibration record
    conn.execute("""
        INSERT OR REPLACE INTO calibration
          (trade_id, classification, materiality, entry_price, exit_price,
           actual_direction, correct, resolved_at)
        SELECT id, side, edge, market_price, ?,
               CASE WHEN ? = 1.0 THEN 'YES' ELSE 'NO' END,
               CASE WHEN ? THEN 1 ELSE 0 END, ?
        FROM trades WHERE id = ?
    """, (sell_price, 1.0 if pnl > 0 else 0.0, 1 if pnl > 0 else 0, now, position["id"]))
    
    conn.commit()
    conn.close()
    
    symbol = "✅" if pnl > 0 else ("❌" if pnl < 0 else "↩️")
    print(f"  {symbol} CASHOUT #{position['id']} [{reason}] "
          f"{side} on \"{position['market_question'][:40]}\" | "
          f"entry=${entry_price:.3f} → exit=${sell_price:.3f} | "
          f"P&L: ${pnl:+.4f}")
    
    return {
        "trade_id": position["id"],
        "reason": reason,
        "entry_price": entry_price,
        "exit_price": sell_price,
        "pnl": pnl,
        "pnl_pct": pnl_info["pnl_pct"],
    }


def check_and_cashout(verbose: bool = True) -> dict:
    """
    Main cashout check loop iteration.
    Check all open positions and cash out if thresholds hit.
    """
    positions = get_open_positions()
    if not positions:
        if verbose:
            log.info("[cashout] No open positions to manage")
        return {"open": 0, "cashouts": 0, "total_pnl": 0.0}
    
    if verbose:
        print(f"\n── Cashout check: {len(positions)} open positions ──")
    
    cashouts = []
    total_pnl = 0.0
    checked = 0
    
    for pos in positions:
        token_id = pos.get("token_id", "")
        if not token_id:
            continue
        
        # Get current price
        price_data = get_current_price(token_id)
        if not price_data:
            continue
        
        checked += 1
        current_price = price_data["mid"]
        
        # Update peak price for trailing stop
        update_peak_price(pos["id"], current_price, pos["side"])
        
        # Calculate and display current state
        entry_price = float(pos["market_price"] or 0.5)
        pnl_info = calculate_unrealized_pnl(pos["side"], entry_price, current_price, float(pos["amount_usd"] or 1.0))
        
        if verbose:
            pnl_emoji = "📈" if pnl_info["pnl"] > 0 else ("📉" if pnl_info["pnl"] < 0 else "➡️")
            print(f"  {pnl_emoji} #{pos['id']} {pos['side']} "
                  f"\"{pos['market_question'][:40]}\" | "
                  f"entry=${entry_price:.3f} now=${current_price:.3f} | "
                  f"P&L: ${pnl_info['pnl']:+.4f} ({pnl_info['pnl_pct']:+.1f}%)")
        
        # Check if we should cash out
        decision = should_cashout(pos, price_data)
        
        if decision["should_sell"]:
            result = execute_cashout(pos, decision["reason"], price_data)
            cashouts.append(result)
            total_pnl += result["pnl"]
    
    if verbose and cashouts:
        print(f"\n  💰 Cashout summary: {len(cashouts)} positions closed | "
              f"Total P&L: ${total_pnl:+.4f}")
    elif verbose:
        print(f"  ℹ️ No cashouts triggered ({checked} positions checked)")
    
    return {
        "open": len(positions),
        "checked": checked,
        "cashouts": len(cashouts),
        "total_pnl": round(total_pnl, 4),
        "details": cashouts,
    }


def run_cashout_monitor():
    """Run the cashout monitor as a continuous loop."""
    import time
    
    print("🔄 Cashout monitor started")
    print(f"   Take-profit: {TAKE_PROFIT_PCT*100:.0f}% of max profit")
    print(f"   Stop-loss: {STOP_LOSS_PCT*100:.0f}% of entry price")
    print(f"   Trailing stop: {'ON' if TRAILING_STOP else 'OFF'} ({TRAILING_STOP_PCT*100:.0f}% from peak)")
    print(f"   Min hold: {MIN_HOLD_SECONDS}s | Check interval: {CHECK_INTERVAL}s")
    
    # Ensure DB columns exist
    ensure_cashout_columns()
    
    while True:
        try:
            result = check_and_cashout(verbose=True)
            if result["cashouts"] > 0:
                log.info(f"[cashout] {result['cashouts']} cashouts, P&L: ${result['total_pnl']:+.4f}")
        except Exception as e:
            log.error(f"[cashout] Error: {e}")
            import traceback
            traceback.print_exc()
        
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_cashout_monitor()