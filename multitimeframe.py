"""
Multi-timeframe price analysis — checks 1h, 4h, 24h price trends on Polymarket.
Helps identify momentum, reversals, and optimal entry timing.

Industry standard: confirm trend on higher timeframe, enter on pullback in lower timeframe.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum

import httpx

import config

log = logging.getLogger(__name__)

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = config.POLYMARKET_HOST


class TrendDirection(Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


@dataclass
class TimeframeData:
    """Price data for a single timeframe."""
    timeframe: str  # "1h", "4h", "24h"
    start_price: float
    end_price: float
    high: float
    low: float
    change_pct: float
    volatility: float  # (high - low) / mid
    direction: TrendDirection
    volume_delta: float = 0.0  # net buy vs sell volume


@dataclass
class MultiTimeframeAnalysis:
    """Combined multi-timeframe analysis for a market."""
    token_id: str
    question: str
    tf_1h: TimeframeData | None = None
    tf_4h: TimeframeData | None = None
    tf_24h: TimeframeData | None = None
    # Confluence signals
    trend_aligned: bool = False  # All timeframes agree
    momentum_score: float = 0.0  # -1.0 (strong bearish) to +1.0 (strong bullish)
    volatility_regime: str = "normal"  # "low", "normal", "high", "extreme"
    entry_timing: str = "neutral"  # "pullback", "breakout", "neutral"
    recommendation: str = ""


def _fetch_price_history(token_id: str, fidelity_minutes: int = 5, start_ts: int | None = None) -> list[dict]:
    """Fetch historical price data from Polymarket CLOB."""
    try:
        params = {"market": token_id, "fidelity": fidelity_minutes}
        if start_ts:
            params["startTs"] = start_ts
        resp = httpx.get(f"{CLOB_API}/prices-history", params=params, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("history", data if isinstance(data, list) else [])
    except Exception as e:
        log.debug(f"[multitimeframe] Price history fetch failed for {token_id}: {e}")
    return []


def _analyze_timeframe(prices: list[dict], timeframe_label: str) -> TimeframeData | None:
    """Analyze price data for a single timeframe window."""
    if not prices or len(prices) < 2:
        return None

    p_values = [float(p.get("p", p.get("price", 0))) for p in prices if p.get("p") is not None or p.get("price") is not None]
    if not p_values:
        return None

    start_price = p_values[0]
    end_price = p_values[-1]
    high = max(p_values)
    low = min(p_values)
    mid = (high + low) / 2 if (high + low) > 0 else 0.5
    volatility = (high - low) / mid if mid > 0 else 0
    change_pct = ((end_price - start_price) / start_price * 100) if start_price > 0 else 0

    if change_pct > 1.0:
        direction = TrendDirection.BULLISH
    elif change_pct < -1.0:
        direction = TrendDirection.BEARISH
    else:
        direction = TrendDirection.NEUTRAL

    return TimeframeData(
        timeframe=timeframe_label,
        start_price=start_price,
        end_price=end_price,
        high=high,
        low=low,
        change_pct=change_pct,
        volatility=volatility,
        direction=direction,
    )


def analyze_market_timeframes(token_id: str, question: str = "") -> MultiTimeframeAnalysis:
    """
    Perform multi-timeframe analysis on a market.
    Fetches 24h of data at 5-min intervals, then splits into 1h, 4h, 24h windows.
    """
    now = int(time.time())
    # Fetch 24h of 5-min candle data
    start_24h = now - (24 * 3600)
    all_prices = _fetch_price_history(token_id, fidelity_minutes=5, start_ts=start_24h)

    if not all_prices:
        return MultiTimeframeAnalysis(token_id=token_id, question=question, recommendation="No price data available")

    # Parse timestamps
    parsed = []
    for p in all_prices:
        ts = p.get("t", p.get("timestamp", 0))
        price = float(p.get("p", p.get("price", 0)))
        if ts and price:
            parsed.append({"ts": ts, "price": price})

    if not parsed:
        return MultiTimeframeAnalysis(token_id=token_id, question=question, recommendation="Invalid price data")

    # Split into timeframes
    hour_ago = now - 3600
    four_hours_ago = now - (4 * 3600)

    tf_1h_data = [p for p in parsed if p["ts"] >= hour_ago]
    tf_4h_data = [p for p in parsed if p["ts"] >= four_hours_ago]
    tf_24h_data = parsed

    tf_1h = _analyze_timeframe(tf_1h_data, "1h")
    tf_4h = _analyze_timeframe(tf_4h_data, "4h")
    tf_24h = _analyze_timeframe(tf_24h_data, "24h")

    # Calculate confluence
    directions = []
    volatilities = []
    changes = []
    for tf in [tf_1h, tf_4h, tf_24h]:
        if tf:
            directions.append(tf.direction)
            volatilities.append(tf.volatility)
            changes.append(tf.change_pct)

    # Trend alignment: all timeframes agree
    bullish_count = sum(1 for d in directions if d == TrendDirection.BULLISH)
    bearish_count = sum(1 for d in directions if d == TrendDirection.BEARISH)
    trend_aligned = bullish_count == len(directions) or bearish_count == len(directions)

    # Momentum score: weighted average (-1 to +1)
    weights = [0.5, 0.3, 0.2]  # 1h has most weight for timing
    momentum = 0.0
    for i, c in enumerate(changes[:3]):
        # Normalize change to -1 to +1 range (cap at ±20%)
        normalized = max(-1.0, min(1.0, c / 20.0))
        momentum += normalized * weights[i]
    momentum = max(-1.0, min(1.0, momentum))

    # Volatility regime
    avg_vol = sum(volatilities) / len(volatilities) if volatilities else 0
    if avg_vol < 0.02:
        vol_regime = "low"
    elif avg_vol < 0.05:
        vol_regime = "normal"
    elif avg_vol < 0.10:
        vol_regime = "high"
    else:
        vol_regime = "extreme"

    # Entry timing: look for pullbacks against higher TF trend
    entry_timing = "neutral"
    if tf_24h and tf_1h:
        if tf_24h.direction == TrendDirection.BULLISH and tf_1h.direction == TrendDirection.BEARISH:
            entry_timing = "pullback"  # Buy the dip in uptrend
        elif tf_24h.direction == TrendDirection.BEARISH and tf_1h.direction == TrendDirection.BULLISH:
            entry_timing = "pullback"  # Sell the rip in downtrend
        elif tf_1h.change_pct > 3.0 and tf_4h and tf_4h.direction == TrendDirection.BULLISH:
            entry_timing = "breakout"

    # Generate recommendation
    if trend_aligned and momentum > 0.3:
        rec = f"STRONG BULLISH — All timeframes aligned upward. Momentum: {momentum:.2f}"
    elif trend_aligned and momentum < -0.3:
        rec = f"STRONG BEARISH — All timeframes aligned downward. Momentum: {momentum:.2f}"
    elif entry_timing == "pullback":
        rec = f"PULLBACK OPPORTUNITY — Higher TF trend intact, lower TF retracing. Momentum: {momentum:.2f}"
    elif vol_regime == "extreme":
        rec = f"HIGH VOLATILITY — Caution. Wide price swings. Avg vol: {avg_vol:.1%}"
    elif abs(momentum) < 0.1:
        rec = f"NEUTRAL — No clear direction. Consider waiting for catalyst. Momentum: {momentum:.2f}"
    else:
        rec = f"MIXED SIGNALS — Partial trend alignment. Momentum: {momentum:.2f}"

    return MultiTimeframeAnalysis(
        token_id=token_id,
        question=question,
        tf_1h=tf_1h,
        tf_4h=tf_4h,
        tf_24h=tf_24h,
        trend_aligned=trend_aligned,
        momentum_score=momentum,
        volatility_regime=vol_regime,
        entry_timing=entry_timing,
        recommendation=rec,
    )


def get_timing_boost(analysis: MultiTimeframeAnalysis) -> float:
    """
    Return a score boost (0.0 to 0.15) based on multi-timeframe confluence.
    Used by edge detector to enhance composite scores.
    """
    boost = 0.0

    # Trend alignment bonus
    if analysis.trend_aligned:
        boost += 0.05

    # Pullback entry timing bonus
    if analysis.entry_timing == "pullback":
        boost += 0.05
    elif analysis.entry_timing == "breakout":
        boost += 0.03

    # Momentum strength bonus
    if abs(analysis.momentum_score) > 0.5:
        boost += 0.03

    # Volatility penalty (extreme vol = risky)
    if analysis.volatility_regime == "extreme":
        boost -= 0.05
    elif analysis.volatility_regime == "high":
        boost -= 0.02

    return max(0.0, min(0.15, boost))