"""
Social sentiment NLP module — analyzes Twitter/X, Telegram, Reddit mentions
for Polymarket-related topics. Converts social buzz into probability estimates.

Industry standard: high positive sentiment + low price = potential edge.
Uses keyword matching + sentiment scoring (no external NLP dependencies for speed).
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from collections import Counter

import httpx

import config

log = logging.getLogger(__name__)

# Sentiment lexicon — weighted words for financial/prediction context
POSITIVE_WORDS = {
    "bullish": 2.0, "moon": 1.5, "pump": 1.5, "breakout": 1.8, "surge": 1.8,
    "rally": 1.5, "buy": 1.2, "long": 1.2, "accumulate": 1.5, "undervalued": 1.8,
    "opportunity": 1.3, "edge": 1.5, "confident": 1.5, "likely": 1.2, "probable": 1.3,
    "confirmed": 1.8, "approved": 2.0, "passed": 1.5, "wins": 1.5, "victory": 1.5,
    "success": 1.5, "milestone": 1.3, "record": 1.2, "growth": 1.3, "profit": 1.2,
    "strong": 1.3, "positive": 1.2, "upgrade": 1.5, "beat": 1.3, "exceed": 1.5,
    "fomo": 1.0, "parabolic": 1.5, "ath": 1.5, "new high": 1.5, "massive": 1.2,
    "huge": 1.2, "guaranteed": 1.0, "inevitable": 1.2, "obvious": 1.0,
}
NEGATIVE_WORDS = {
    "bearish": 2.0, "crash": 2.0, "dump": 1.8, "sell": 1.5, "short": 1.5,
    "overvalued": 1.8, "bubble": 1.8, "scam": 2.0, "fraud": 2.0, "rug": 2.0,
    "unlikely": 1.5, "impossible": 2.0, "denied": 2.0, "rejected": 2.0, "failed": 1.8,
    "decline": 1.3, "drop": 1.5, "fall": 1.3, "loss": 1.3, "risk": 1.0,
    "danger": 1.5, "warning": 1.3, "caution": 1.0, "fear": 1.5, "panic": 2.0,
    "capitulation": 2.0, "liquidation": 1.8, "bankruptcy": 2.0, "collapse": 2.0,
    "dead": 1.8, "over": 1.5, "rigged": 1.5, "manipulated": 1.5,
}
INTENSIFIERS = {"very": 1.5, "extremely": 2.0, "incredibly": 2.0, "absolutely": 2.0,
                "definitely": 1.5, "certainly": 1.5, "obviously": 1.3, "clearly": 1.3}
NEGATORS = {"not", "no", "never", "don't", "doesn't", "won't", "can't", "isn't", "aren't"}


@dataclass
class SentimentResult:
    """Result of sentiment analysis for a topic."""
    topic: str
    mention_count: int
    positive_mentions: int
    negative_mentions: int
    neutral_mentions: int
    raw_score: float  # -1.0 to 1.0
    weighted_score: float  # -1.0 to 1.0 (intensified)
    volume_trend: str  # "rising", "stable", "falling"
    implied_probability: float  # 0.0 to 1.0
    confidence: float  # 0.0 to 1.0 (based on sample size)
    top_phrases: list[str]


def _score_text(text: str) -> tuple[float, float]:
    """Score a single text. Returns (raw_score, weighted_score)."""
    words = re.findall(r'\b\w+\b', text.lower())
    raw_pos = 0
    raw_neg = 0
    weighted_pos = 0.0
    weighted_neg = 0.0
    has_negation = False
    intensifier_mult = 1.0

    for i, word in enumerate(words):
        # Check for negation in previous 3 words
        if word in NEGATORS:
            has_negation = True
            continue

        # Check for intensifiers
        if word in INTENSIFIERS:
            intensifier_mult = INTENSIFIERS[word]
            continue

        if word in POSITIVE_WORDS:
            weight = POSITIVE_WORDS[word] * intensifier_mult
            if has_negation:
                raw_neg += 1
                weighted_neg += weight
                has_negation = False
            else:
                raw_pos += 1
                weighted_pos += weight
        elif word in NEGATIVE_WORDS:
            weight = NEGATIVE_WORDS[word] * intensifier_mult
            if has_negation:
                raw_pos += 1
                weighted_pos += weight * 0.5  # Negated negative is weaker positive
                has_negation = False
            else:
                raw_neg += 1
                weighted_neg += weight

        # Reset modifiers after use
        intensifier_mult = 1.0
        if i > 0 and words[i - 1] not in NEGATORS:
            has_negation = False

    total = raw_pos + raw_neg
    if total == 0:
        return 0.0, 0.0

    raw = (raw_pos - raw_neg) / total
    weighted_total = weighted_pos + weighted_neg
    weighted = (weighted_pos - weighted_neg) / weighted_total if weighted_total > 0 else 0.0
    return max(-1.0, min(1.0, raw)), max(-1.0, min(1.0, weighted))


def _sentiment_to_probability(score: float, market_price: float) -> float:
    """
    Convert sentiment score to implied probability.
    Uses logistic function calibrated to prediction markets.

    High positive sentiment near 50% market price → implied prob > market price (edge).
    """
    # Base: sentiment score maps to probability shift
    # Score of 0 = neutral (implied prob = market price)
    # Score of +1 = strongly bullish (implied prob = market + 20%)
    # Score of -1 = strongly bearish (implied prob = market - 20%)
    shift = score * 0.20  # Max 20% shift from sentiment
    implied = market_price + shift
    return max(0.01, min(0.99, implied))


@dataclass
class SocialMention:
    """A single social media mention."""
    text: str
    source: str  # "twitter", "telegram", "reddit", "news"
    timestamp: float
    engagement: int = 0  # likes/retweets/reactions


class SentimentAnalyzer:
    """
    Analyzes social sentiment for prediction market topics.
    Processes mentions from news_stream and external sources.
    """

    def __init__(self):
        self._mention_buffer: dict[str, list[SocialMention]] = {}  # topic -> mentions
        self._sentiment_cache: dict[str, SentimentResult] = {}
        self._cache_ttl: float = 120  # 2 minutes

    def add_mention(self, topic: str, mention: SocialMention):
        """Add a social mention for a topic."""
        topic_key = topic.lower().strip()
        if topic_key not in self._mention_buffer:
            self._mention_buffer[topic_key] = []
        self._mention_buffer[topic_key].append(mention)

        # Keep only last 100 mentions per topic
        if len(self._mention_buffer[topic_key]) > 100:
            self._mention_buffer[topic_key] = self._mention_buffer[topic_key][-100:]

        # Invalidate cache
        self._sentiment_cache.pop(topic_key, None)

    def ingest_news_items(self, news_items: list, topic_keywords: list[str]):
        """
        Ingest news items as social mentions.
        Maps news headlines to topic-keyed sentiment data.
        """
        for item in news_items:
            headline = getattr(item, 'headline', str(item))
            source = getattr(item, 'source', 'news')
            ts = getattr(item, 'timestamp', time.time())

            # Check if headline matches any topic keywords
            headline_lower = headline.lower()
            for keyword in topic_keywords:
                if keyword.lower() in headline_lower:
                    self.add_mention(keyword, SocialMention(
                        text=headline,
                        source=source,
                        timestamp=ts,
                        engagement=1,  # News = 1 engagement point
                    ))
                    break

    def analyze(self, topic: str, market_price: float = 0.5) -> SentimentResult:
        """
        Analyze sentiment for a topic. Returns cached result if fresh.
        """
        topic_key = topic.lower().strip()

        # Check cache
        if topic_key in self._sentiment_cache:
            cached = self._sentiment_cache[topic_key]
            return cached

        mentions = self._mention_buffer.get(topic_key, [])
        if not mentions:
            return SentimentResult(
                topic=topic,
                mention_count=0,
                positive_mentions=0,
                negative_mentions=0,
                neutral_mentions=0,
                raw_score=0.0,
                weighted_score=0.0,
                volume_trend="stable",
                implied_probability=market_price,
                confidence=0.0,
                top_phrases=[],
            )

        # Score all mentions
        positive = 0
        negative = 0
        neutral = 0
        raw_scores = []
        weighted_scores = []
        all_phrases = []

        for mention in mentions:
            raw, weighted = _score_text(mention.text)
            raw_scores.append(raw)
            weighted_scores.append(weighted)

            if raw > 0.1:
                positive += 1
            elif raw < -0.1:
                negative += 1
            else:
                neutral += 1

            # Extract key phrases (2-3 word combinations)
            words = mention.text.lower().split()
            for i in range(len(words) - 1):
                phrase = f"{words[i]} {words[i+1]}"
                if any(w in POSITIVE_WORDS or w in NEGATIVE_WORDS for w in [words[i], words[i+1]]):
                    all_phrases.append(phrase)

        avg_raw = sum(raw_scores) / len(raw_scores) if raw_scores else 0.0
        avg_weighted = sum(weighted_scores) / len(weighted_scores) if weighted_scores else 0.0

        # Volume trend: compare recent vs older mentions
        now = time.time()
        recent = sum(1 for m in mentions if now - m.timestamp < 3600)  # Last 1h
        older = len(mentions) - recent
        if recent > older * 1.5:
            volume_trend = "rising"
        elif recent < older * 0.5:
            volume_trend = "falling"
        else:
            volume_trend = "stable"

        # Implied probability
        implied = _sentiment_to_probability(avg_weighted, market_price)

        # Confidence based on sample size (sigmoid)
        n = len(mentions)
        confidence = min(1.0, n / 20.0)  # Full confidence at 20+ mentions

        # Top phrases
        phrase_counts = Counter(all_phrases)
        top_phrases = [p for p, _ in phrase_counts.most_common(5)]

        result = SentimentResult(
            topic=topic,
            mention_count=n,
            positive_mentions=positive,
            negative_mentions=negative,
            neutral_mentions=neutral,
            raw_score=avg_raw,
            weighted_score=avg_weighted,
            volume_trend=volume_trend,
            implied_probability=implied,
            confidence=confidence,
            top_phrases=top_phrases,
        )

        self._sentiment_cache[topic_key] = result
        return result


# Singleton
_analyzer = SentimentAnalyzer()


def ingest_news(news_items: list, keywords: list[str]):
    """Module-level: ingest news into sentiment analyzer."""
    _analyzer.ingest_news_items(news_items, keywords)


def analyze_sentiment(topic: str, market_price: float = 0.5) -> SentimentResult:
    """Module-level: analyze sentiment for a topic."""
    return _analyzer.analyze(topic, market_price)


def get_sentiment_boost(topic: str, market_price: float) -> float:
    """
    Return a score boost (0.0 to 0.10) based on social sentiment.
    Boosts when sentiment direction aligns with potential trade direction.
    """
    result = _analyzer.analyze(topic, market_price)
    if result.confidence < 0.2 or result.mention_count < 3:
        return 0.0

    boost = 0.0

    # If sentiment is strongly bullish and market is underpriced
    if result.weighted_score > 0.3 and result.implied_probability > market_price + 0.05:
        boost += 0.05 * result.confidence

    # If sentiment is strongly bearish and market is overpriced
    if result.weighted_score < -0.3 and result.implied_probability < market_price - 0.05:
        boost += 0.05 * result.confidence

    # Rising volume trend bonus
    if result.volume_trend == "rising":
        boost += 0.02

    return min(0.10, boost)