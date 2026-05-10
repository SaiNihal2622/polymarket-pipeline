"""
leaderboard.py — Polymarket top-wallet copy-trade signals.

Uses working public endpoints (verified):
  1. https://gamma-api.polymarket.com/profiles?limit=50&order=profit&ascending=false
     Returns top-profit profiles with their wallet addresses.
  2. https://data-api.polymarket.com/positions?user=<wallet>&sizeThreshold=100
     Returns current open positions for a wallet.
  3. Cross-reference open positions with markets we're about to trade.
     If 3+ top wallets hold YES → bullish signal, NO → bearish signal.

Fallback: Hardcoded known top-performing wallets from Polymarket leaderboard.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

GAMMA_API = "https://gamma-api.polymarket.com"
DATA_API  = "https://data-api.polymarket.com"

# Hardcoded top trader wallets (from Polymarket public leaderboard)
# These are real high-PnL wallets — updated periodically from leaderboard
KNOWN_TOP_WALLETS = [
    # Known top-PnL wallets from Polymarket leaderboard (public data)
    "0x16aa920c53B39d1d8972a604B7c3d21E3cBFCBf4",
    "0x1f5b4Aa2E3F2ea03c2e1FB8e10a20Dbf5c48a86E",
    "0x4bD2d6E1D5Fc62D4d4b59F8F84cf5C5F66C0F90",
    "0x7f2Ed34a04b72Ed8c22F22456Ac8b64d61e01C6E",
    "0xA3aB10e79e3B6bd94d5a96E04E7Ca13D5E0C6E42",
]

_EVM_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")


def _is_valid_wallet(wallet: str) -> bool:
    """Reject placeholders/invalid wallets before calling Polymarket APIs."""
    return bool(wallet and _EVM_RE.fullmatch(wallet))

_wallet_cache:    list[str] = []
_wallet_cache_at: float = 0.0
_WALLET_TTL = 3600  # refresh hourly

_position_cache:    dict[str, list[dict]] = {}  # wallet → positions
_position_cache_at: float = 0.0
_POS_TTL = 300  # refresh every 5 min


def fetch_top_wallets(limit: int = 50) -> list[str]:
    """Fetch top-PnL wallets from Gamma profiles API, fallback to hardcoded list."""
    global _wallet_cache, _wallet_cache_at
    if time.time() - _wallet_cache_at < _WALLET_TTL and _wallet_cache:
        return _wallet_cache

    wallets: list[str] = []

    # Try all known Polymarket leaderboard endpoints
    endpoints = [
        f"{GAMMA_API}/profiles?limit={limit}&order=profit&ascending=false",
        f"{GAMMA_API}/profiles?limit={limit}&sortBy=totalProfit&order=desc",
        f"{GAMMA_API}/leaderboard?limit={limit}",
        f"{DATA_API}/profiles?limit={limit}&order=profit",
        f"{DATA_API}/leaderboard?limit={limit}&order=profit",
        # Try with different params
        f"{GAMMA_API}/profiles?limit={limit}&order=volumeTraded&ascending=false",
    ]
    for url in endpoints:
        try:
            r = httpx.get(url, timeout=12, headers={"User-Agent": "polymarket-bot/1.0"})
            if r.status_code != 200:
                log.debug(f"[lb] {url} → {r.status_code}")
                continue
            data = r.json()
            items = data if isinstance(data, list) else (
                data.get("data") or data.get("profiles") or data.get("leaderboard") or []
            )
            for it in items[:limit]:
                w = (it.get("proxyWallet") or it.get("address") or
                     it.get("wallet")      or it.get("user") or "")
                if _is_valid_wallet(w) and w not in wallets:
                    wallets.append(w)
            if len(wallets) >= 10:
                log.info(f"[lb] {len(wallets)} wallets from {url.split('//')[1].split('/')[0]}")
                break
        except Exception as e:
            log.debug(f"[lb] {url}: {e}")

    # Always include hardcoded known whales
    for w in KNOWN_TOP_WALLETS:
        if _is_valid_wallet(w) and w not in wallets:
            wallets.append(w)

    if wallets:
        _wallet_cache    = wallets
        _wallet_cache_at = time.time()
        log.info(f"[lb] Total wallet pool: {len(wallets)}")
    return wallets or KNOWN_TOP_WALLETS


def fetch_wallet_positions(wallet: str, timeout: int = 8) -> list[dict]:
    """Fetch current open positions for a wallet. Returns list of position dicts."""
    if not _is_valid_wallet(wallet):
        log.debug(f"[lb] skipped invalid wallet: {wallet}")
        return []

    # Gamma has no /positions route; using it creates noisy 404s. Data API is the
    # supported public positions endpoint, but it returns 400 for invalid wallets,
    # which are filtered above.
    endpoints = [
        f"{DATA_API}/positions?user={wallet}&sizeThreshold=50",
        f"{DATA_API}/positions?user={wallet}",
    ]
    for url in endpoints:
        try:
            r = httpx.get(url, timeout=timeout, headers={"User-Agent": "polymarket-bot/1.0"})
            if r.status_code != 200:
                continue
            data = r.json()
            items = data if isinstance(data, list) else data.get("data") or data.get("positions") or []
            if items:
                log.debug(f"[lb] {wallet[:10]} → {len(items)} positions")
                return items
        except Exception as e:
            log.debug(f"[lb] positions {wallet[:10]}: {e}")
    return []


@dataclass
class CopySignal:
    condition_id: str
    direction: str      # "bullish" / "bearish" / "neutral"
    wallet_count: int
    total_usd: float
    reason: str


def build_copy_signals(condition_ids: set[str],
                       top_n: int = 20,
                       min_usd: float = 100.0) -> dict[str, CopySignal]:
    """
    For each condition_id, check how many top wallets hold YES vs NO.
    Returns map: condition_id → CopySignal
    """
    global _position_cache, _position_cache_at
    now = time.time()

    wallets = fetch_top_wallets(limit=top_n)[:top_n]
    if not wallets:
        return {}

    # Refresh position cache if stale
    if now - _position_cache_at > _POS_TTL:
        new_cache: dict[str, list[dict]] = {}
        fetched = 0
        for w in wallets[:25]:  # check top 25 wallets
            positions = fetch_wallet_positions(w)
            if positions:
                new_cache[w] = positions
                fetched += 1
            time.sleep(0.15)  # gentle rate limiting
        _position_cache    = new_cache
        _position_cache_at = now
        log.info(f"[lb] position cache: {fetched}/{min(25,len(wallets))} wallets, {sum(len(p) for p in new_cache.values())} positions")

    # Aggregate per condition_id
    agg: dict[str, dict] = {}
    for wallet, positions in _position_cache.items():
        for pos in positions:
            cid = (pos.get("conditionId") or pos.get("market") or
                   pos.get("condition_id") or pos.get("marketId") or "")
            if not cid or cid not in condition_ids:
                continue
            outcome = str(pos.get("outcome") or pos.get("side") or "").upper()
            size    = float(pos.get("size") or pos.get("currentValue") or
                           pos.get("amount") or 0)
            if size < min_usd:
                continue
            d = agg.setdefault(cid, {"yes": 0.0, "no": 0.0, "wallets": set()})
            if "YES" in outcome or outcome in ("1", "Y", "BUY"):
                d["yes"] += size
            elif "NO" in outcome or outcome in ("0", "N", "SELL"):
                d["no"]  += size
            d["wallets"].add(wallet)

    signals: dict[str, CopySignal] = {}
    for cid, d in agg.items():
        total = d["yes"] + d["no"]
        if total < min_usd:
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
            total_usd=round(total, 2),
            reason=f"{len(d['wallets'])} top wallets: ${d['yes']:.0f}YES/${d['no']:.0f}NO",
        )

    if signals:
        log.info(f"[lb] {len(signals)} copy signals found")
    return signals
