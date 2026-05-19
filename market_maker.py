"""
Market maker module — places limit orders on both sides of thin markets
to earn the bid-ask spread. Modeled after Brody's "liquidity providing" approach.

Key insight: thin markets with wide spreads = easy money if you can provide liquidity.
Places YES bids below midpoint and NO bids below midpoint, earning spread on fills.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx

import config
import orderbook
import bankroll

log = logging.getLogger(__name__)


@dataclass
class MarketMakingOpportunity:
    """A market making opportunity."""
    market_question: str
    token_id: str
    best_bid: float
    best_ask: float
    spread: float
    spread_pct: float
    recommended_bid: float
    recommended_ask: float
    estimated_profit_per_fill: float
    volume_24h: float
    liquidity: float
    risk_score: float  # 0-1, higher = riskier


MIN_SPREAD_PCT = 0.03  # Minimum 3% spread to bother
MAX_SPREAD_PCT = 0.20  # Too wide = illiquid, skip
MIN_VOLUME_FOR_MM = 1000  # Minimum $1000 daily volume
MAX_POSITION_PER_MARKET = 50  # Max $50 per market for MM


def analyze_spread(token_id: str, market_question: str = "") -> MarketMakingOpportunity | None:
    """
    Analyze orderbook spread for market making potential.
    Returns opportunity if spread is wide enough to profit.
    """
    try:
        book = orderbook.get_book(token_id)
        if not book:
            return None

        bids = book.get("bids", [])
        asks = book.get("asks", [])

        if not bids or not asks:
            return None

        best_bid = float(bids[0].get("price", 0))
        best_ask = float(asks[0].get("price", 0))

        if best_bid <= 0 or best_ask <= 0 or best_ask <= best_bid:
            return None

        spread = best_ask - best_bid
        mid = (best_bid + best_ask) / 2
        spread_pct = spread / mid if mid > 0 else 0

        if spread_pct < MIN_SPREAD_PCT or spread_pct > MAX_SPREAD_PCT:
            return None

        # Place bid slightly above current best bid
        recommended_bid = best_bid + 0.005
        # Place ask slightly below current best ask
        recommended_ask = best_ask - 0.005

        # Profit per fill = spread minus our improvement
        profit_per_fill = (recommended_ask - recommended_bid) * 0.9  # 90% of theoretical

        # Risk score: wider spread in illiquid market = higher risk
        bid_depth = sum(float(b.get("size", 0)) for b in bids[:5])
        ask_depth = sum(float(a.get("size", 0)) for a in asks[:5])
        risk = 0.3
        if bid_depth < 100 or ask_depth < 100:
            risk += 0.3
        if spread_pct > 0.10:
            risk += 0.2

        return MarketMakingOpportunity(
            market_question=market_question,
            token_id=token_id,
            best_bid=best_bid,
            best_ask=best_ask,
            spread=spread,
            spread_pct=spread_pct,
            recommended_bid=recommended_bid,
            recommended_ask=recommended_ask,
            estimated_profit_per_fill=profit_per_fill,
            volume_24h=0,  # Would need volume data
            liquidity=bid_depth + ask_depth,
            risk_score=min(1.0, risk),
        )
    except Exception as e:
        log.debug(f"[market_maker] Spread analysis failed: {e}")
        return None


def find_mm_opportunities(markets: list, min_spread_pct: float = MIN_SPREAD_PCT) -> list[MarketMakingOpportunity]:
    """
    Scan markets for market making opportunities.
    Returns list of opportunities sorted by spread (widest first).
    """
    opportunities = []
    for m in markets:
        token_id = getattr(m, 'token_yes_id', None) or getattr(m, 'id', None)
        question = getattr(m, 'question', '')
        if not token_id:
            continue

        opp = analyze_spread(str(token_id), question)
        if opp and opp.spread_pct >= min_spread_pct:
            opportunities.append(opp)

    opportunities.sort(key=lambda o: o.spread, reverse=True)
    return opportunities


def size_mm_order(opp: MarketMakingOpportunity, bankroll_usd: float) -> float:
    """Calculate appropriate order size for market making."""
    # Risk 2-5% of bankroll per market making position
    max_position = bankroll_usd * 0.03
    max_position = min(max_position, MAX_POSITION_PER_MARKET)

    # Reduce size if risk is high
    if opp.risk_score > 0.6:
        max_position *= 0.5

    return round(max_position, 2)


# ─── Database & Dashboard Integration ──────────────────────────────────────────
import sqlite3
from datetime import datetime, timezone

from config import DB_PATH


def _init_maker_table():
    """Create market_maker tables if they don't exist."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS maker_cycles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL DEFAULT (datetime('now')),
            markets_scanned INTEGER DEFAULT 0,
            opportunities_found INTEGER DEFAULT 0,
            orders_placed INTEGER DEFAULT 0,
            total_spread REAL DEFAULT 0,
            details TEXT DEFAULT ''
        )
    """)
    conn.commit()
    conn.close()


def get_maker_stats() -> dict:
    """Get market maker statistics for the dashboard."""
    _init_maker_table()
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute("""
            SELECT markets_scanned, opportunities_found, orders_placed, total_spread, ts
            FROM maker_cycles ORDER BY id DESC LIMIT 1
        """).fetchone()
        total_cycles = conn.execute("SELECT COUNT(*) FROM maker_cycles").fetchone()[0]
        total_opps = conn.execute("SELECT COALESCE(SUM(opportunities_found),0) FROM maker_cycles").fetchone()[0]
        total_orders = conn.execute("SELECT COALESCE(SUM(orders_placed),0) FROM maker_cycles").fetchone()[0]
    except Exception:
        row = None
        total_cycles = total_opps = total_orders = 0
    finally:
        conn.close()

    return {
        "last_scan": {
            "markets_scanned": row[0] if row else 0,
            "opportunities": row[1] if row else 0,
            "orders_placed": row[2] if row else 0,
            "avg_spread": round(row[3], 4) if row and row[3] else 0,
            "time": row[4] if row else None,
        },
        "total_cycles": total_cycles,
        "total_opportunities": total_opps,
        "total_orders": total_orders,
    }


def run_maker_cycle(markets: list = None) -> dict:
    """
    Run one market-making scan cycle.
    Fetches markets, analyzes spreads, logs results.
    Returns summary dict for dashboard.
    """
    _init_maker_table()

    # Fetch markets if not provided
    if not markets:
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.get(
                    "https://gamma-api.polymarket.com/markets",
                    params={
                        "limit": 100,
                        "active": "true",
                        "closed": "false",
                        "order": "volume24hr",
                        "ascending": "false",
                    }
                )
                resp.raise_for_status()
                raw = resp.json()
                markets = raw if isinstance(raw, list) else raw.get("data", raw.get("markets", []))
        except Exception as e:
            log.warning(f"[market_maker] Failed to fetch markets: {e}")
            return {"error": str(e)}

    # Build token_id -> market mapping
    token_markets = []
    for m in markets:
        cid = m.get("conditionId", m.get("condition_id", ""))
        question = m.get("question", m.get("title", ""))
        tokens = m.get("clobTokenIds", "")
        if isinstance(tokens, str):
            tokens = [t.strip() for t in tokens.split(",") if t.strip()] if tokens else []
        elif not isinstance(tokens, list):
            tokens = []
        for tid in tokens:
            token_markets.append((tid, question))

    # Analyze spreads
    opportunities = []
    total_spread = 0.0
    for tid, question in token_markets:
        opp = analyze_spread(tid, question)
        if opp and opp.spread_pct >= MIN_SPREAD_PCT:
            opportunities.append(opp)
            total_spread += opp.spread_pct

    opportunities.sort(key=lambda o: o.spread, reverse=True)
    top = opportunities[:10]

    # Log cycle to DB
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO maker_cycles (markets_scanned, opportunities_found, orders_placed, total_spread, details)
        VALUES (?, ?, ?, ?, ?)
    """, (
        len(markets),
        len(opportunities),
        0,  # We don't auto-place orders yet — just scanning
        round(total_spread, 4),
        str([{"question": o.market_question, "spread": round(o.spread_pct, 4), "bid": o.recommended_bid} for o in top[:5]])
    ))
    conn.commit()
    conn.close()

    log.info(f"[market_maker] Cycle complete: {len(markets)} markets, "
             f"{len(opportunities)} opportunities found")

    return {
        "markets_scanned": len(markets),
        "tokens_checked": len(token_markets),
        "opportunities_found": len(opportunities),
        "avg_spread": round(total_spread / len(opportunities), 4) if opportunities else 0,
        "top_opportunities": [
            {
                "question": o.market_question,
                "spread_pct": round(o.spread_pct * 100, 2),
                "best_bid": o.best_bid,
                "best_ask": o.best_ask,
                "recommended_bid": o.recommended_bid,
                "risk_score": round(o.risk_score, 2),
            }
            for o in top
        ],
    }
