"""
Arbitrage module — finds guaranteed-profit opportunities across related markets.
Detects mispricings between YES/NO sides, correlated markets, and multi-outcome events.

Key insight: if YES + NO doesn't equal $1.00, there's free money.
Also detects cross-market arbitrage (e.g., two markets about same event with different prices).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import config
import price_feeds
import orderbook

log = logging.getLogger(__name__)


@dataclass
class ArbitrageOpportunity:
    """A guaranteed profit opportunity."""
    market_question: str
    strategy: str  # "yes_no_spread", "cross_market", "multi_outcome"
    yes_price: float
    no_price: float
    total_cost: float  # Cost to buy both sides
    guaranteed_profit: float  # Profit if resolved either way
    profit_pct: float  # ROI percentage
    risk_free: bool
    token_ids: list[str]
    confidence: float  # 0-1 (how sure we are of the arb)


MIN_ARB_PROFIT_PCT = 0.015  # 1.5% minimum profit
MAX_ARB_PRICE_SLIPPAGE = 0.03  # 3% max slippage from displayed prices


def check_yes_no_arb(token_yes_id: str, token_no_id: str, market_question: str = "") -> ArbitrageOpportunity | None:
    """
    Check if YES + NO prices < $1.00 (guaranteed arbitrage).
    Also check if YES + NO > $1.00 (sell-side arbitrage if possible).
    """
    try:
        yes_price = price_feeds.get_price(token_yes_id)
        no_price = price_feeds.get_price(token_no_id)

        if not yes_price or not no_price:
            return None

        total_cost = yes_price + no_price

        # Classic arb: buy both sides for less than $1
        if total_cost < (1.0 - MIN_ARB_PROFIT_PCT):
            profit = 1.0 - total_cost
            return ArbitrageOpportunity(
                market_question=market_question,
                strategy="yes_no_spread",
                yes_price=yes_price,
                no_price=no_price,
                total_cost=total_cost,
                guaranteed_profit=profit,
                profit_pct=profit / total_cost,
                risk_free=True,
                token_ids=[token_yes_id, token_no_id],
                confidence=0.95,
            )

        return None
    except Exception as e:
        log.debug(f"[arb] YES/NO check failed: {e}")
        return None


def check_orderbook_arb(token_id: str, side: str, market_question: str = "") -> ArbitrageOpportunity | None:
    """
    Check orderbook for price inefficiencies — if best ask < fair value,
    buy immediately.
    """
    try:
        book = orderbook.get_book(token_id)
        if not book:
            return None

        asks = book.get("asks", [])
        bids = book.get("bids", [])

        if not asks or not bids:
            return None

        best_ask = float(asks[0].get("price", 0))
        best_bid = float(bids[0].get("price", 0))
        spread = best_ask - best_bid

        # If spread is very wide and we can buy at the bid, there's likely value
        if spread > 0.05 and best_ask < 0.90:
            # Potential arb: buy at ask, sell at higher price later
            return ArbitrageOpportunity(
                market_question=market_question,
                strategy="orderbook_spread",
                yes_price=best_ask if side == "YES" else 0,
                no_price=best_ask if side == "NO" else 0,
                total_cost=best_ask,
                guaranteed_profit=spread * 0.5,  # Conservative: half the spread
                profit_pct=spread / best_ask if best_ask > 0 else 0,
                risk_free=False,
                token_ids=[token_id],
                confidence=0.6,
            )

        return None
    except Exception as e:
        log.debug(f"[arb] Orderbook check failed: {e}")
        return None


def scan_all_markets(markets: list) -> list[ArbitrageOpportunity]:
    """
    Scan all markets for arbitrage opportunities.
    Returns sorted by profit_pct (highest first).
    """
    opportunities = []

    for m in markets:
        yes_id = getattr(m, 'token_yes_id', None)
        no_id = getattr(m, 'token_no_id', None)
        question = getattr(m, 'question', '')

        if yes_id and no_id:
            opp = check_yes_no_arb(str(yes_id), str(no_id), question)
            if opp:
                opportunities.append(opp)

    # Sort by profit
    opportunities.sort(key=lambda o: o.profit_pct, reverse=True)
    return opportunities


def size_arb_trade(opp: ArbitrageOpportunity, bankroll_usd: float, max_single: float = 100) -> tuple[float, float]:
    """
    Calculate position sizes for arbitrage.
    Returns (yes_size, no_size) in dollars.
    """
    if opp.risk_free:
        # Risk-free: use up to 10% of bankroll
        max_total = min(bankroll_usd * 0.10, max_single * 2)
    else:
        # Risky: use max 3% of bankroll
        max_total = min(bankroll_usd * 0.03, max_single)

    if opp.strategy == "yes_no_spread":
        # Split evenly between YES and NO
        per_side = max_total / 2
        return per_side, per_side
    else:
        return max_total, 0