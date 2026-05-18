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