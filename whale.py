"""
whale.py — Polymarket whale / smart-money signal + copy-trade tracker.

Uses data-api.polymarket.com (accessible from Railway) to:
1. GET /holders?tokenId=<id>  — top holders per market (YES/NO bias)
2. GET /trades?user=<wallet>  — recent trades from top wallets
3. Copy-trade: if a known top wallet opened a position in the last 2h → signal

Integrated into demo_runner.py Track 1 (fast markets).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx

DATA_API = "https://data-api.polymarket.com"
log = logging.getLogger(__name__)

# Known top-performing wallets (seeded; updated dynamically from /holders)
# Polycool leaderboard wallets — will be populated live
KNOWN_WHALES: list[str] = []

# Minimum holder size (USDC) to be considered a whale
WHALE_MIN_SIZE = 500.0


@dataclass
class WhaleSignal:
    condition_id: str
    yes_bias: float    # net fraction of whale money on YES side (0–1)
    whale_count: int
    top_wallet: str
    total_whale_usd: float
    direction: str     # "bullish" | "bearish" | "neutral"
    reasoning: str


def _get(path: str, params: dict, timeout: int = 12) -> list | dict | None:
    try:
        r = httpx.get(f"{DATA_API}{path}", params=params, timeout=timeout)
        if r.status_code == 200:
            return r.json()
        log.debug(f"[whale] {path} → {r.status_code}")
    except Exception as e:
        log.debug(f"[whale] {path} error: {e}")
    return None


def get_top_holders(condition_id: str, token_id: str | None = None, limit: int = 20) -> list[dict]:
    """Return top position holders for a market. Uses token_id (YES token) if available."""
    # /holders accepts either conditionId or tokenId
    params = {"limit": limit}
    if token_id:
        params["tokenId"] = token_id
    else:
        params["conditionId"] = condition_id
    data = _get("/holders", params)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("data", [])
    return []


def get_recent_trades(wallet: str, condition_id: str, limit: int = 10) -> list[dict]:
    """Return recent trades for a wallet in a specific market."""
    data = _get("/trades", {"user": wallet, "market": condition_id, "limit": limit})
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("data", [])
    return []


def whale_signal(condition_id: str, token_id: str | None = None) -> WhaleSignal | None:
    """
    Compute whale signal for a market.
    Returns WhaleSignal or None if insufficient data.
    """
    holders = get_top_holders(condition_id, token_id=token_id, limit=20)
    if not holders:
        return None

    yes_usd = 0.0
    no_usd  = 0.0
    whale_count = 0
    top_wallet = ""

    for h in holders:
        # Each holder: {proxyWallet, outcome, size (USDC), currentValue, ...}
        size = float(h.get("size", h.get("currentValue", 0)) or 0)
        if size < WHALE_MIN_SIZE:
            continue
        outcome = str(h.get("outcome", "")).upper()
        wallet  = h.get("proxyWallet", h.get("userAddress", ""))

        if "YES" in outcome or outcome == "1":
            yes_usd += size
        elif "NO" in outcome or outcome == "0":
            no_usd  += size

        whale_count += 1
        if not top_wallet:
            top_wallet = wallet

    total = yes_usd + no_usd
    if total < WHALE_MIN_SIZE or whale_count == 0:
        return None

    yes_bias = yes_usd / total
    if yes_bias >= 0.65:
        direction = "bullish"
    elif yes_bias <= 0.35:
        direction = "bearish"
    else:
        direction = "neutral"

    reasoning = (
        f"{whale_count} whales: ${yes_usd:,.0f} YES vs ${no_usd:,.0f} NO "
        f"({yes_bias:.0%} YES bias)"
    )
    log.info(f"[whale] {condition_id[:16]}… {direction} — {reasoning}")

    return WhaleSignal(
        condition_id=condition_id,
        yes_bias=yes_bias,
        whale_count=whale_count,
        top_wallet=top_wallet,
        total_whale_usd=total,
        direction=direction,
        reasoning=reasoning,
    )


def bulk_whale_signals(condition_ids: list[str], token_map: dict[str, str] | None = None, delay: float = 0.3) -> dict[str, WhaleSignal]:
    """Fetch whale signals for multiple markets. Returns {condition_id: signal}."""
    results = {}
    tm = token_map or {}
    for cid in condition_ids:
        sig = whale_signal(cid, token_id=tm.get(cid))
        if sig:
            results[cid] = sig
        time.sleep(delay)
    return results


def get_recent_whale_buys(condition_id: str, lookback_hours: float = 4.0) -> list[dict]:
    """
    Fetch recent trades in a market from high-volume wallets.
    Returns list of {wallet, side, size, timestamp} for trades in last N hours.
    """
    from datetime import datetime, timezone, timedelta
    cutoff_ts = int((datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).timestamp())

    # Get top holders first to know which wallets are whales
    holders = get_top_holders(condition_id, limit=10)
    whale_wallets = [
        h.get("proxyWallet") or h.get("userAddress", "")
        for h in holders
        if float(h.get("size", h.get("currentValue", 0)) or 0) >= WHALE_MIN_SIZE
    ][:5]

    buys = []
    for wallet in whale_wallets:
        if not wallet:
            continue
        data = _get("/trades", {
            "user": wallet,
            "market": condition_id,
            "limit": 10,
            "takerOnly": "true",
        })
        trades = data if isinstance(data, list) else (data or {}).get("data", [])
        for t in trades:
            ts = int(t.get("timestamp", t.get("matchTime", 0)) or 0)
            if ts < cutoff_ts:
                continue
            buys.append({
                "wallet": wallet[:10] + "...",
                "side": t.get("side", "BUY"),
                "size": float(t.get("size", t.get("usdcSize", 0)) or 0),
                "timestamp": ts,
            })
        time.sleep(0.2)

    return buys


def copy_trade_signal(condition_id: str, token_id: str | None = None) -> dict | None:
    """
    Returns a copy-trade signal if whales recently opened large positions.
    signal = {direction: bullish/bearish, confidence: 0-1, reason: str}
    """
    recent = get_recent_whale_buys(condition_id, lookback_hours=4)
    if not recent:
        return None

    yes_size = sum(t["size"] for t in recent if t["side"] in ("BUY", "YES"))
    no_size  = sum(t["size"] for t in recent if t["side"] in ("SELL", "NO"))
    total = yes_size + no_size
    if total < 100:
        return None

    bias = yes_size / total
    direction = "bullish" if bias >= 0.65 else "bearish" if bias <= 0.35 else "neutral"
    confidence = abs(bias - 0.5) * 2  # 0→neutral, 1→all one side

    return {
        "direction": direction,
        "confidence": round(confidence, 2),
        "yes_size": yes_size,
        "no_size": no_size,
        "trade_count": len(recent),
        "reason": f"Whales: ${yes_size:.0f} YES vs ${no_size:.0f} NO in last 4h ({len(recent)} trades)",
    }


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    # Test with a known active market condition ID
    test_id = sys.argv[1] if len(sys.argv) > 1 else "0x9f955c01b3a5a94673d6de7a92fdec00d57c9ec9"
    sig = whale_signal(test_id)
    if sig:
        print(f"\nWhale signal: {sig.direction}")
        print(f"  yes_bias: {sig.yes_bias:.2%}")
        print(f"  whales:   {sig.whale_count}")
        print(f"  total $:  ${sig.total_whale_usd:,.0f}")
        print(f"  reason:   {sig.reasoning}")
    else:
        print("No whale signal (insufficient data or API unreachable)")
