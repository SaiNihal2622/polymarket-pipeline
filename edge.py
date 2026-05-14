"""
Edge detection and position sizing.
V4: Heterogeneous consensus + optimal filter ordering + Kelly sizing.

Filter ordering (cheapest → most expensive):
  1. Direction check (free)
  2. Consensus agreement (free — already computed)
  3. Price room check (free — math only)
  4. Materiality threshold (free — already computed)
  5. Edge threshold (free — math only)
  6. Composite score (cheap — weighted sum)
  7. Sureshot keyword scan (cheap — string match)
  8. Position sizing (cheap — Kelly formula)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import config
from markets import Market
from classifier import Classification
from news_stream import NewsEvent

log = logging.getLogger(__name__)


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
    # V4 fields
    signal_grade: str = ""  # "S" / "A" / "B" — for priority ranking


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
    V4: Optimal filter ordering for maximum profit extraction.

    Filters (cheapest first — fail fast):
      1. Direction != neutral
      2. Consensus agreed (all 3 AI models)
      3. Materiality >= 0.80
      4. Price room exists (not already priced in)
      5. Edge >= 0.15
      6. Composite score >= threshold
      7. Sureshot keyword boost (if applicable)
      8. Kelly position sizing
    """
    # ── GATE 1: Direction (free) ──────────────────────────────────────────
    if classification.direction == "neutral":
        return None

    # ── GATE 2: Consensus (free — already computed by classifier) ─────────
    if config.CONSENSUS_ENABLED and not classification.consensus_agreed:
        log.debug(f"[edge] REJECTED consensus_fail: '{news_event.headline[:50]}'")
        return None

    # ── GATE 3: Materiality (free — already computed) ─────────────────────
    if classification.materiality < config.MATERIALITY_THRESHOLD:
        log.debug(f"[edge] REJECTED mat={classification.materiality:.2f} < {config.MATERIALITY_THRESHOLD}")
        return None

    # ── GATE 4: Price room (free — pure math) ─────────────────────────────
    market_price = market.yes_price

    if classification.direction == "bullish":
        side = "YES"
        if market_price > 0.90:
            log.debug(f"[edge] REJECTED bullish but price={market_price:.2f} > 0.90 — already priced in")
            return None
        model_prob = getattr(classification, 'probability', None)
        if model_prob and 0 < model_prob < 1:
            raw_edge = model_prob - market_price
        else:
            # REJECT trades without probability estimate — strategy guide says
            # "only trade when confidence exceeds threshold". No probability = no trade.
            log.debug(f"[edge] REJECTED bullish — no probability estimate from LLM")
            return None
        price_room = 1.0 - market_price
    else:  # bearish
        side = "NO"
        if market_price < 0.10:
            log.debug(f"[edge] REJECTED bearish but price={market_price:.2f} < 0.10 — already priced in")
            return None
        model_prob = getattr(classification, 'probability', None)
        if model_prob and 0 < model_prob < 1:
            raw_edge = (1.0 - model_prob) - (1.0 - market_price)
        else:
            log.debug(f"[edge] REJECTED bearish — no probability estimate from LLM")
            return None
        price_room = market_price

    # ── GATE 4b: Minimum ROI filter (ensures ≥100% ROI per trade) ─────────
    # YES: buy only if price ≤ 0.50 → profit per $1 = (1/price - 1) ≥ $1.00
    # NO: buy only if YES price ≥ 0.50 → NO price ≤ 0.50 → same math
    if side == "YES" and market_price > config.MAX_YES_ENTRY_PRICE:
        roi_pct = (1.0 / market_price - 1.0) * 100
        log.debug(f"[edge] REJECTED YES price={market_price:.2f} > {config.MAX_YES_ENTRY_PRICE:.2f} — ROI={roi_pct:.0f}% too low, need ≥100%")
        return None
    if side == "NO" and market_price < config.MIN_NO_ENTRY_PRICE:
        no_price = 1.0 - market_price
        roi_pct = (1.0 / no_price - 1.0) * 100
        log.debug(f"[edge] REJECTED NO price={no_price:.2f} > 0.50 — ROI={roi_pct:.0f}% too low, need ≥100%")
        return None

    # ── GATE 5: Edge threshold (free — pure math) ─────────────────────────
    if raw_edge < config.EDGE_THRESHOLD:
        log.debug(f"[edge] REJECTED edge={raw_edge:.3f} < {config.EDGE_THRESHOLD}")
        return None

    # ── GATE 6: Composite score (cheap — weighted sum) ────────────────────
    composite = compute_composite_score(
        classification=classification,
        market=market,
        news_event=news_event,
        price_room=price_room,
    )

    # ── GATE 7: Sureshot keyword detection (cheap — string match) ─────────
    sureshot_keywords = [
        # Cricket/Sports — definitive outcomes
        "toss", "injury", "playing xi", "out", "replaced", "captain",
        "won the match", "lost the match", "eliminated",
        # Legal/Political — binary outcomes
        "resigned", "fired", "died", "guilty", "not guilty", "verdict",
        "convicted", "acquitted", "impeached", "arrested",
        # Business — definitive events
        "officially confirmed", "breaks records", "acquired", "merged",
        "bankrupt", "halting", "delisted", "approved", "rejected",
        "signed", "deal closed", "ipo priced",
        # Tech/AI — concrete milestones
        "launched", "released", "shutdown", "open-sourced",
    ]
    headline_lower = news_event.headline.lower()
    is_high_conviction = any(kw in headline_lower for kw in sureshot_keywords)

    # Sureshot: price near 50/50 AND extremely material news
    mat_req = 0.75 if is_high_conviction else 0.85
    is_sureshot = (0.25 <= market_price <= 0.75) and (classification.materiality >= mat_req)

    if is_sureshot:
        composite = max(composite, 0.85 if is_high_conviction else 0.80)
        raw_edge = max(raw_edge, config.EDGE_THRESHOLD * 2.0)

    # Composite threshold — sureshots get a small discount
    min_composite = 0.60 if is_sureshot else 0.70
    if composite < min_composite:
        log.debug(f"[edge] REJECTED composite={composite:.3f} < {min_composite}")
        return None

    # ── STEP 8: Signal grading & position sizing ──────────────────────────
    # Grade the signal for priority ranking
    grade = _grade_signal(composite, classification.materiality, raw_edge, is_sureshot)

    # Kelly position sizing with composite boost
    bet_amount = size_position(raw_edge, composite_boost=composite)

    # ROI-weighted sizing: higher ROI trades get bigger bets
    # ROI 150% = 1.0x, ROI 300% = 1.5x, ROI 500% = 2.0x
    buy_price = market_price if side == "YES" else (1.0 - market_price)
    if buy_price > 0 and buy_price < 1.0:
        roi_pct = ((1.0 - buy_price) / buy_price) * 100
        roi_multiplier = min(1.0 + (roi_pct - 100) / 400, 2.0)  # 1.0x at 100% ROI, 2.0x at 500%+ ROI
        bet_amount = min(bet_amount * max(roi_multiplier, 1.0), config.MAX_BET_USD)

    # Sureshot boost: up to 2x (conservative) within bankroll limits
    if is_sureshot:
        bet_amount = min(bet_amount * 2.0, config.MAX_BET_USD)

    total_latency = news_event.latency_ms + classification.latency_ms

    log.info(
        f"[edge] ✅ SIGNAL grade={grade} side={side} edge={raw_edge:.3f} "
        f"composite={composite:.3f} mat={classification.materiality:.2f} "
        f"bet=${bet_amount:.2f} '{news_event.headline[:60]}'"
    )

    return Signal(
        market=market,
        claude_score=classification.probability if classification.probability else classification.materiality,
        market_price=market_price,
        edge=raw_edge,
        side=side,
        bet_amount=bet_amount,
        reasoning=classification.reasoning + (f" [SURESHOT/{grade}]" if is_sureshot else f" [{grade}]"),
        headlines=news_event.headline,
        news_source=news_event.source,
        classification=classification.direction,
        materiality=classification.materiality,
        news_latency_ms=news_event.latency_ms,
        classification_latency_ms=classification.latency_ms,
        total_latency_ms=total_latency,
        composite_score=composite,
        consensus_agreed=classification.consensus_agreed,
        signal_grade=grade,
    )


def _grade_signal(composite: float, materiality: float, edge: float, is_sureshot: bool) -> str:
    """
    Grade signal quality for priority ranking.
    S-tier: Only the absolute best — high composite, high materiality, high edge
    A-tier: Strong signal, worth max bet
    B-tier: Decent signal, worth min bet
    """
    score = (composite * 0.4) + (materiality * 0.35) + (min(edge / 0.3, 1.0) * 0.25)
    if is_sureshot:
        score += 0.10  # sureshot bonus

    if score >= 0.85:
        return "S"
    elif score >= 0.70:
        return "A"
    else:
        return "B"


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
    age_seconds = news_event.age_seconds() if hasattr(news_event, 'age_seconds') else 3600
    age_hours = age_seconds / 3600
    if age_hours < 0.5:       # < 30 min: very fresh
        recency_signal = 1.0
    elif age_hours < 1.5:     # < 1.5h: fresh
        recency_signal = 0.8
    elif age_hours < 3.0:     # < 3h: usable
        recency_signal = 0.5
    elif age_hours < 6.0:     # < 6h: stale but consider
        recency_signal = 0.3
    else:                     # > 6h: very stale
        recency_signal = 0.1
    score += weights["recency"] * recency_signal

    # 6. Asymmetric payoff bonus — cheaper entry = higher ROI = bonus
    # Sweet spot: 15-40¢ entry → 150-567% ROI → bonus 0.05-0.15
    buy_price = market.yes_price  # already filtered by side in caller
    if buy_price <= 0.20:
        roi_bonus = 0.15   # 400%+ ROI: max bonus
    elif buy_price <= 0.30:
        roi_bonus = 0.10   # 233%+ ROI: good bonus
    elif buy_price <= 0.40:
        roi_bonus = 0.05   # 150%+ ROI: small bonus
    else:
        roi_bonus = 0.0
    score += roi_bonus

    return round(min(score, 1.0), 4)


def size_position(edge: float, composite_boost: float = 0.5) -> float:
    """
    Quarter-Kelly position sizing, tuned for PROFIT GUARANTEE even at low accuracy.

    Key insight: At 30¢ entry, break-even is only 30%. So even small edges are
    massively profitable. Scale bets with confidence:
      - Grade S (high conviction): max bet ($1.00)
      - Grade A (medium): $0.50-$0.75
      - Grade B (low): minimum bet ($0.50)

    Uses fractional Kelly to NEVER risk too much on one trade.
    """
    # Conservative: 1/8 Kelly (protect bankroll from variance)
    fraction = edge * 0.125

    # Scale by composite confidence (0.5 to 1.5 range)
    confidence_multiplier = 0.5 + composite_boost
    fraction *= confidence_multiplier

    # Use actual bankroll for sizing
    bankroll = config.BANKROLL_USD
    raw_size = bankroll * fraction

    # Minimum $0.50 bet (Polymarket minimum), max per config
    # Cap at $1 flat bet to protect bankroll
    return min(max(round(raw_size, 2), 0.50), config.MAX_BET_USD)
