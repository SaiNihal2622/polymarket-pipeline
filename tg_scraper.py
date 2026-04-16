"""
tg_scraper.py — Polycool bot market feed via Telegram user account.

Sends /market <keyword> to @polycoolapp_bot, parses the response into
MarketFeedItem objects (question, yes_price, no_price, bid, ask, volume, liquidity, expiry).

Used by demo_runner.py as an additional market intelligence signal.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

TG_API_ID   = int(os.getenv("TG_API_ID", "37171721"))
TG_API_HASH = os.getenv("TG_API_HASH", "e55c30fcf0368f49113f59cccefb19b6")
TG_PHONE    = os.getenv("TG_PHONE", "+916305842166")
SESSION_FILE = Path(__file__).parent / "polycool_session.session"

# Restore session from env var on Railway (base64-encoded)
_SESSION_B64 = os.getenv("TG_SESSION_B64", "")
if _SESSION_B64 and not SESSION_FILE.exists():
    try:
        SESSION_FILE.write_bytes(base64.b64decode(_SESSION_B64))
        log.info("[tg] Restored session from TG_SESSION_B64 env var")
    except Exception as e:
        log.warning(f"[tg] Failed to restore session: {e}")

BOT = "@polycoolapp_bot"

# Keywords to query — one per scan cycle
MARKET_KEYWORDS = [
    "bitcoin", "ethereum", "solana",
    "trump", "fed rate", "tariff",
    "ipl", "nba", "soccer", "tennis",
    "nasdaq", "s&p 500",
]


@dataclass
class BotMarket:
    question: str
    yes_price: float = 0.0
    no_price: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    volume: float = 0.0
    liquidity: float = 0.0
    expiry: str = ""
    keyword: str = ""


def _parse_price(s: str) -> float:
    """Parse '29.5¢' or '$2.58M' → float."""
    s = s.strip().replace("¢", "").replace("$", "").replace(",", "")
    mult = 1.0
    if s.endswith("M"):
        mult = 1_000_000
        s = s[:-1]
    elif s.endswith("K"):
        mult = 1_000
        s = s[:-1]
    try:
        return float(s) * mult / (100 if mult == 1.0 else 1)
    except ValueError:
        return 0.0


def _parse_bot_response(text: str, keyword: str) -> list[BotMarket]:
    """Parse the /market response text into BotMarket items."""
    items = []
    # Split into individual market blocks (numbered 1), 2), 3)...)
    blocks = re.split(r'\n(?=\d+\))', text)
    for block in blocks:
        lines = [l.strip() for l in block.strip().splitlines() if l.strip()]
        if not lines:
            continue
        # First line: "N) Will X..." or the group header
        question = re.sub(r'^\d+\)\s*', '', lines[0]).strip()
        if not question or len(question) < 10:
            continue

        m = BotMarket(question=question, keyword=keyword)
        for line in lines[1:]:
            line = line.lstrip('├└│').strip()
            if line.startswith("Yes") and "·" in line:
                parts = line.split("·")
                m.yes_price = _parse_price(parts[0].replace("Yes", ""))
                m.no_price  = _parse_price(parts[1].replace("No", ""))
            elif line.startswith("Vol") and "·" in line:
                parts = line.split("·")
                m.volume    = _parse_price(parts[0].replace("Vol", ""))
                m.liquidity = _parse_price(parts[1].replace("Liq", ""))
            elif line.startswith("Bid") and "·" in line:
                parts = line.split("·")
                m.bid = _parse_price(parts[0].replace("Bid", ""))
                m.ask = _parse_price(parts[1].replace("Ask", ""))
            elif line.startswith("Exp"):
                m.expiry = line.replace("Exp", "").strip()
        if m.yes_price > 0:
            items.append(m)
    return items


async def _fetch_bot_markets_async(keywords: list[str]) -> list[BotMarket]:
    """Send /market <keyword> for each keyword, return all parsed markets."""
    if not SESSION_FILE.exists():
        log.warning("[tg] No session file — skipping Polycool bot fetch")
        return []

    try:
        from telethon import TelegramClient
    except ImportError:
        log.warning("[tg] telethon not installed — pip install telethon")
        return []

    results: list[BotMarket] = []
    try:
        client = TelegramClient(str(SESSION_FILE.with_suffix("")), TG_API_ID, TG_API_HASH)
        await client.connect()
        if not await client.is_user_authorized():
            log.warning("[tg] Session not authorized — skipping")
            await client.disconnect()
            return []

        for kw in keywords:
            try:
                await client.send_message(BOT, f"/market {kw}")
                await asyncio.sleep(5)
                msgs = await client.get_messages(BOT, limit=5)
                for m in msgs:
                    if m.text and ("Yes" in m.text) and ("¢" in m.text):
                        parsed = _parse_bot_response(m.text, kw)
                        results.extend(parsed)
                        log.info(f"[tg] /market {kw} → {len(parsed)} markets")
                        break
            except Exception as e:
                log.debug(f"[tg] /market {kw} failed: {e}")
            await asyncio.sleep(2)

        await client.disconnect()
    except Exception as e:
        log.warning(f"[tg] Polycool fetch failed: {e}")

    return results


def fetch_polycool_markets(keywords: list[str] | None = None) -> list[BotMarket]:
    """Sync wrapper — call from demo_runner."""
    kws = keywords or MARKET_KEYWORDS
    try:
        loop = asyncio.new_event_loop()
        return loop.run_until_complete(_fetch_bot_markets_async(kws))
    except Exception as e:
        log.warning(f"[tg] fetch_polycool_markets failed: {e}")
        return []


def polycool_signal(question: str, bot_markets: list[BotMarket]) -> dict | None:
    """
    Match a Polymarket question to a Polycool bot market.
    Returns dict with bid/ask/spread info if matched.
    Tight spread = liquid = more reliable price.
    """
    q_lower = question.lower()
    for bm in bot_markets:
        bm_lower = bm.question.lower()
        # Simple overlap score
        q_words = set(q_lower.split())
        b_words = set(bm_lower.split())
        overlap = len(q_words & b_words) / max(len(q_words), 1)
        if overlap >= 0.4:
            spread = round(bm.ask - bm.bid, 4) if bm.ask > 0 and bm.bid > 0 else None
            return {
                "bot_question": bm.question,
                "yes": bm.yes_price,
                "no": bm.no_price,
                "bid": bm.bid,
                "ask": bm.ask,
                "spread": spread,
                "volume": bm.volume,
                "liquidity": bm.liquidity,
                "expiry": bm.expiry,
            }
    return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    markets = fetch_polycool_markets(["bitcoin", "trump", "ipl", "nba"])
    print(f"\nFetched {len(markets)} markets from Polycool bot:\n")
    for m in markets:
        spread = f"spread:{m.ask-m.bid:.3f}" if m.ask > 0 else ""
        print(f"  [{m.keyword}] {m.question[:60]} | yes:{m.yes_price:.3f} vol:${m.volume:,.0f} {spread}")
