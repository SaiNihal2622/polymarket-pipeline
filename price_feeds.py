"""
price_feeds.py — Real-time price data from free APIs.
Used to verify crypto/stock market outcomes mathematically.

Sources:
  - CoinGecko (free, no key) — BTC, ETH, SOL, XRP, BNB, DOGE, ADA, AVAX
  - Yahoo Finance via yfinance — S&P 500, NASDAQ, stocks
  - All prices cached 60s to avoid hammering APIs
"""
from __future__ import annotations

import time
import logging
import re
from typing import Optional

import httpx

log = logging.getLogger(__name__)

_cache: dict[str, tuple[float, float]] = {}  # symbol → (price, timestamp)
CACHE_TTL = 60  # seconds


# ── CoinGecko ID map ────────────────────────────────────────────────────────
COINGECKO_IDS = {
    "btc": "bitcoin", "bitcoin": "bitcoin",
    "eth": "ethereum", "ethereum": "ethereum",
    "sol": "solana", "solana": "solana",
    "xrp": "ripple", "ripple": "ripple",
    "bnb": "binancecoin",
    "doge": "dogecoin", "dogecoin": "dogecoin",
    "ada": "cardano", "cardano": "cardano",
    "avax": "avalanche-2", "avalanche": "avalanche-2",
    "matic": "matic-network", "polygon": "matic-network",
    "link": "chainlink", "chainlink": "chainlink",
    "uni": "uniswap", "uniswap": "uniswap",
    "shib": "shiba-inu",
    "pepe": "pepe",
    "dot": "polkadot", "polkadot": "polkadot",
    "ltc": "litecoin", "litecoin": "litecoin",
    "atom": "cosmos", "cosmos": "cosmos",
}


def get_crypto_price(symbol: str) -> Optional[float]:
    """Get current USD price for a crypto symbol. Returns None on failure."""
    symbol = symbol.lower().strip()
    cg_id = COINGECKO_IDS.get(symbol)
    if not cg_id:
        return None

    cache_key = f"cg:{cg_id}"
    if cache_key in _cache:
        price, ts = _cache[cache_key]
        if time.time() - ts < CACHE_TTL:
            return price

    try:
        resp = httpx.get(
            f"https://api.coingecko.com/api/v3/simple/price",
            params={"ids": cg_id, "vs_currencies": "usd"},
            timeout=8,
        )
        data = resp.json()
        price = float(data[cg_id]["usd"])
        _cache[cache_key] = (price, time.time())
        log.info(f"[price_feeds] {symbol.upper()} = ${price:,.2f}")
        return price
    except Exception as e:
        log.warning(f"[price_feeds] CoinGecko error for {symbol}: {e}")
        return None


def get_all_crypto_prices() -> dict[str, float]:
    """Fetch all tracked cryptos in one request."""
    ids = ",".join(set(COINGECKO_IDS.values()))
    try:
        resp = httpx.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": ids, "vs_currencies": "usd"},
            timeout=10,
        )
        data = resp.json()
        if not isinstance(data, dict):
            log.warning(f"[price_feeds] CoinGecko unexpected response: {str(data)[:100]}")
            return {}
        result = {}
        now = time.time()
        for sym, cg_id in COINGECKO_IDS.items():
            entry = data.get(cg_id, {})
            if isinstance(entry, dict) and "usd" in entry:
                price = float(entry["usd"])
                result[sym] = price
                _cache[f"cg:{cg_id}"] = (price, now)
        log.info(f"[price_feeds] Bulk fetched {len(result)} crypto prices")
        return result
    except Exception as e:
        log.warning(f"[price_feeds] Bulk CoinGecko error: {e}")
        return {}


# ── Market question parser ───────────────────────────────────────────────────

def _extract_threshold(question: str) -> Optional[tuple[str, str, float]]:
    """
    Parse a market question to extract (symbol, direction, threshold).
    Examples:
      "Will Bitcoin be above $80,000 on April 20?" → ("btc", "above", 80000)
      "Will ETH be below $2,000?" → ("eth", "below", 2000)
      "Will BTC be between $70,000 and $80,000?" → ("btc", "between", 70000)
      "Bitcoin Up or Down - April 20?" → ("btc", "updown", None)
    """
    q = question.lower()

    # Find crypto symbol
    symbol = None
    for sym in ["bitcoin", "btc", "ethereum", "eth", "solana", "sol",
                "xrp", "ripple", "bnb", "dogecoin", "doge", "cardano", "ada",
                "avalanche", "avax", "polygon", "matic", "chainlink", "link",
                "uniswap", "shib", "pepe", "polkadot", "dot", "litecoin", "ltc"]:
        if sym in q:
            symbol = sym
            break

    if not symbol:
        return None

    # Extract dollar threshold
    amounts = re.findall(r'\$[\d,]+(?:\.\d+)?', question.replace(",", ""))
    thresholds = []
    for a in amounts:
        try:
            thresholds.append(float(a.replace("$", "").replace(",", "")))
        except Exception:
            pass

    if "up or down" in q or "up or down" in q:
        return (symbol, "updown", None)
    elif "above" in q and thresholds:
        return (symbol, "above", thresholds[0])
    elif "below" in q and thresholds:
        return (symbol, "below", thresholds[0])
    elif "between" in q and len(thresholds) >= 2:
        return (symbol, "between_low", thresholds[0])
    elif thresholds:
        # "Will Bitcoin dip to $73,000?" or "reach $100,000?"
        if "dip" in q or "drop" in q or "fall" in q:
            return (symbol, "below", thresholds[0])
        elif "reach" in q or "hit" in q or "surge" in q:
            return (symbol, "above", thresholds[0])

    return None


def verify_crypto_market(question: str) -> Optional[dict]:
    """
    Given a market question, fetch the live price and determine if
    the outcome is mathematically determined RIGHT NOW.

    Returns:
      {"direction": "bullish"|"bearish", "confidence": 0.0-1.0,
       "reasoning": "BTC is $84,500 vs threshold $70,000 — YES certain",
       "current_price": 84500, "threshold": 70000}
    or None if cannot determine.
    """
    parsed = _extract_threshold(question)
    if not parsed:
        return None

    symbol, direction, threshold = parsed
    price = get_crypto_price(symbol)
    if price is None:
        return None

    if direction == "updown":
        # "Up or Down" markets resolve at end of period based on price change
        # We can't know the direction until close — skip these
        return None

    if direction == "above" and threshold:
        gap_pct = (price - threshold) / threshold
        if gap_pct > 0.08:
            # Price is >8% above threshold — YES is nearly certain
            conf = min(0.95, 0.80 + gap_pct * 0.5)
            return {
                "direction": "bullish",
                "confidence": round(conf, 3),
                "reasoning": f"{symbol.upper()} is ${price:,.0f}, threshold ${threshold:,.0f} (+{gap_pct:.1%}) — YES very likely",
                "current_price": price,
                "threshold": threshold,
            }
        elif gap_pct < -0.08:
            # Price is >8% below threshold — NO is nearly certain
            conf = min(0.95, 0.80 + abs(gap_pct) * 0.5)
            return {
                "direction": "bearish",
                "confidence": round(conf, 3),
                "reasoning": f"{symbol.upper()} is ${price:,.0f}, threshold ${threshold:,.0f} ({gap_pct:.1%}) — NO very likely",
                "current_price": price,
                "threshold": threshold,
            }

    elif direction == "below" and threshold:
        gap_pct = (threshold - price) / threshold
        if gap_pct > 0.08:
            conf = min(0.95, 0.80 + gap_pct * 0.5)
            return {
                "direction": "bullish",
                "confidence": round(conf, 3),
                "reasoning": f"{symbol.upper()} is ${price:,.0f}, must go below ${threshold:,.0f} — YES likely if close",
                "current_price": price,
                "threshold": threshold,
            }
        elif gap_pct < -0.08:
            conf = min(0.95, 0.80 + abs(gap_pct) * 0.5)
            return {
                "direction": "bearish",
                "confidence": round(conf, 3),
                "reasoning": f"{symbol.upper()} is ${price:,.0f}, already above ${threshold:,.0f} — NO very likely",
                "current_price": price,
                "threshold": threshold,
            }

    return None  # Too close to call — skip


if __name__ == "__main__":
    # Quick test
    prices = get_all_crypto_prices()
    print("Live prices:", {k: f"${v:,.0f}" for k, v in list(prices.items())[:8]})

    tests = [
        "Will Bitcoin be above $70,000 on April 20?",
        "Will ETH be below $1,000 on April 20?",
        "Will BTC dip to $50,000?",
        "Bitcoin Up or Down - April 20?",
    ]
    for q in tests:
        result = verify_crypto_market(q)
        print(f"\nQ: {q}")
        print(f"A: {result}")
