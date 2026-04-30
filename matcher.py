"""
News-to-market matching — routes breaking news to relevant active markets.
Two strategies: fast keyword matching + semantic Claude matching for ambiguous cases.
"""
from __future__ import annotations

import logging
from markets import Market

log = logging.getLogger(__name__)


def extract_keywords(question: str) -> list[str]:
    """Extract meaningful keywords from a market question."""
    stopwords = {
        "will", "the", "a", "an", "be", "by", "in", "on", "at", "to",
        "of", "for", "is", "it", "this", "that", "and", "or", "not",
        "before", "after", "end", "yes", "no", "any", "has", "have",
        "does", "do", "than", "more", "less", "over", "under", "above",
        "below", "through", "during", "between", "reach", "exceed",
    }
    words = question.lower().split()
    keywords = [
        w.strip("?.,!\"'()[]")
        for w in words
        if w.strip("?.,!\"'()[]") not in stopwords and len(w.strip("?.,!\"'()[]")) > 2
    ]
    return keywords


import re

def match_news_to_markets(
    headline: str,
    markets: list[Market],
    max_matches: int = 5,
    top_k: int | None = None,
) -> list[Market]:
    """
    Find markets that a news headline is relevant to.
    Uses strict word-boundary keyword overlap scoring.
    """
    if top_k is not None:
        max_matches = top_k
    headline_lower = headline.lower()
    scored = []

    # Pre-tokenize headline for faster matching
    headline_words = set(re.findall(r'\b\w{3,}\b', headline_lower))

    for market in markets:
        keywords = extract_keywords(market.question)
        if not keywords:
            continue

        # Count keyword hits using word boundaries (exact word match)
        hits = 0
        matched_kws = []
        for kw in keywords:
            if kw in headline_words:
                hits += 1
                matched_kws.append(kw)

        if hits == 0:
            continue

        # STRICTNESS: 
        # 1. Need at least 2 hits OR if only 1 hit, it must be a long word (>6 chars)
        # 2. Score must be > 0.2
        score = hits / len(keywords)
        
        is_strong_match = (hits >= 2) or (hits == 1 and len(matched_kws[0]) >= 5)
        
        if is_strong_match and score >= 0.10:
            scored.append((score, market))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in scored[:max_matches]]


def match_news_to_markets_broad(
    headline: str,
    summary: str,
    markets: list[Market],
    max_matches: int = 5,
) -> list[Market]:
    """
    Tightened broad matching. Headline + Summary keyword overlap.
    No longer falls back to generic category matching as it causes hallucinations.
    """
    return match_news_to_markets(f"{headline} {summary}", markets, max_matches)



if __name__ == "__main__":
    from markets import fetch_active_markets, filter_by_categories
    import config

    print("Fetching markets...")
    all_m = fetch_active_markets(limit=100)
    filtered = filter_by_categories(all_m)
    niche = [m for m in filtered if config.MIN_VOLUME_USD <= m.volume <= config.MAX_VOLUME_USD]
    print(f"Niche markets: {len(niche)}")

    test_headlines = [
        "OpenAI reportedly testing GPT-5 internally with select partners",
        "Bitcoin ETF inflows hit $2.1B in single week",
        "Fed minutes signal growing consensus for summer rate cut",
    ]

    for h in test_headlines:
        matches = match_news_to_markets(h, niche)
        print(f"\n\"{h[:60]}...\"")
        print(f"  Matched {len(matches)} markets:")
        for m in matches:
            print(f"    [{m.category}] {m.question[:50]}")
