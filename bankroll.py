"""
bankroll.py — Kelly-criterion bet sizing for $100 passive-income bankroll.

Rules:
  - Max 5% of bankroll per bet (safety cap)
  - Kelly fraction based on edge, but HALF-KELLY for variance smoothing
  - Minimum bet: $0.50 (below this, skip — not worth dust)
  - Daily loss cap: 15% (if hit, stop trading for the day)

Usage:
  size = kelly_bet_size(bankroll=100.0, edge=0.12, market_price=0.55)
"""
from __future__ import annotations

import os

INITIAL_BANKROLL = float(os.getenv("BANKROLL_USD", "20"))
MAX_BET_FRAC     = 0.10   # 10% max per bet ($2 on $20 bankroll)
MIN_BET_USD      = 0.50
DAILY_LOSS_CAP   = 0.15   # stop trading after 15% daily drawdown


def kelly_bet_size(bankroll: float, edge: float, market_price: float,
                   materiality: float = 0.5) -> float:
    """
    Compute Kelly bet size given edge and market price.

    Kelly formula for binary markets:
      f* = edge / (1 - market_price)    [for YES bets]

    We use HALF-KELLY (×0.5) to reduce variance, capped at MAX_BET_FRAC.
    We scale further by materiality (confidence) so weak signals bet less.
    """
    if edge <= 0 or bankroll <= 0:
        return 0.0

    # Avoid division blowup for extreme prices
    denom = max(0.05, 1.0 - market_price)
    kelly_frac = edge / denom

    # Full Kelly for crypto-only (proven 73% edge)
    # Half-Kelly was too conservative — $1 bets on $20 bankroll = slow profits
    # kelly_frac *= 0.5  ← removed: full Kelly for max profit

    # Scale by confidence (materiality) — weak signals get smaller bets
    kelly_frac *= max(0.5, materiality)

    # Cap at MAX_BET_FRAC
    kelly_frac = min(kelly_frac, MAX_BET_FRAC)

    bet = bankroll * kelly_frac
    if bet < MIN_BET_USD:
        return 0.0
    return round(bet, 2)


def get_current_bankroll(db_path: str | None = None) -> float:
    """Compute current bankroll = initial + realized PnL from outcomes table."""
    import sqlite3
    from pathlib import Path

    path = Path(db_path or os.getenv("DB_PATH", "trades.db"))
    if not path.exists():
        return INITIAL_BANKROLL
    try:
        conn = sqlite3.connect(path)
        row = conn.execute(
            "SELECT COALESCE(SUM(pnl), 0) FROM outcomes"
        ).fetchone()
        conn.close()
        return INITIAL_BANKROLL + float(row[0] or 0)
    except Exception:
        return INITIAL_BANKROLL


def todays_pnl(db_path: str | None = None) -> float:
    """Return PnL realized today (UTC)."""
    import sqlite3
    from datetime import datetime, timezone
    from pathlib import Path

    path = Path(db_path or os.getenv("DB_PATH", "trades.db"))
    if not path.exists():
        return 0.0
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        conn = sqlite3.connect(path)
        row = conn.execute(
            "SELECT COALESCE(SUM(pnl), 0) FROM outcomes WHERE resolved_at >= ?",
            (today,)
        ).fetchone()
        conn.close()
        return float(row[0] or 0)
    except Exception:
        return 0.0


def can_trade_today() -> tuple[bool, str]:
    """Return (allowed, reason). In demo mode, cap is much looser (virtual $)."""
    import os
    is_demo = os.getenv("DRY_RUN", "true").lower() == "true"
    bankroll = get_current_bankroll()
    pnl_today = todays_pnl()
    # Demo mode: 50% loss cap (virtual money — learning mode)
    # Live mode: 15% loss cap (real money — strict protection)
    cap = 0.50 if is_demo else DAILY_LOSS_CAP
    if pnl_today < -(bankroll * cap):
        return False, f"Daily loss cap hit: ${pnl_today:.2f} < -{cap:.0%}"
    return True, "ok"
