"""
price_feeds.py — Real-time price data from free APIs.
Used to verify crypto/stock market outcomes mathematically.

Sources:
  - Binance (primary, free, no key, high rate limits) — BTC, ETH, SOL etc.
  - CoinGecko (fallback, free, no key) — BTC, ETH, SOL, XRP, BNB, DOGE, ADA, AVAX
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


# ── Binance symbol map (primary — no key, high rate limits) ─────────────────
BINANCE_SYMBOLS: dict[str, str] = {
    "btc": "BTCUSDT", "bitcoin": "BTCUSDT",
    "eth": "ETHUSDT", "ethereum": "ETHUSDT",
    "sol": "SOLUSDT", "solana": "SOLUSDT",
    "xrp": "XRPUSDT", "ripple": "XRPUSDT",
    "bnb": "BNBUSDT",
    "doge": "DOGEUSDT", "dogecoin": "DOGEUSDT",
    "ada": "ADAUSDT", "cardano": "ADAUSDT",
    "avax": "AVAXUSDT", "avalanche": "AVAXUSDT",
    "matic": "MATICUSDT", "polygon": "MATICUSDT",
    "link": "LINKUSDT", "chainlink": "LINKUSDT",
    "uni": "UNIUSDT", "uniswap": "UNIUSDT",
    "shib": "SHIBUSDT",
    "pepe": "PEPEUSDT",
    "dot": "DOTUSDT", "polkadot": "DOTUSDT",
    "ltc": "LTCUSDT", "litecoin": "LTCUSDT",
    "atom": "ATOMUSDT", "cosmos": "ATOMUSDT",
}

# ── CoinGecko ID map (fallback) ──────────────────────────────────────────────
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


def _get_binance_price(symbol: str) -> Optional[float]:
    """Fetch price from Binance public API (no key required)."""
    bn_sym = BINANCE_SYMBOLS.get(symbol.lower().strip())
    if not bn_sym:
        return None
    cache_key = f"bn:{bn_sym}"
    if cache_key in _cache:
        price, ts = _cache[cache_key]
        if time.time() - ts < CACHE_TTL:
            return price
    try:
        resp = httpx.get(
            "https://api.binance.com/api/v3/ticker/price",
            params={"symbol": bn_sym},
            timeout=5,
        )
        data = resp.json()
        price = float(data["price"])
        _cache[cache_key] = (price, time.time())
        log.info(f"[price_feeds] Binance {symbol.upper()} = ${price:,.4f}")
        return price
    except Exception as e:
        log.debug(f"[price_feeds] Binance error for {symbol}: {e}")
        return None


def _get_binance_all() -> dict[str, float]:
    """Fetch all prices from Binance in one call."""
    cache_key = "bn:all"
    if cache_key in _cache:
        _, ts = _cache[cache_key]
        if time.time() - ts < CACHE_TTL:
            # Return cached values for each symbol
            result = {}
            for sym, bn_sym in BINANCE_SYMBOLS.items():
                k = f"bn:{bn_sym}"
                if k in _cache:
                    result[sym] = _cache[k][0]
            if result:
                return result

    try:
        resp = httpx.get(
            "https://api.binance.com/api/v3/ticker/price",
            timeout=8,
        )
        data = resp.json()  # list of {symbol, price}
        price_map = {item["symbol"]: float(item["price"]) for item in data if "symbol" in item}
        now = time.time()
        result = {}
        for sym, bn_sym in BINANCE_SYMBOLS.items():
            if bn_sym in price_map:
                price = price_map[bn_sym]
                result[sym] = price
                _cache[f"bn:{bn_sym}"] = (price, now)
        _cache[cache_key] = (0.0, now)  # marker
        log.info(f"[price_feeds] Binance bulk: {len(result)} prices")
        return result
    except Exception as e:
        log.warning(f"[price_feeds] Binance bulk error: {e}")
        return {}


def get_crypto_price(symbol: str) -> Optional[float]:
    """Get current USD price for a crypto symbol. Tries Binance first, then CoinGecko."""
    symbol = symbol.lower().strip()

    # Try Binance first (fast, no rate limit)
    price = _get_binance_price(symbol)
    if price is not None:
        return price

    # Fallback: CoinGecko
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
        entry = data.get(cg_id, {})
        if not isinstance(entry, dict) or "usd" not in entry:
            return None
        price = float(entry["usd"])
        _cache[cache_key] = (price, time.time())
        log.info(f"[price_feeds] CoinGecko {symbol.upper()} = ${price:,.2f}")
        return price
    except Exception as e:
        log.warning(f"[price_feeds] CoinGecko error for {symbol}: {e}")
        return None


def get_all_crypto_prices() -> dict[str, float]:
    """Fetch all tracked cryptos in one request. Binance primary, CoinGecko fallback."""
    # Try Binance bulk first
    result = _get_binance_all()
    if result:
        return result

    # Fallback: CoinGecko bulk
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
        now = time.time()
        for sym, cg_id in COINGECKO_IDS.items():
            entry = data.get(cg_id, {})
            if isinstance(entry, dict) and "usd" in entry:
                price = float(entry["usd"])
                result[sym] = price
                _cache[f"cg:{cg_id}"] = (price, now)
        log.info(f"[price_feeds] CoinGecko bulk: {len(result)} prices")
        return result
    except Exception as e:
        log.warning(f"[price_feeds] CoinGecko bulk error: {e}")
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

    if "up or down" in q:
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
        return None  # can't know direction until period closes

    if direction == "between_low" and threshold:
        # "Will BTC be between $74,000 and $76,000?"
        # Extract both bounds from original question
        amounts = re.findall(r'[\d,]+(?:\.\d+)?', question.replace("$",""))
        bounds = []
        for a in amounts:
            try:
                v = float(a.replace(",",""))
                if v > 100:  # filter out small numbers like years
                    bounds.append(v)
            except Exception:
                pass
        bounds.sort()
        if len(bounds) >= 2:
            low, high = bounds[0], bounds[1]
            if price < low * 0.92 or price > high * 1.08:
                # Price clearly outside the range → NO
                gap = min(abs(price - low)/low, abs(price - high)/high)
                conf = min(0.95, 0.80 + gap * 0.5)
                return {
                    "direction": "bearish",
                    "confidence": round(conf, 3),
                    "reasoning": f"{symbol.upper()} is ${price:,.0f}, outside range ${low:,.0f}-${high:,.0f} — NO very likely",
                    "current_price": price,
                    "threshold": low,
                }
            elif low * 1.01 <= price <= high * 0.99:
                # Price clearly inside range → YES
                conf = 0.82
                return {
                    "direction": "bullish",
                    "confidence": round(conf, 3),
                    "reasoning": f"{symbol.upper()} is ${price:,.0f}, inside range ${low:,.0f}-${high:,.0f} — YES likely",
                    "current_price": price,
                    "threshold": low,
                }
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
    print("Live prices:", {k: f"${v:,.4f}" for k, v in list(prices.items())[:8]})

    tests = [
        "Will Bitcoin be above $70,000 on April 20?",
        "Will ETH be below $1,000 on April 20?",
        "Will BTC dip to $50,000?",
        "Bitcoin Up or Down - April 20?",
        "Will Ethereum be above $2,355 on April 20?",
    ]
    for q in tests:
        result = verify_crypto_market(q)
        print(f"\nQ: {q}")
        print(f"A: {result}")
