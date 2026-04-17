"""
leaderboard.py — Fetch top-performing Polymarket wallets and their recent trades.
Replaces broken Polycool Telegram integration. No auth needed.

Endpoints tried (in order):
  1. https://lb-api.polymarket.com/profit?window=1d&limit=50
  2. https://data-api.polymarket.com/leaderboard?window=1d
  3. https://polymarket.com/api/leaderboard (web fallback)

Once top wallets are known, we fetch their recent activity from
data-api.polymarket.com/activity?user=<wallet>&limit=20
and detect which markets they just entered.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

import httpx

log = logging.getLogger(__name__)

LB_ENDPOINTS = [
    "https://lb-api.polymarket.com/profit?window=1d&limit=100",
    "https://lb-api.polymarket.com/rank?window=1d&limit=100",
    "https://data-api.polymarket.com/leaderboard?window=1d&limit=100",
]
ACTIVITY_API = "https://data-api.polymarket.com/activity"

# Cache: wallet list refreshed every hour
_wallet_cache: list[str] = []
_wallet_cache_at: float = 0.0
_WALLET_TTL = 3600


@dataclass
class CopySignal:
    condition_id: str
    direction: str     # "bullish"/"bearish"/"neutral"
    wallet_count: int  # how many top wallets bought this
    total_usd: float
    reason: str


def fetch_top_wallets(limit: int = 50) -> list[str]:
    """Fetch top-performing wallets from Polymarket leaderboard APIs."""
    global _wallet_cache, _wallet_cache_at
    if time.time() - _wallet_cache_at < _WALLET_TTL and _wallet_cache:
        return _wallet_cache

    wallets: list[str] = []
    for url in LB_ENDPOINTS:
        try:
            r = httpx.get(url, timeout=10)
            if r.status_code != 200:
                continue
            data = r.json()
            items = data if isinstance(data, list) else data.get("data") or data.get("leaderboard") or []
            for it in items[:limit]:
                w = it.get("proxyWallet") or it.get("wallet") or it.get("user") or it.get("address")
                if w and w not in wallets:
                    wallets.append(w)
            if wallets:
                log.info(f"[lb] {len(wallets)} top wallets from {url.split('/')[2]}")
                break
        except Exception as e:
            log.debug(f"[lb] {url} failed: {e}")

    if wallets:
        _wallet_cache = wallets
        _wallet_cache_at = time.time()
    return wallets


def fetch_wallet_activity(wallet: str, lookback_hours: int = 6) -> list[dict]:
    """Fetch recent activity for a wallet. Returns list of trade/position events."""
    try:
        r = httpx.get(ACTIVITY_API, params={"user": wallet, "limit": 30}, timeout=8)
        if r.status_code != 200:
            return []
        data = r.json()
        items = data if isinstance(data, list) else data.get("data", [])
        cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
        recent = []
        for it in items:
            ts = it.get("timestamp") or it.get("createdAt") or it.get("time")
            if not ts:
                continue
            try:
                if isinstance(ts, (int, float)):
                    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                else:
                    dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            except Exception:
                continue
            if dt >= cutoff:
                recent.append(it)
        return recent
    except Exception as e:
        log.debug(f"[lb] activity {wallet[:10]} err: {e}")
        return []


def build_copy_signals(condition_ids: set[str], top_n_wallets: int = 30,
                       lookback_hours: int = 6) -> dict[str, CopySignal]:
    """
    For each condition_id, aggregate recent buys from top wallets.
    Returns map: condition_id → CopySignal
    """
    wallets = fetch_top_wallets(limit=top_n_wallets)
    if not wallets:
        return {}

    # aggregate: cid → {yes_usd, no_usd, wallets_set}
    agg: dict[str, dict] = {}
    for w in wallets[:top_n_wallets]:
        activity = fetch_wallet_activity(w, lookback_hours=lookback_hours)
        for ev in activity:
            cid = ev.get("conditionId") or ev.get("market") or ev.get("condition_id")
            if not cid or cid not in condition_ids:
                continue
            side = str(ev.get("outcome") or ev.get("side") or "").upper()
            usd  = float(ev.get("usdcSize") or ev.get("size") or ev.get("amount") or 0)
            if usd < 50:  # ignore dust
                continue
            d = agg.setdefault(cid, {"yes": 0.0, "no": 0.0, "wallets": set()})
            if "YES" in side or side == "1":
                d["yes"] += usd
            elif "NO" in side or side == "0":
                d["no"] += usd
            d["wallets"].add(w)

    signals: dict[str, CopySignal] = {}
    for cid, d in agg.items():
        total = d["yes"] + d["no"]
        if total < 100:
            continue
        yes_frac = d["yes"] / total
        if yes_frac >= 0.65:
            direction = "bullish"
        elif yes_frac <= 0.35:
            direction = "bearish"
        else:
            direction = "neutral"
        signals[cid] = CopySignal(
            condition_id=cid,
            direction=direction,
            wallet_count=len(d["wallets"]),
            total_usd=total,
            reason=f"{len(d['wallets'])} top wallets: ${d['yes']:.0f} YES / ${d['no']:.0f} NO",
        )
    return signals
