from __future__ import annotations

from dataclasses import dataclass

import httpx

import config

GAMMA_API = "https://gamma-api.polymarket.com"


@dataclass
class Market:
    condition_id: str
    question: str
    category: str
    yes_price: float
    no_price: float
    volume: float
    end_date: str
    active: bool
    tokens: list[dict]

    @property
    def implied_probability(self) -> float:
        return self.yes_price


def fetch_active_markets(limit: int = 50) -> list[Market]:
    """Fetch active, liquid markets from Polymarket's Gamma API."""
    markets = []

    import time as _time
    max_retries = 3
    timeout = 30
    import random
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ]
    
    for attempt in range(max_retries):
        try:
            headers = {"User-Agent": random.choice(user_agents)}
            resp = httpx.get(
                f"{GAMMA_API}/markets",
                params={
                    "limit": limit,
                    "active": True,
                    "closed": False,
                    "order": "volume",
                    "ascending": False,
                },
                headers=headers,
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            break # Success
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 2 * (attempt + 1)
                print(f"[markets] Gamma API timeout/error (attempt {attempt+1}): {e}. Retrying in {wait}s...")
                _time.sleep(wait)
            else:
                print(f"[markets] Gamma API failed after {max_retries} attempts: {e}, falling back to CLOB...")
                return _fetch_from_clob(limit)

    items = data if isinstance(data, list) else data.get("data", [])

    for m in items:
        try:
            # Gamma API uses outcomePrices as a JSON string
            outcome_prices = m.get("outcomePrices", "")
            yes_price = 0.5
            no_price = 0.5

            if outcome_prices:
                import json
                try:
                    prices = json.loads(outcome_prices) if isinstance(outcome_prices, str) else outcome_prices
                    if len(prices) >= 2:
                        yes_price = float(prices[0])
                        no_price = float(prices[1])
                except (json.JSONDecodeError, ValueError):
                    pass

            # Also check tokens array
            tokens = m.get("tokens", m.get("clobTokenIds", []))
            if isinstance(tokens, str):
                import json
                try:
                    tokens = json.loads(tokens)
                except json.JSONDecodeError:
                    tokens = []

            # Build token list for order execution
            clob_token_ids = m.get("clobTokenIds", "")
            if isinstance(clob_token_ids, str):
                import json
                try:
                    clob_token_ids = json.loads(clob_token_ids)
                except json.JSONDecodeError:
                    clob_token_ids = []

            token_list = []
            outcomes = ["Yes", "No"]
            for i, tid in enumerate(clob_token_ids if isinstance(clob_token_ids, list) else []):
                token_list.append({
                    "token_id": tid,
                    "outcome": outcomes[i] if i < len(outcomes) else f"Outcome_{i}",
                    "price": yes_price if i == 0 else no_price,
                })

            vol = float(m.get("volume", m.get("volumeNum", 0)) or 0)
            question = m.get("question", "")

            # Skip resolved or low-info markets
            if yes_price in (0.0, 1.0) and vol == 0:
                continue

            markets.append(Market(
                condition_id=m.get("conditionId", m.get("condition_id", m.get("id", ""))),
                question=question,
                category=_infer_category(question, m.get("tags", None) or []),
                yes_price=yes_price,
                no_price=no_price,
                volume=vol,
                end_date=m.get("endDate", m.get("end_date_iso", "")),
                active=m.get("active", True),
                tokens=token_list,
            ))
        except (KeyError, ValueError, TypeError):
            continue

    # Sort by volume descending
    markets.sort(key=lambda x: x.volume, reverse=True)
    return markets


def _fetch_from_clob(limit: int) -> list[Market]:
    """Fallback: fetch from CLOB API directly."""
    markets = []
    try:
        resp = httpx.get(
            f"{config.POLYMARKET_HOST}/markets",
            params={"limit": limit, "active": True},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[markets] CLOB API error: {e}")
        return markets

    items = data if isinstance(data, list) else data.get("data", data.get("markets", []))

    for m in items:
        try:
            tokens = m.get("tokens", [])
            yes_price = 0.5
            no_price = 0.5
            for t in tokens:
                outcome = t.get("outcome", "").lower()
                price = float(t.get("price", 0.5))
                if outcome == "yes":
                    yes_price = price
                elif outcome == "no":
                    no_price = price

            markets.append(Market(
                condition_id=m.get("condition_id", m.get("id", "")),
                question=m.get("question", ""),
                category=_infer_category(m.get("question", ""), m.get("tags") or []),
                yes_price=yes_price,
                no_price=no_price,
                volume=float(m.get("volume", 0)),
                end_date=m.get("end_date_iso", m.get("end_date", "")),
                active=m.get("active", True),
                tokens=tokens,
            ))
        except (KeyError, ValueError):
            continue

    return markets


def _infer_category(question: str, tags: list) -> str:
    """Infer category from question text and tags."""
    q = question.lower()
    tag_str = " ".join(str(t).lower() for t in tags)
    combined = f"{q} {tag_str}"

    if any(kw in combined for kw in ["ai", "artificial intelligence", "openai", "chatgpt", "llm", "google ai", "anthropic", "gpt"]):
        return "ai"
    if any(kw in combined for kw in ["bitcoin", "ethereum", "crypto", "blockchain", "defi", "token", "btc", "eth", "solana"]):
        return "crypto"
    if any(kw in combined for kw in ["election", "president", "congress", "senate", "trump", "biden", "political", "governor", "vote", "ballot", "legislation"]):
        return "politics"
    if any(kw in combined for kw in [
        "ipl", "cricket", "nba", "nfl", "soccer", "football", "basketball",
        "tennis", "ufc", "mma", "f1", "formula", "olympics", "world cup",
        "champions league", "premier league", "playoffs", "super bowl",
        "match", "tournament", "championship", "season", "batting", "bowling",
        # Fight/MMA/sports props (critical - these were passing as "other")
        "fight", "ko", "tko", "knockout", "goalscorer", "goal scorer",
        "anytime goalscorer", "round", "distance", "go the distance",
        "win by", "decision", "submission", "striker", "pitcher",
        "batter", "touchdown", "home run", "assist", "rebounds",
        "points scored", "passing yards", "rushing yards",
    ]):
        return "sports"
    if any(kw in combined for kw in [
        "oscars", "grammy", "emmy", "box office", "movie", "film", "album",
        "netflix", "disney", "spotify", "streaming", "celebrity", "award",
        "concert", "tour", "entertainment", "american idol", "bachelor",
        "dancing with", "reality tv", "talent show", "season finale",
        "elimination", "voted off",
    ]):
        return "entertainment"
    if any(kw in combined for kw in [
        "fed", "interest rate", "inflation", "gdp", "unemployment", "recession",
        "stock", "s&p", "nasdaq", "dow", "treasury", "yield", "bond",
        "earnings", "revenue", "ipo",
    ]):
        return "finance"
    if any(kw in combined for kw in ["spacex", "nasa", "climate", "research", "study", "discovery", "mars", "starship"]):
        return "science"
    if any(kw in combined for kw in ["tech", "apple", "google", "microsoft", "software", "startup", "nvidia", "meta", "tesla"]):
        return "technology"
    if any(kw in combined for kw in ["war", "nato", "sanctions", "united nations", "geopolitical", "invasion", "ceasefire"]):
        return "world"
    return "other"


def filter_by_end_hours(markets: list[Market], hours: float = 24) -> list[Market]:
    """Return only markets closing within `hours` from now (UTC)."""
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=hours)
    fmts = [
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ]
    result = []
    for m in markets:
        end_dt = None
        for fmt in fmts:
            try:
                end_dt = datetime.strptime(m.end_date[:26], fmt).replace(tzinfo=timezone.utc)
                break
            except (ValueError, TypeError):
                continue
        if end_dt and now < end_dt <= cutoff:
            result.append(m)
    return result


def filter_by_categories(markets: list[Market], categories: list[str] | None = None) -> list[Market]:
    """Filter markets to only target categories."""
    cats = categories or config.MARKET_CATEGORIES
    return [m for m in markets if m.category in cats]


def get_token_id(market: Market, side: str) -> str | None:
    """Get the token ID for a given side (YES/NO)."""
    for t in market.tokens:
        if t.get("outcome", "").upper() == side.upper():
            return t.get("token_id")
    return None


if __name__ == "__main__":
    all_markets = fetch_active_markets(limit=20)
    filtered = filter_by_categories(all_markets)
    print(f"\n--- {len(filtered)} markets in target categories (of {len(all_markets)} total) ---\n")
    for m in filtered[:15]:
        print(f"  [{m.category}] {m.question}")
        print(f"    YES: {m.yes_price:.2f} | NO: {m.no_price:.2f} | Vol: ${m.volume:,.0f}")
        print()
