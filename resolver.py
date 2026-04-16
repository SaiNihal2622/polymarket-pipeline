#!/usr/bin/env python3
"""
resolver.py — Polls Polymarket Gamma API to resolve demo trades.
Checks if markets have closed, determines win/loss, updates DB.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

_db_env = os.getenv("DB_PATH", "")
DB_PATH = Path(_db_env) if _db_env else Path(__file__).parent / "trades.db"
GAMMA_API = "https://gamma-api.polymarket.com"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def get_pending_demo_trades() -> list[dict]:
    """Get all demo/dry_run trades not yet resolved."""
    conn = _conn()
    rows = conn.execute("""
        SELECT t.id, t.market_id, t.market_question, t.side, t.amount_usd,
               t.claude_score, t.market_price, t.edge, t.created_at
        FROM trades t
        LEFT JOIN outcomes o ON t.id = o.trade_id
        WHERE t.status IN ('demo', 'dry_run')
          AND o.id IS NULL
          AND t.market_id != ''
        ORDER BY t.created_at DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _parse_outcome(m: dict) -> float | None:
    """Extract resolution result from a Gamma market dict. Returns 1.0/0.0/0.5/None."""
    closed = m.get("closed", False)
    active = m.get("active", True)

    outcome_prices_raw = m.get("outcomePrices", "")
    if outcome_prices_raw:
        try:
            prices = json.loads(outcome_prices_raw) if isinstance(outcome_prices_raw, str) else outcome_prices_raw
            if len(prices) >= 2:
                yes_price = float(prices[0])
                no_price  = float(prices[1])
                if yes_price >= 0.95:
                    return 1.0
                elif no_price >= 0.95:
                    return 0.0
                elif closed and 0.40 <= yes_price <= 0.60:
                    return 0.5
        except (json.JSONDecodeError, ValueError):
            pass

    res_price = m.get("resolutionPrice")
    if res_price is not None:
        try:
            rp = float(res_price)
            if rp >= 0.95:   return 1.0
            elif rp <= 0.05: return 0.0
            else:            return 0.5
        except (ValueError, TypeError):
            pass

    if closed and not active:
        return 0.5
    return None


# Module-level cache: conditionId → outcome (populated by bulk fetch)
_resolution_cache: dict[str, float] = {}
_cache_fetched_at: float = 0.0
_CACHE_TTL = 300  # refresh every 5 min


def _refresh_resolution_cache(condition_ids: list[str]) -> None:
    """
    Fetch recently-closed markets in bulk and populate _resolution_cache.
    The Gamma API conditionId filter is broken — so we fetch closed markets
    by volume and match locally.
    """
    global _resolution_cache, _cache_fetched_at
    import time as _time

    now = _time.time()
    if now - _cache_fetched_at < _CACHE_TTL:
        return  # still fresh

    fetched: dict[str, float] = {}
    # Fetch last 500 closed markets
    for offset in range(0, 1000, 100):
        try:
            resp = httpx.get(
                f"{GAMMA_API}/markets",
                params={
                    "closed": "true",
                    "limit": 100,
                    "offset": offset,
                    "order": "updatedAt",
                    "ascending": "false",
                },
                timeout=15,
            )
            data = resp.json()
            items = data if isinstance(data, list) else data.get("data", [])
            if not items:
                break
            for m in items:
                cid = m.get("conditionId", "")
                if not cid:
                    continue
                result = _parse_outcome(m)
                if result is not None:
                    fetched[cid] = result
            # Stop early if we have all our condition_ids
            if all(cid in fetched for cid in condition_ids):
                break
        except Exception as e:
            log.warning(f"[resolver] bulk fetch error (offset={offset}): {e}")
            break

    _resolution_cache.update(fetched)
    _cache_fetched_at = now
    print(f"[resolver] cache refreshed: {len(fetched)} closed markets fetched, "
          f"{sum(1 for c in condition_ids if c in fetched)} of our trades matched")


def check_market_resolution(condition_id: str) -> float | None:
    """
    Check if a market has resolved. Uses bulk-fetch cache since
    the Gamma API conditionId filter doesn't work reliably.
    Returns 1.0 (YES), 0.0 (NO), 0.5 (push), or None (still open).
    """
    if not condition_id:
        return None
    return _resolution_cache.get(condition_id, None)


def resolve_trade(trade_id: int, market_result: float, side: str, amount_usd: float):
    """Mark a trade as resolved in the DB."""
    won = (side == "YES" and market_result == 1.0) or \
          (side == "NO" and market_result == 0.0)
    push = market_result == 0.5

    if push:
        pnl = 0.0
        result_str = "push"
    elif won:
        pnl = round(amount_usd * 0.9, 4)  # ~90c per dollar (10% Polymarket fee approx)
        result_str = "win"
    else:
        pnl = round(-amount_usd, 4)
        result_str = "loss"

    now = datetime.now(timezone.utc).isoformat()
    conn = _conn()
    conn.execute("""
        INSERT OR IGNORE INTO outcomes (trade_id, resolved_at, result, pnl)
        VALUES (?, ?, ?, ?)
    """, (trade_id, now, result_str, pnl))
    conn.execute("""
        INSERT OR REPLACE INTO calibration
          (trade_id, classification, materiality, entry_price, exit_price,
           actual_direction, correct, resolved_at)
        SELECT id, side, edge, market_price, ?,
               CASE WHEN ? = 1.0 THEN 'YES' ELSE 'NO' END,
               CASE WHEN ? THEN 1 ELSE 0 END,
               ?
        FROM trades WHERE id = ?
    """, (market_result, market_result, 1 if (won and not push) else 0, now, trade_id))
    conn.commit()
    conn.close()
    return result_str, pnl


def run_resolution_check(verbose: bool = True) -> dict:
    """
    Check all pending demo trades for resolution.
    Returns summary dict with counts.
    """
    pending = get_pending_demo_trades()

    if not pending:
        if verbose:
            print("[resolver] No pending demo trades to resolve.")
        return {"checked": 0, "resolved": 0, "wins": 0, "losses": 0, "pushes": 0}

    if verbose:
        print(f"[resolver] Checking {len(pending)} pending demo trades...")

    # Bulk-fetch closed markets and populate cache
    condition_ids = [t["market_id"] for t in pending if t.get("market_id")]
    _refresh_resolution_cache(condition_ids)

    resolved = wins = losses = pushes = 0

    for trade in pending:
        market_result = check_market_resolution(trade["market_id"])
        if verbose:
            print(
                f"[resolver] #{trade['id']} result={market_result} "
                f"q=\"{trade['market_question'][:45]}\""
            )

        if market_result is None:
            continue  # still open

        result_str, pnl = resolve_trade(
            trade_id=trade["id"],
            market_result=market_result,
            side=trade["side"],
            amount_usd=trade["amount_usd"],
        )
        resolved += 1

        if result_str == "win":
            wins += 1
            symbol = "✅"
        elif result_str == "loss":
            losses += 1
            symbol = "❌"
        else:
            pushes += 1
            symbol = "↩️"

        if verbose:
            print(
                f"  {symbol} Trade #{trade['id']} | {result_str.upper()} | "
                f"{trade['side']} on \"{trade['market_question'][:50]}\" | "
                f"PnL: ${pnl:+.2f}"
            )

    if verbose and resolved > 0:
        print(f"[resolver] Resolved {resolved} trades: {wins}W {losses}L {pushes}P")

    return {
        "checked": len(pending),
        "resolved": resolved,
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
    }


def get_accuracy_stats() -> dict:
    """Calculate overall accuracy from resolved demo trades."""
    conn = _conn()
    # Total trades logged (pending + resolved)
    logged_row = conn.execute(
        "SELECT COUNT(*) as total FROM trades WHERE status IN ('demo','dry_run')"
    ).fetchone()
    row = conn.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN o.result = 'win' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN o.result = 'loss' THEN 1 ELSE 0 END) as losses,
            SUM(CASE WHEN o.result = 'push' THEN 1 ELSE 0 END) as pushes,
            COALESCE(SUM(o.pnl), 0) as total_pnl
        FROM trades t
        JOIN outcomes o ON t.id = o.trade_id
        WHERE t.status IN ('demo', 'dry_run')
    """).fetchone()
    conn.close()

    total = row["total"] or 0
    wins = row["wins"] or 0
    losses = row["losses"] or 0
    pushes = row["pushes"] or 0
    total_pnl = row["total_pnl"] or 0.0

    decisive = total - pushes
    accuracy = round(wins / decisive * 100, 1) if decisive > 0 else 0.0

    return {
        "total_logged": logged_row["total"] or 0,
        "total_resolved": total,
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "accuracy_pct": accuracy,
        "total_pnl": round(total_pnl, 2),
        "ready_for_live": accuracy >= 70.0 and decisive >= 10,
    }


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    result = run_resolution_check(verbose=True)
    print(f"\nResolution check complete: {result}")
    stats = get_accuracy_stats()
    print(f"\nAccuracy stats: {stats}")
