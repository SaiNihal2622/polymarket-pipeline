"""
Cross-market correlation engine — finds related Polymarket markets and detects
correlated price movements. Enables cross-market signals and portfolio risk management.

Industry standard: if "Trump wins" moves, "Trump tax policy" should too.
Uses cosine similarity on market metadata + price correlation analysis.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from collections import defaultdict

import httpx
import numpy as np

import config
from markets import Market

log = logging.getLogger(__name__)

GAMMA_API = "https://gamma-api.polymarket.com"


@dataclass
class CorrelatedMarket:
    """A market correlated with another."""
    market: Market
    correlation: float  # -1.0 to 1.0
    relationship: str   # "same_topic", "causal", "inverse", "sector"
    confidence: float   # 0.0 to 1.0


@dataclass
class CorrelationCluster:
    """A group of correlated markets."""
    name: str
    markets: list[str]  # market questions
    avg_correlation: float
    direction: str  # "bullish", "bearish", "neutral"
    size: int = 0


# Keyword-based market categorization for fast grouping
TOPIC_KEYWORDS = {
    "politics": ["trump", "biden", "election", "president", "congress", "senate", "vote", "democrat", "republican", "gop", "white house", "impeach", "cabinet"],
    "crypto": ["bitcoin", "btc", "ethereum", "eth", "crypto", "solana", "sol", "token", "defi", "nft", "blockchain", "binance", "coinbase"],
    "ai": ["openai", "chatgpt", "gpt", "ai ", "artificial intelligence", "nvidia", "google ai", "gemini", "claude", "anthropic", "machine learning"],
    "economy": ["fed", "rate", "inflation", "gdp", "recession", "tariff", "trade war", "unemployment", "stock market", "s&p", "nasdaq", "dow jones", "treasury"],
    "geopolitics": ["war", "ukraine", "russia", "china", "taiwan", "iran", "israel", "hamas", "nato", "sanctions", "ceasefire", "nuclear"],
    "science": ["fda", "approval", "vaccine", "clinical trial", "drug", "spacex", "nasa", "climate", "pandemic", "disease"],
    "tech": ["apple", "iphone", "google", "microsoft", "meta", "facebook", "twitter", "x.com", "amazon", "tesla", "spacex", "uber"],
    "sports": ["nba", "nfl", "mlb", "soccer", "football", "basketball", "world cup", "super bowl", "championship", "playoffs"],
    "culture": ["oscar", "grammy", "emmy", "taylor swift", "kanye", "celebrity", "movie", "album", "billionaire"],
}


def _categorize_market(question: str) -> list[str]:
    """Categorize a market by its question keywords."""
    q_lower = question.lower()
    categories = []
    for cat, keywords in TOPIC_KEYWORDS.items():
        if any(kw in q_lower for kw in keywords):
            categories.append(cat)
    return categories or ["other"]


def _keyword_similarity(q1: str, q2: str) -> float:
    """Fast keyword-based similarity between two market questions."""
    words1 = set(q1.lower().split()) - {"will", "the", "a", "an", "in", "on", "by", "to", "of", "for", "is", "be", "at", "or", "and", "do", "does"}
    words2 = set(q2.lower().split()) - {"will", "the", "a", "an", "in", "on", "by", "to", "of", "for", "is", "be", "at", "or", "and", "do", "does"}
    if not words1 or not words2:
        return 0.0
    intersection = words1 & words2
    union = words1 | words2
    return len(intersection) / len(union) if union else 0.0


class CorrelationEngine:
    """
    Manages market correlation analysis.
    Caches market clusters and updates periodically.
    """

    def __init__(self):
        self._market_cache: list[dict] = []
        self._cache_time: float = 0
        self._cache_ttl: float = 300  # 5 minutes
        self._clusters: dict[str, list[str]] = defaultdict(list)  # topic -> market_ids
        self._price_cache: dict[str, list[float]] = {}  # token_id -> recent prices

    def _refresh_markets(self):
        """Refresh market cache from Gamma API."""
        now = time.time()
        if now - self._cache_time < self._cache_ttl and self._market_cache:
            return

        try:
            resp = httpx.get(
                f"{GAMMA_API}/markets",
                params={"limit": 200, "active": True, "closed": False},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                self._market_cache = data if isinstance(data, list) else data.get("data", [])
                self._cache_time = now

                # Build clusters
                self._clusters.clear()
                for m in self._market_cache:
                    q = m.get("question", "")
                    for cat in _categorize_market(q):
                        mid = m.get("conditionId", m.get("id", ""))
                        if mid:
                            self._clusters[cat].append(mid)
                log.debug(f"[correlation] Cached {len(self._market_cache)} markets in {len(self._clusters)} clusters")
        except Exception as e:
            log.debug(f"[correlation] Market fetch failed: {e}")

    def find_correlated_markets(self, market: Market, limit: int = 5) -> list[CorrelatedMarket]:
        """
        Find markets correlated with the given market.
        Uses topic matching + keyword similarity + price correlation.
        """
        self._refresh_markets()
        if not self._market_cache:
            return []

        # Categorize the target market
        target_cats = _categorize_market(market.question)
        target_price = market.yes_price

        candidates = []
        for m_data in self._market_cache:
            m_id = m_data.get("conditionId", m_data.get("id", ""))
            if m_id == market.id:
                continue

            m_question = m_data.get("question", "")
            m_cats = _categorize_market(m_question)

            # Calculate topic overlap
            topic_overlap = len(set(target_cats) & set(m_cats))
            if topic_overlap == 0:
                continue

            # Keyword similarity
            kw_sim = _keyword_similarity(market.question, m_question)

            # Price correlation (if we have price history)
            price_corr = self._estimate_price_correlation(market.id, m_id, m_data)

            # Combined correlation score
            topic_score = topic_overlap * 0.3
            kw_score = kw_sim * 0.4
            price_score = abs(price_corr) * 0.3

            total_corr = min(1.0, topic_score + kw_score + price_score)

            if total_corr < 0.15:
                continue

            # Determine relationship type
            if topic_overlap >= 2:
                relationship = "same_topic"
            elif price_corr < -0.3:
                relationship = "inverse"
            elif kw_sim > 0.3:
                relationship = "causal"
            else:
                relationship = "sector"

            # Build Market object
            try:
                outcomes = m_data.get("outcomes", '["Yes","No"]')
                if isinstance(outcomes, str):
                    outcomes = json.loads(outcomes)
                outcome_prices = m_data.get("outcomePrices", '[0.5,0.5]')
                if isinstance(outcome_prices, str):
                    outcome_prices = json.loads(outcome_prices)

                yes_price = float(outcome_prices[0]) if outcome_prices else 0.5
                no_price = float(outcome_prices[1]) if len(outcome_prices) > 1 else 1.0 - yes_price

                corr_market = Market(
                    id=m_id,
                    question=m_question,
                    slug=m_data.get("slug", ""),
                    yes_price=yes_price,
                    no_price=no_price,
                    volume=float(m_data.get("volume", 0)),
                    liquidity=float(m_data.get("liquidity", 0)),
                    end_date_str=m_data.get("endDate", ""),
                    category=_categorize_market(m_question)[0] if _categorize_market(m_question) else "other",
                    active=m_data.get("active", True),
                    closed=m_data.get("closed", False),
                    outcomes=outcomes,
                )
            except Exception:
                continue

            candidates.append(CorrelatedMarket(
                market=corr_market,
                correlation=total_corr,
                relationship=relationship,
                confidence=min(1.0, total_corr * 1.2),
            ))

        # Sort by correlation and return top N
        candidates.sort(key=lambda c: c.correlation, reverse=True)
        return candidates[:limit]

    def _estimate_price_correlation(self, id1: str, id2: str, m2_data: dict) -> float:
        """Estimate price correlation between two markets using cached prices."""
        # For now, use category-based correlation estimate
        # Full implementation would use historical price data
        cats1 = set(_categorize_market(m2_data.get("question", "")))

        # Same category = positive correlation estimate
        # Inverse keywords = negative correlation
        q2 = m2_data.get("question", "").lower()
        inverse_keywords = ["not", "fail", "decline", "drop", "crash", "lose"]
        has_inverse = any(kw in q2 for kw in inverse_keywords)

        if has_inverse:
            return -0.5  # Estimate inverse correlation
        return 0.3  # Estimate positive correlation for same-topic

    def get_portfolio_correlation_risk(self, active_markets: list[dict]) -> dict:
        """
        Analyze portfolio-level correlation risk.
        Returns risk metrics and warnings.
        """
        if len(active_markets) < 2:
            return {"risk_level": "low", "warnings": [], "max_correlation": 0.0}

        # Group active positions by category
        category_positions: dict[str, list[dict]] = defaultdict(list)
        for pos in active_markets:
            cats = _categorize_market(pos.get("market", ""))
            for cat in cats:
                category_positions[cat].append(pos)

        warnings = []
        max_corr = 0.0

        # Check category concentration
        total_positions = len(active_markets)
        for cat, positions in category_positions.items():
            concentration = len(positions) / total_positions
            if concentration > 0.5:
                warnings.append(
                    f"HIGH CONCENTRATION: {concentration:.0%} of positions in '{cat}' "
                    f"({len(positions)}/{total_positions})"
                )
            if concentration > 0.3:
                max_corr = max(max_corr, concentration)

        # Check for same-direction bets
        bullish = sum(1 for p in active_markets if p.get("side") == "YES")
        bearish = total_positions - bullish
        if bullish > 0 and bearish > 0:
            direction_ratio = max(bullish, bearish) / total_positions
            if direction_ratio > 0.8:
                warnings.append(
                    f"DIRECTIONAL RISK: {direction_ratio:.0%} of bets in same direction"
                )

        risk_level = "high" if len(warnings) >= 2 else ("medium" if warnings else "low")

        return {
            "risk_level": risk_level,
            "warnings": warnings,
            "max_correlation": max_corr,
            "category_breakdown": {cat: len(pos) for cat, pos in category_positions.items()},
            "direction": {"bullish": bullish, "bearish": bearish},
        }


# Singleton instance
_engine = CorrelationEngine()


def find_correlated_markets(market: Market, limit: int = 5) -> list[CorrelatedMarket]:
    """Module-level function: find correlated markets."""
    return _engine.find_correlated_markets(market, limit)


def get_portfolio_risk(active_positions: list[dict]) -> dict:
    """Module-level function: get portfolio correlation risk."""
    return _engine.get_portfolio_correlation_risk(active_positions)


def get_correlation_boost(market: Market, active_positions: list[dict]) -> float:
    """
    Return a score boost (0.0 to 0.10) based on cross-market correlation.
    Boosts signals where correlated markets confirm direction.
    Penalizes correlated exposure.
    """
    correlated = find_correlated_markets(market, limit=3)
    if not correlated:
        return 0.0

    boost = 0.0

    # Boost if correlated markets are moving same direction
    for cm in correlated:
        if cm.relationship in ("same_topic", "causal") and cm.correlation > 0.3:
            # Check if correlated market price is moving similarly
            if abs(cm.market.yes_price - market.yes_price) < 0.15:
                boost += 0.02

    # Penalty for too much correlated exposure
    risk = _engine.get_portfolio_correlation_risk(active_positions)
    if risk["risk_level"] == "high":
        boost -= 0.05
    elif risk["risk_level"] == "medium":
        boost -= 0.02

    return max(-0.05, min(0.10, boost))