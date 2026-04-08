"""
Edge detection and position sizing.
V3: Multi-signal RRF scoring (inspired by SkillX reciprocal rank fusion)
+ conservative sizing for small bankrolls.
"""
from __future__ import annotations

from dataclasses import dataclass

import config
from markets import Market
from classifier import Classification
from news_stream import NewsEvent


@dataclass
class Signal:
    market: Market
    claude_score: float
    market_price: float
    edge: float
    side: str  # "YES" or "NO"
    bet_amount: float
    reasoning: str
    headlines: str
    # V2 fields
    news_source: str = ""
    classification: str = ""
    materiality: float = 0.0
    news_latency_ms: int = 0
    classification_latency_ms: int = 0
    total_latency_ms: int = 0
    # V3 fields
    composite_score: float = 0.0
    consensus_agreed: bool = True


def detect_edge(
    market: Market,
    claude_score: float,
    reasoning: str = "",
    headlines: str = "",
) -> Signal | None:
    """V1: Compare Claude's confidence against market price."""
    market_price = market.yes_price
    edge = claude_score - market_price

    if abs(edge) < config.EDGE_THRESHOLD:
        return None

    if edge > 0:
        side = "YES"
        raw_edge = edge
    else:
        side = "NO"
        raw_edge = abs(edge)

    bet_amount = size_position(raw_edge)

    return Signal(
        market=market,
        claude_score=claude_score,
        market_price=market_price,
        edge=raw_edge,
        side=side,
        bet_amount=bet_amount,
        reasoning=reasoning,
        headlines=headlines,
    )


def detect_edge_v2(
    market: Market,
    classification: Classification,
    news_event: NewsEvent,
) -> Signal | None:
    """
    V2/V3: Use classification direction + materiality + multi-signal composite.
    Only generates a signal when:
    - Direction is bullish or bearish (not neutral)
    - Consensus agreed (if enabled)
    - Materiality exceeds threshold
    - Composite score exceeds threshold
    - Market price has room to move in the predicted direction
    """
    if classification.direction == "neutral":
        return None

    # V3: Require consensus agreement
    if config.CONSENSUS_ENABLED and not classification.consensus_agreed:
        return None

    if classification.materiality < config.MATERIALITY_THRESHOLD:
        return None

    market_price = market.yes_price

    if classification.direction == "bullish":
        side = "YES"
        if market_price > 0.85:
            return None
        raw_edge = classification.materiality * (1.0 - market_price)
        price_room = 1.0 - market_price
    else:  # bearish
        side = "NO"
        if market_price < 0.15:
            return None
        raw_edge = classification.materiality * market_price
        price_room = market_price

    if raw_edge < config.EDGE_THRESHOLD:
        return None

    # V3: Multi-signal composite score (RRF-inspired weighted fusion)
    composite = compute_composite_score(
        classification=classification,
        market=market,
        news_event=news_event,
        price_room=price_room,
    )

    # Only trade on high-composite signals
    if composite < 0.4:
        return None

    # Use composite to scale position size — higher composite = more confidence
    bet_amount = size_position(raw_edge, composite_boost=composite)
    total_latency = news_event.latency_ms + classification.latency_ms

    return Signal(
        market=market,
        claude_score=classification.materiality,
        market_price=market_price,
        edge=raw_edge,
        side=side,
        bet_amount=bet_amount,
        reasoning=classification.reasoning,
        headlines=news_event.headline,
        news_source=news_event.source,
        classification=classification.direction,
        materiality=classification.materiality,
        news_latency_ms=news_event.latency_ms,
        classification_latency_ms=classification.latency_ms,
        total_latency_ms=total_latency,
        composite_score=composite,
        consensus_agreed=classification.consensus_agreed,
    )


def compute_composite_score(
    classification: Classification,
    market: Market,
    news_event: NewsEvent,
    price_room: float,
) -> float:
    """
    RRF-inspired multi-signal composite score.
    Combines multiple independent signals into a single confidence metric.
    Each signal is normalized 0-1, then weighted per config.SIGNAL_WEIGHTS.
    """
    weights = config.SIGNAL_WEIGHTS
    score = 0.0

    # 1. Classification strength (materiality as proxy)
    score += weights["classification"] * classification.materiality

    # 2. Materiality signal (bonus for high materiality)
    mat_signal = min(classification.materiality / 0.8, 1.0)  # normalize: 0.8+ = max
    score += weights["materiality"] * mat_signal

    # 3. Price room — more room to move = better opportunity
    room_signal = min(price_room / 0.5, 1.0)  # normalize: 0.5+ room = max
    score += weights["price_room"] * room_signal

    # 4. Niche market bonus — lower volume = less competition
    if market.volume <= 50000:
        niche_signal = 1.0
    elif market.volume <= 200000:
        niche_signal = 0.7
    elif market.volume <= config.MAX_VOLUME_USD:
        niche_signal = 0.4
    else:
        niche_signal = 0.1
    score += weights["volume_niche"] * niche_signal

    # 5. News recency — fresher = better edge before market absorbs
    age_seconds = news_event.age_seconds() if hasattr(news_event, 'age_seconds') else 60
    if age_seconds < 30:
        recency_signal = 1.0
    elif age_seconds < 120:
        recency_signal = 0.8
    elif age_seconds < 300:
        recency_signal = 0.5
    else:
        recency_signal = 0.2
    score += weights["recency"] * recency_signal

    return round(score, 4)


def size_position(edge: float, composite_boost: float = 0.5) -> float:
    """
    Quarter-Kelly position sizing, tuned for small bankrolls.
    Uses actual bankroll from config. Composite score scales size up/down.
    Capped at MAX_BET_USD.
    """
    # Quarter-Kelly: fraction = edge * 0.25
    fraction = edge * 0.25

    # Scale by composite confidence (0.4 to 1.0 range mapped to 0.5x-1.5x)
    confidence_multiplier = 0.5 + composite_boost
    fraction *= confidence_multiplier

    # Use actual bankroll for sizing
    bankroll = config.BANKROLL_USD
    raw_size = bankroll * fraction

    # Minimum $0.50 bet (Polymarket minimum), max per config
    return min(max(round(raw_size, 2), 0.50), config.MAX_BET_USD)
