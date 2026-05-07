"""
Accuracy & Profit Optimizer — V5 enhancements.

Adds:
  1. Price momentum analysis (detect trends before entering)
  2. Contrarian signal detection (strong news, market hasn't moved)
  3. Full Kelly position sizing (maximize long-run profits)
  4. Market quality scoring (prefer clear-resolution markets)
  5. Adaptive thresholds (auto-tune based on recent accuracy)
  6. Liquidity spread check (avoid illiquid markets)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

import config

log = logging.getLogger(__name__)


# ============================================================
# Price Momentum Analysis
# ============================================================

@dataclass
class MomentumResult:
    """Result of price momentum analysis."""
    trend: str          # "up", "down", "flat"
    strength: float     # 0.0-1.0
    price_5m: float     # price 5 min ago
    price_now: float    # current price
    change_pct: float   # % change
    signal: str         # "momentum_aligned", "momentum_against", "neutral"


def analyze_momentum(price_history: list[dict], current_price: float, direction: str) -> MomentumResult:
    """
    Analyze price momentum from recent price history.
    
    Args:
        price_history: List of {"timestamp": ..., "price": ...} dicts
        current_price: Current YES price
        direction: Our classified direction ("bullish" or "bearish")
    
    Returns:
        MomentumResult with trend analysis
    """
    if not price_history or len(price_history) < 2:
        return MomentumResult(
            trend="flat", strength=0.0,
            price_5m=current_price, price_now=current_price,
            change_pct=0.0, signal="neutral"
        )
    
    # Get prices from different time windows
    prices = [p.get("price", p.get("p", current_price)) for p in price_history]
    prices = [float(p) for p in prices if p is not None]
    
    if len(prices) < 2:
        return MomentumResult(
            trend="flat", strength=0.0,
            price_5m=current_price, price_now=current_price,
            change_pct=0.0, signal="neutral"
        )
    
    # Recent price (last 5 data points ≈ 5 min)
    recent = prices[-min(5, len(prices)):]
    older = prices[:max(1, len(prices) - 5)]
    
    avg_recent = sum(recent) / len(recent)
    avg_older = sum(older) / len(older)
    
    change_pct = ((avg_recent - avg_older) / max(avg_older, 0.01)) * 100
    
    # Determine trend
    if abs(change_pct) < 0.5:
        trend = "flat"
        strength = 0.0
    elif change_pct > 0:
        trend = "up"
        strength = min(abs(change_pct) / 5.0, 1.0)  # 5% change = max strength
    else:
        trend = "down"
        strength = min(abs(change_pct) / 5.0, 1.0)
    
    # Check if momentum aligns with our direction
    if direction == "bullish":
        if trend == "up" and strength > 0.3:
            signal = "momentum_aligned"  # Price rising + we're bullish = confirmed
        elif trend == "down" and strength > 0.3:
            signal = "momentum_against"  # Price falling + we're bullish = contrarian
        else:
            signal = "neutral"
    elif direction == "bearish":
        if trend == "down" and strength > 0.3:
            signal = "momentum_aligned"  # Price falling + we're bearish = confirmed
        elif trend == "up" and strength > 0.3:
            signal = "momentum_against"  # Price rising + we're bearish = contrarian
        else:
            signal = "neutral"
    else:
        signal = "neutral"
    
    return MomentumResult(
        trend=trend,
        strength=strength,
        price_5m=avg_older,
        price_now=avg_recent,
        change_pct=change_pct,
        signal=signal,
    )


# ============================================================
# Contrarian Signal Detection
# ============================================================

@dataclass
class ContrarianResult:
    """Result of contrarian analysis."""
    is_contrarian: bool
    confidence: float   # 0.0-1.0
    reason: str


def detect_contrarian(
    materiality: float,
    market_price: float,
    direction: str,
    news_age_seconds: float,
    price_change_since_news: float = 0.0,
) -> ContrarianResult:
    """
    Detect contrarian opportunities: strong news but market hasn't moved yet.
    
    The best profits come from being FIRST to act on breaking news.
    If materiality is high but the market price hasn't moved, that's alpha.
    """
    # Only look at fresh news (< 30 min)
    if news_age_seconds > 1800:  # 30 min
        return ContrarianResult(is_contrarian=False, confidence=0.0, reason="news too old")
    
    # High materiality but small price movement = contrarian opportunity
    if materiality >= 0.80 and abs(price_change_since_news) < 0.03:
        # Very strong news, market hasn't reacted
        confidence = min(materiality * 1.2, 1.0)
        return ContrarianResult(
            is_contrarian=True,
            confidence=confidence,
            reason=f"STRONG news (mat={materiality:.2f}) but market moved only {price_change_since_news:.1%}"
        )
    
    if materiality >= 0.70 and abs(price_change_since_news) < 0.02:
        # Good news, no market reaction
        confidence = materiality * 0.9
        return ContrarianResult(
            is_contrarian=True,
            confidence=confidence,
            reason=f"Good news (mat={materiality:.2f}) with no market reaction"
        )
    
    # Check if market is moving AGAINST our direction (potential mispricing)
    if direction == "bullish" and market_price < 0.30 and materiality >= 0.75:
        return ContrarianResult(
            is_contrarian=True,
            confidence=0.85,
            reason=f"Very low price ({market_price:.0%}) for bullish signal with mat={materiality:.2f}"
        )
    
    if direction == "bearish" and market_price > 0.70 and materiality >= 0.75:
        return ContrarianResult(
            is_contrarian=True,
            confidence=0.85,
            reason=f"Very high price ({market_price:.0%}) for bearish signal with mat={materiality:.2f}"
        )
    
    return ContrarianResult(is_contrarian=False, confidence=0.0, reason="not contrarian")


# ============================================================
# Full Kelly Position Sizing
# ============================================================

def kelly_size(
    edge: float,
    odds: float,
    bankroll: float,
    fraction: float = 0.25,
    max_bet: float = None,
    min_bet: float = 0.50,
) -> float:
    """
    Kelly Criterion position sizing for maximum long-run growth.
    
    Args:
        edge: Our estimated edge (e.g., 0.15 = 15% edge)
        odds: Decimal odds from the market (e.g., 2.0 for 50/50)
        bankroll: Current bankroll in USD
        fraction: Kelly fraction (0.25 = quarter Kelly, conservative)
        max_bet: Maximum bet size
        min_bet: Minimum bet size
    
    Returns:
        Optimal bet size in USD
    """
    if max_bet is None:
        max_bet = config.MAX_BET_USD
    
    if edge <= 0 or odds <= 1.0:
        return min_bet
    
    # Kelly formula: f* = (bp - q) / b
    # where b = odds - 1, p = probability of winning, q = 1 - p
    b = odds - 1.0
    p = 0.5 + edge  # our estimated probability
    q = 1.0 - p
    
    kelly_f = (b * p - q) / b
    
    if kelly_f <= 0:
        return min_bet
    
    # Apply fraction (quarter Kelly for safety)
    bet = bankroll * kelly_f * fraction
    
    # Clamp
    return min(max(round(bet, 2), min_bet), max_bet)


# ============================================================
# Market Quality Scoring
# ============================================================

@dataclass
class MarketQuality:
    """Market quality assessment."""
    score: float        # 0.0-1.0
    resolution_clarity: float  # How clear is the resolution criteria
    liquidity_score: float     # Spread + volume quality
    time_score: float          # Time to resolution
    reason: str


def score_market_quality(
    question: str,
    volume: float,
    yes_price: float,
    end_date: str = "",
    spread: float = 0.0,
) -> MarketQuality:
    """
    Score market quality for trading suitability.
    Higher quality = more likely to resolve correctly + easier to trade.
    """
    score = 0.0
    reasons = []
    
    # 1. Resolution clarity (0-0.3)
    # Markets with clear YES/NO criteria are better
    clarity_keywords_high = [
        "will", "before", "after", "by", "reach", "exceed",
        "win", "lose", "score", "price", "above", "below",
    ]
    clarity_keywords_low = [
        "might", "could", "opinion", "think", "believe",
        "should", "would", "ever",
    ]
    
    q_lower = question.lower()
    high_count = sum(1 for kw in clarity_keywords_high if kw in q_lower)
    low_count = sum(1 for kw in clarity_keywords_low if kw in q_lower)
    
    clarity = min(0.3, (high_count * 0.05) - (low_count * 0.05))
    clarity = max(0.05, clarity)
    score += clarity
    
    # 2. Liquidity score (0-0.35)
    # Prefer moderate volume (not too low, not too high which means priced in)
    if volume < 100:
        liq = 0.05  # Too illiquid
        reasons.append("very illiquid")
    elif volume < 1000:
        liq = 0.15
    elif volume < 10000:
        liq = 0.25  # Sweet spot for niche markets
    elif volume < 100000:
        liq = 0.30  # Good liquidity
    elif volume < 500000:
        liq = 0.25  # Getting efficient
    else:
        liq = 0.15  # Very efficient, harder to find edge
        reasons.append("very efficient market")
    
    # Spread penalty
    if spread > 0.10:
        liq *= 0.5
        reasons.append("wide spread")
    elif spread > 0.05:
        liq *= 0.8
    
    score += liq
    
    # 3. Price room score (0-0.2)
    # Markets near 50/50 have most room to move
    price_dist_from_mid = abs(yes_price - 0.5)
    room = 0.2 * (1.0 - price_dist_from_mid * 2)  # 0.5 = max room
    room = max(0.0, room)
    score += room
    
    # 4. Time score (0.15)
    # Prefer markets resolving in 1-48 hours (not too soon, not too far)
    if end_date:
        try:
            from datetime import datetime
            end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            hours_to_resolution = (end - datetime.now(end.tzinfo)).total_seconds() / 3600
            
            if hours_to_resolution < 0.5:
                time_s = 0.05  # Too soon, already priced in
                reasons.append("closing too soon")
            elif hours_to_resolution < 2:
                time_s = 0.15  # Good window
            elif hours_to_resolution < 24:
                time_s = 0.15  # Ideal
            elif hours_to_resolution < 72:
                time_s = 0.10  # Acceptable
            else:
                time_s = 0.05  # Too far out, uncertain
                reasons.append("too far out")
            
            score += time_s
        except Exception:
            score += 0.10  # Default if can't parse
    else:
        score += 0.10
    
    return MarketQuality(
        score=round(score, 3),
        resolution_clarity=clarity,
        liquidity_score=liq,
        time_score=time_s if 'time_s' in dir() else 0.10,
        reason="; ".join(reasons) if reasons else "good quality",
    )


# ============================================================
# Adaptive Thresholds
# ============================================================

class AdaptiveThresholds:
    """
    Auto-tune trading thresholds based on recent performance.
    When accuracy is low → tighten filters (fewer but better trades)
    When accuracy is high → loosen slightly (more trades, more profit)
    """
    
    def __init__(self):
        self.recent_wins = 0
        self.recent_losses = 0
        self.window_size = 20  # Look at last 20 trades
        self.history = []  # True = win, False = loss
    
    def record_result(self, won: bool):
        """Record a trade result."""
        self.history.append(won)
        if len(self.history) > self.window_size:
            self.history = self.history[-self.window_size:]
        
        self.recent_wins = sum(1 for r in self.history if r)
        self.recent_losses = sum(1 for r in self.history if not r)
    
    @property
    def recent_accuracy(self) -> float:
        """Recent accuracy as a percentage."""
        if not self.history:
            return 0.0
        return (self.recent_wins / len(self.history)) * 100
    
    def get_adjusted_thresholds(self) -> dict:
        """
        Get adjusted thresholds based on recent performance.
        
        Returns dict with:
            - edge_threshold: Minimum edge to trade
            - materiality_threshold: Minimum materiality
            - composite_threshold: Minimum composite score
            - max_bet_multiplier: Bet size multiplier (0.5-2.0)
        """
        if len(self.history) < 5:
            # Not enough data, use defaults
            return {
                "edge_threshold": config.EDGE_THRESHOLD,
                "materiality_threshold": config.MATERIALITY_THRESHOLD,
                "composite_threshold": 0.70,
                "max_bet_multiplier": 1.0,
            }
        
        acc = self.recent_accuracy
        
        if acc >= 85:
            # Excellent — can afford to be slightly more aggressive
            return {
                "edge_threshold": max(0.12, config.EDGE_THRESHOLD - 0.03),
                "materiality_threshold": max(0.70, config.MATERIALITY_THRESHOLD - 0.05),
                "composite_threshold": 0.65,
                "max_bet_multiplier": 1.3,  # Bet slightly more
            }
        elif acc >= 75:
            # Good — maintain current settings
            return {
                "edge_threshold": config.EDGE_THRESHOLD,
                "materiality_threshold": config.MATERIALITY_THRESHOLD,
                "composite_threshold": 0.70,
                "max_bet_multiplier": 1.0,
            }
        elif acc >= 60:
            # Below target — tighten filters
            return {
                "edge_threshold": config.EDGE_THRESHOLD + 0.03,
                "materiality_threshold": config.MATERIALITY_THRESHOLD + 0.05,
                "composite_threshold": 0.75,
                "max_bet_multiplier": 0.8,  # Bet slightly less
            }
        else:
            # Poor — significantly tighten
            return {
                "edge_threshold": config.EDGE_THRESHOLD + 0.05,
                "materiality_threshold": config.MATERIALITY_THRESHOLD + 0.10,
                "composite_threshold": 0.80,
                "max_bet_multiplier": 0.5,  # Half bet size
            }


# ============================================================
# Enhanced Edge Detection (V5)
# ============================================================

def enhance_signal(
    signal,
    price_history: list[dict] = None,
    news_age_seconds: float = 60.0,
    price_change_since_news: float = 0.0,
    adaptive: AdaptiveThresholds = None,
):
    """
    Apply V5 enhancements to an existing signal.
    
    Modifies signal in place:
    - Adjusts composite_score based on momentum + contrarian analysis
    - Adjusts bet_amount using Kelly criterion
    - Adds signal grading
    
    Returns the enhanced signal, or None if it should be filtered out.
    """
    if signal is None:
        return None
    
    # 1. Momentum analysis
    momentum = MomentumResult("flat", 0.0, signal.market_price, signal.market_price, 0.0, "neutral")
    if price_history:
        momentum = analyze_momentum(price_history, signal.market_price, signal.classification)
    
    # 2. Contrarian detection
    contrarian = detect_contrarian(
        materiality=signal.materiality,
        market_price=signal.market_price,
        direction=signal.classification,
        news_age_seconds=news_age_seconds,
        price_change_since_news=price_change_since_news,
    )
    
    # 3. Adjust composite score
    boost = 0.0
    
    # Momentum boost/penalty
    if momentum.signal == "momentum_aligned":
        boost += 0.05 * momentum.strength  # Up to +5%
        log.info(f"[optimizer] Momentum aligned: +{0.05 * momentum.strength:.3f} boost")
    elif momentum.signal == "momentum_against":
        boost -= 0.03 * momentum.strength  # Up to -3% (contrarian can still work)
        log.info(f"[optimizer] Momentum against: {-(0.03 * momentum.strength):.3f} penalty")
    
    # Contrarian boost
    if contrarian.is_contrarian:
        boost += 0.08 * contrarian.confidence  # Up to +8%
        log.info(f"[optimizer] Contrarian detected: +{0.08 * contrarian.confidence:.3f} boost — {contrarian.reason}")
    
    signal.composite_score = min(1.0, signal.composite_score + boost)
    
    # 4. Adaptive threshold check
    if adaptive:
        thresholds = adaptive.get_adjusted_thresholds()
        
        if signal.edge < thresholds["edge_threshold"]:
            log.info(f"[optimizer] REJECTED by adaptive: edge={signal.edge:.3f} < {thresholds['edge_threshold']:.3f}")
            return None
        
        if signal.materiality < thresholds["materiality_threshold"]:
            log.info(f"[optimizer] REJECTED by adaptive: mat={signal.materiality:.2f} < {thresholds['materiality_threshold']:.2f}")
            return None
        
        if signal.composite_score < thresholds["composite_threshold"]:
            log.info(f"[optimizer] REJECTED by adaptive: composite={signal.composite_score:.3f} < {thresholds['composite_threshold']:.3f}")
            return None
        
        # Adjust bet size
        signal.bet_amount = min(
            signal.bet_amount * thresholds["max_bet_multiplier"],
            config.MAX_BET_USD
        )
    
    # 5. Kelly position sizing (override default sizing)
    if signal.side == "YES":
        odds = 1.0 / max(signal.market_price, 0.01)
    else:
        odds = 1.0 / max(1.0 - signal.market_price, 0.01)
    
    kelly_bet = kelly_size(
        edge=signal.edge,
        odds=odds,
        bankroll=config.BANKROLL_USD,
        fraction=0.25,
        max_bet=config.MAX_BET_USD,
    )
    
    # Use the more conservative of Kelly and current sizing
    signal.bet_amount = min(signal.bet_amount, kelly_bet)
    signal.bet_amount = max(signal.bet_amount, 0.50)  # Minimum bet
    
    # 6. Update reasoning with optimizer info
    optimizer_notes = []
    if momentum.signal != "neutral":
        optimizer_notes.append(f"mom={momentum.trend}({momentum.change_pct:+.1f}%)")
    if contrarian.is_contrarian:
        optimizer_notes.append(f"contra={contrarian.confidence:.0%}")
    if adaptive and len(adaptive.history) >= 5:
        optimizer_notes.append(f"acc={adaptive.recent_accuracy:.0f}%")
    
    if optimizer_notes:
        signal.reasoning += f" [V5: {', '.join(optimizer_notes)}]"
    
    return signal


# ============================================================
# Global adaptive instance
# ============================================================

adaptive_thresholds = AdaptiveThresholds()