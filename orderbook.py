"""
orderbook.py — Direct Polymarket CLOB orderbook fetch.
No auth, no Telegram. Replaces broken Polycool integration.

Public CLOB API: https://clob.polymarket.com/book?token_id=<tokenId>
Returns bids/asks depth. We extract best bid, best ask, spread, depth.

A tight spread (<3¢) + strong book depth means the market is liquid and
consensus-priced — a great time to trade if we have an edge.
A wide spread (>10¢) means low liquidity / high uncertainty — we back off.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

CLOB_API = "https://clob.polymarket.com"
log = logging.getLogger(__name__)


@dataclass
class BookSignal:
    token_id: str
    best_bid: float
    best_ask: float
    spread: float
    mid: float
    bid_depth_usd: float   # total USD on bid side (top 5 levels)
    ask_depth_usd: float   # total USD on ask side (top 5 levels)
    liquidity_tier: str    # "deep" / "medium" / "thin"


def fetch_book(token_id: str, timeout: int = 8) -> BookSignal | None:
    """Fetch orderbook for a tokenId (YES or NO token) from Polymarket CLOB."""
    if not token_id:
        return None
    try:
        r = httpx.get(f"{CLOB_API}/book", params={"token_id": token_id}, timeout=timeout)
        if r.status_code != 200:
            return None
        data = r.json()
    except Exception as e:
        log.debug(f"[book] fetch error {token_id[:16]}: {e}")
        return None

    bids = data.get("bids", []) or []
    asks = data.get("asks", []) or []
    if not bids or not asks:
        return None

    try:
        # Orderbook entries: {"price": "0.45", "size": "1234.5"}
        best_bid = float(bids[0]["price"])
        best_ask = float(asks[0]["price"])
    except (KeyError, ValueError, IndexError):
        return None

    # Polymarket CLOB returns bids sorted desc by price, asks asc.
    # Some deployments invert — normalize.
    if best_bid > best_ask:
        best_bid, best_ask = best_ask, best_bid

    spread = best_ask - best_bid
    mid    = (best_bid + best_ask) / 2.0

    # Depth: top 5 price levels × size (shares × price ≈ USD)
    bid_depth = sum(float(b["price"]) * float(b["size"]) for b in bids[:5] if "price" in b and "size" in b)
    ask_depth = sum(float(a["price"]) * float(a["size"]) for a in asks[:5] if "price" in a and "size" in a)
    total_depth = bid_depth + ask_depth

    if total_depth >= 5000:
        tier = "deep"
    elif total_depth >= 1000:
        tier = "medium"
    else:
        tier = "thin"

    return BookSignal(
        token_id=token_id,
        best_bid=best_bid,
        best_ask=best_ask,
        spread=round(spread, 4),
        mid=round(mid, 4),
        bid_depth_usd=round(bid_depth, 2),
        ask_depth_usd=round(ask_depth, 2),
        liquidity_tier=tier,
    )


def book_edge_adjustment(book: BookSignal | None, gemini_direction: str) -> tuple[float, str]:
    """
    Return (materiality_delta, tag) based on orderbook conditions.

    - Tight spread + deep book → +0.08 materiality (market is confident & liquid)
    - Wide spread (>10¢) → -0.10 (low liquidity, risky)
    - Thin book → -0.05 (not enough depth)
    - Book heavily imbalanced AGAINST our direction → -0.08
    - Book heavily imbalanced WITH our direction → +0.06
    """
    if not book:
        return 0.0, ""

    delta = 0.0
    tags = []

    if book.spread < 0.03 and book.liquidity_tier in ("deep", "medium"):
        delta += 0.08
        tags.append(f"tight-spread")
    elif book.spread > 0.10:
        delta -= 0.10
        tags.append(f"wide-spread{book.spread:.2f}")

    if book.liquidity_tier == "thin":
        delta -= 0.05
        tags.append("thin")

    # Imbalance check: if asks much deeper than bids → sellers pressuring → bearish book
    total = book.bid_depth_usd + book.ask_depth_usd
    if total > 500:
        bid_frac = book.bid_depth_usd / total
        if bid_frac > 0.65 and gemini_direction == "bullish":
            delta += 0.06
            tags.append("book-bullish")
        elif bid_frac < 0.35 and gemini_direction == "bearish":
            delta += 0.06
            tags.append("book-bearish")
        elif bid_frac > 0.65 and gemini_direction == "bearish":
            delta -= 0.08
            tags.append("book-vs-gemini")
        elif bid_frac < 0.35 and gemini_direction == "bullish":
            delta -= 0.08
            tags.append("book-vs-gemini")

    return round(delta, 3), " ".join(tags)
