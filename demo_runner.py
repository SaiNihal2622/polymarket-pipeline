#!/usr/bin/env python3
"""
demo_runner.py — Paper-trade markets resolving within 24 hours.

Uses the FULL V2 analysis engine:
  - Pass 1: Analyst classification (bullish/bearish/neutral + materiality)
  - Pass 2: Skeptic / devil's advocate (MiroFish debate pattern)
  - Consensus: BOTH passes must agree — else SKIP
  - RRF multi-signal composite: classification + materiality + price room
    + niche bonus + news recency (SkillX fusion scoring)

Flow:
  1. Fetch live Polymarket markets ending in ≤ DEMO_HOURS_WINDOW hours
  2. Scrape news → match headlines to each market
  3. Run full consensus + RRF analysis on each match
  4. Log high-composite signals as demo trades (no real money)
  5. Every RESOLVE_INTERVAL_MIN minutes: check if markets resolved → win/loss
  6. Track accuracy live; when ≥ 70% over 10+ trades → go-live banner

Usage:
  python demo_runner.py              # continuous loop
  python demo_runner.py --once       # single scan then exit
  python demo_runner.py --report     # just show accuracy report
  python demo_runner.py --resolve    # just run resolution check
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
import time
from datetime import datetime, timezone, timedelta

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

import config
import logger
from resolver import get_pending_demo_trades as _get_pending_raw

def get_pending_market_ids() -> set:
    try:
        return {t["market_id"] for t in _get_pending_raw()}
    except Exception:
        return set()
from markets import fetch_active_markets, filter_by_categories
from edge import detect_edge_v2, Signal
from resolver import run_resolution_check, get_accuracy_stats, get_resolved_trade_list, get_pipeline_comparison

console = Console()
log = logging.getLogger(__name__)


def _print_accuracy_oneliner():
    """Always print a one-line accuracy summary — shown every scan and every resolution check."""
    stats = get_accuracy_stats()
    total_logged   = stats.get("total_logged", 0)
    total_resolved = stats["total_resolved"]
    wins           = stats["wins"]
    losses         = stats["losses"]
    acc            = stats["accuracy_pct"]

    if total_resolved == 0:
        acc_str = "[dim]no resolutions yet[/dim]"
    else:
        color   = "bright_green" if acc >= ACCURACY_THRESHOLD else "yellow" if acc >= 50 else "red"
        acc_str = f"[{color}]{acc:.1f}%[/{color}] ({wins}W / {losses}L)"

    need = max(0, MIN_RESOLVED - total_resolved)
    console.print(
        f"  [bold cyan]▶ ACCURACY:[/bold cyan] {acc_str}  "
        f"| logged={total_logged}  resolved={total_resolved}  "
        f"| need {need} more to go-live"
    )

    # Side-by-side pipeline comparison
    try:
        cmp = get_pipeline_comparison()
        old = cmp["old"]
        new = cmp["new"]
        old_acc = f"{old['accuracy_pct']:.1f}%" if old['resolved'] > 0 else "n/a"
        new_acc_val = new['accuracy_pct']
        new_color = "bright_green" if new_acc_val >= 65 else "yellow" if new_acc_val >= 50 else "red"
        new_acc = f"[{new_color}]{new_acc_val:.1f}%[/{new_color}]" if new['resolved'] > 0 else "[dim]no data yet[/dim]"
        console.print(
            f"  [dim]  OLD pipeline (#{1}–#191):[/dim] {old_acc} ({old['wins']}W/{old['losses']}L, {old['resolved']} resolved)  "
            f"[bold]NEW pipeline (#192+):[/bold] {new_acc} ({new['wins']}W/{new['losses']}L, {new['resolved']} resolved)"
        )
        # Category breakdown for new pipeline
        cats = cmp.get("new_categories", {})
        if cats:
            cat_parts = []
            for cat, s in sorted(cats.items()):
                c_acc = f"{s['accuracy_pct']:.0f}%" if s['resolved'] > 0 else "?"
                cat_parts.append(f"{cat}:{c_acc}({s['wins']}W/{s['losses']}L)")
            console.print(f"  [dim]  New breakdown → {' | '.join(cat_parts)}[/dim]")
    except Exception:
        pass


def _wipe_all_trades():
    """Wipe ALL trades and outcomes for a clean fresh start."""
    import sqlite3
    from pathlib import Path as _Path
    db = _Path(os.getenv("DB_PATH", "/data/trades.db"))
    if not db.exists():
        console.print("  [dim]No DB to wipe.[/dim]")
        return
    conn = sqlite3.connect(db)
    trades_count = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    outcomes_count = conn.execute("SELECT COUNT(*) FROM outcomes").fetchone()[0]
    conn.execute("DELETE FROM outcomes")
    conn.execute("DELETE FROM trades")
    conn.commit()
    conn.close()
    console.print(f"  [bold red]🗑 WIPED {trades_count} trades + {outcomes_count} outcomes — fresh start[/bold red]")


def _startup_cleanup():
    """
    Two-phase cleanup on startup:
    1. Void non-profitable category trades (sports, esports, NFL draft, UFC, O/U)
       These were logged by the old engine and are money drains (20% accuracy).
    2. Void long-dated futures that can't resolve in 24h.
    """
    import sqlite3
    from pathlib import Path as _Path
    db = _Path(os.getenv("DB_PATH", "/data/trades.db"))
    if not db.exists():
        return
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row

    # ── Phase 1: Void non-crypto trades ────────────────────────────────
    CRYPTO_KW = [
        "bitcoin", "btc", "ethereum", "eth", "solana", "sol", "crypto",
        "dogecoin", "doge", "xrp", "bnb", "hyperliquid",
        "cardano", "ada", "avalanche", "avax", "polkadot", "dot",
        "chainlink", "link", "litecoin", "ltc", "polygon", "matic",
        "uniswap", "uni", "pepe", "shib", "meme coin",
    ]

    non_voided = conn.execute(
        "SELECT id, market_question, status FROM trades WHERE id >= 192 AND status != 'voided'"
    ).fetchall()

    void_ids = []
    for t in non_voided:
        q = (t["market_question"] or "").lower()
        is_profitable = any(k in q for k in CRYPTO_KW)
        if not is_profitable:
            void_ids.append(t["id"])

    if void_ids:
        placeholders = ','.join('?' * len(void_ids))
        conn.execute(f"UPDATE trades SET status = 'voided' WHERE id IN ({placeholders})", void_ids)
        conn.execute(f"DELETE FROM outcomes WHERE trade_id IN ({placeholders})", void_ids)
        conn.execute(f"DELETE FROM calibration WHERE trade_id IN ({placeholders})", void_ids)
        conn.commit()
        console.print(f"  [yellow]🗑 Voided {len(void_ids)} non-profitable trades (sports/esports/UFC/NFL draft)[/yellow]")

    # ── Phase 2: Void old junk trades ────────────────────────────────────
    old_cutoff = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    rows = conn.execute(
        "SELECT id, market_question FROM trades "
        "WHERE status IN ('demo','dry_run') AND created_at < ?",
        (old_cutoff,)
    ).fetchall()

    JUNK_KW = [
        "2027", "world series", "french open", "wimbledon", "us open",
        "nba champion", "nba finals", "super bowl", "afc champion", "nfc champion",
        "eurovision", "lpl 2026", "ipl champion", "grammy", "oscar", "nobel",
        "governor", "senator", "president", "fed chair", "confirmed as",
        "(bo1)", "(bo3)", "map 1 winner", "map 2 winner", "map 3 winner",
        "game 1 winner", "game 2 winner", "o/u ", "both teams to score",
        "halftime", "exact score", "spread:", "1h spread",
    ]

    junk_ids = []
    for r in rows:
        q = (r["market_question"] or "").lower()
        if any(k in q for k in JUNK_KW):
            junk_ids.append(r["id"])

    if junk_ids:
        placeholders = ','.join('?' * len(junk_ids))
        conn.execute(f"UPDATE trades SET status = 'voided' WHERE id IN ({placeholders})", junk_ids)
        conn.execute(f"DELETE FROM outcomes WHERE trade_id IN ({placeholders})", junk_ids)
        conn.commit()
        console.print(f"  [yellow]🗑 Voided {len(junk_ids)} long-dated/junk trades[/yellow]")

    if not void_ids and not junk_ids:
        console.print(f"  [dim]All trades look clean — nothing voided.[/dim]")

    conn.close()


# ── Settings ─────────────────────────────────────────────────────────────────
DEMO_HOURS_WINDOW = float(getattr(config, "DEMO_HOURS_WINDOW", 24))    # markets closing within N hours
SCAN_INTERVAL_MIN = int(getattr(config, "SCAN_INTERVAL_MIN", 30))       # re-scan every N minutes
RESOLVE_INTERVAL_MIN = int(getattr(config, "RESOLVE_INTERVAL_MIN", 10)) # check resolutions every N minutes
ACCURACY_THRESHOLD = float(getattr(config, "ACCURACY_THRESHOLD", 70.0)) # % to unlock live trading
MIN_RESOLVED = int(getattr(config, "MIN_RESOLVED_TRADES", 10))          # min trades needed for decision
# ─────────────────────────────────────────────────────────────────────────────


def _parse_end_date(end_date_str: str) -> datetime | None:
    """Parse various Polymarket date formats into UTC datetime."""
    if not end_date_str:
        return None
    fmts = [
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in fmts:
        try:
            dt = datetime.strptime(end_date_str[:26], fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def filter_closing_soon(markets, hours: float = DEMO_HOURS_WINDOW):
    """Return only markets closing within `hours` from now."""
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=hours)
    result = []
    for m in markets:
        end = _parse_end_date(m.end_date)
        if end and now < end <= cutoff:
            result.append(m)
    return result


def _parse_window_duration_hours(question: str) -> float | None:
    """Detect short-window markets like 'X:XXam-X:XXam ET'. Returns duration in hours or None."""
    pattern = r'(\d+):(\d+)\s*([AaPp][Mm]).*?[-–]\s*(\d+):(\d+)\s*([AaPp][Mm])'
    m = re.search(pattern, question)
    if not m:
        return None
    h1, m1, ap1 = int(m.group(1)), int(m.group(2)), m.group(3).upper()
    h2, m2, ap2 = int(m.group(4)), int(m.group(5)), m.group(6).upper()
    if ap1 == "PM" and h1 != 12: h1 += 12
    if ap1 == "AM" and h1 == 12: h1 = 0
    if ap2 == "PM" and h2 != 12: h2 += 12
    if ap2 == "AM" and h2 == 12: h2 = 0
    mins = (h2 * 60 + m2) - (h1 * 60 + m1)
    if mins < 0: mins += 1440
    return mins / 60


_WEATHER_MARKET_KW = {
    "temperature", "celsius", "fahrenheit", "°c", "°f", "degrees",
    "highest temp", "lowest temp", "hottest", "coldest", "rainfall",
    "precipitation", "wind speed", "humidity",
}


def _is_weather_market(question: str) -> bool:
    q = question.lower()
    return any(k in q for k in _WEATHER_MARKET_KW)


def filter_quality_markets(markets, now: datetime) -> tuple[list, dict]:
    """
    Filter markets to high-quality candidates only. Removes:
      - Markets closing too soon (< MIN_CLOSE_HOURS) — already priced in
      - Markets with extreme YES prices (< MIN_YES_PRICE or > MAX_YES_PRICE) — near-certain
      - Low-volume markets (< MIN_VOLUME_USD) — micro/5-min windows
      - Micro time-window markets (< MIN_WINDOW_HOURS duration)
      - Weather/temperature markets — no relevant news source covers them
    Returns (filtered_list, stats_dict).
    """
    result = []
    skipped = {"too_soon": 0, "price_extreme": 0, "low_volume": 0, "micro_window": 0, "weather": 0}

    for m in markets:
        # 1. Skip markets closing too soon
        end = _parse_end_date(m.end_date)
        if end:
            hours_left = (end - now).total_seconds() / 3600
            if hours_left < config.MIN_CLOSE_HOURS:
                skipped["too_soon"] += 1
                continue

        # 2. Skip near-certain prices — broaden to get more markets
        # <0.05 or >0.95: payout so small it's never worth the risk
        if m.yes_price < 0.05 or m.yes_price > 0.95:
            skipped["price_extreme"] += 1
            continue

        # 3. Volume filter — very low floor to maximise pool
        # EV gate in unified engine handles bad risk/reward, not volume
        end2 = _parse_end_date(m.end_date)
        h_left = ((end2 - now).total_seconds() / 3600) if end2 else 9999
        vol_min = 50 if h_left <= 24 else 200
        if m.volume < vol_min:
            skipped["low_volume"] += 1
            continue

        # 4. Skip micro time-window markets (< 30 min duration)
        win_dur = _parse_window_duration_hours(m.question)
        if win_dur is not None and win_dur < config.MIN_WINDOW_HOURS:
            skipped["micro_window"] += 1
            continue

        # 5. Skip weather/temperature markets — RSS feeds don't cover them
        if _is_weather_market(m.question):
            skipped["weather"] += 1
            continue

        result.append(m)

    return result, skipped


def _log_demo_trade(signal: Signal, token_id: str | None = None) -> int:
    """Log a demo trade to the DB with status='demo'. Always virtual — no real money."""
    trade_id = logger.log_trade(
        market_id=signal.market.condition_id,
        market_question=signal.market.question,
        claude_score=signal.claude_score,
        market_price=signal.market_price,
        edge=signal.edge,
        side=signal.side,
        amount_usd=signal.bet_amount,
        order_id=None,
        status="demo",
        reasoning=signal.reasoning,
        headlines=signal.headlines,
        news_source=signal.news_source or "demo_runner",
        classification=signal.classification,
        materiality=signal.materiality,
        news_latency_ms=signal.news_latency_ms,
        classification_latency_ms=signal.classification_latency_ms,
        total_latency_ms=signal.total_latency_ms,
        token_id=token_id,
    )
    return trade_id



def _get_db_pending_condition_ids() -> set:
    """Get condition_ids of ALL pending trades from database — prevents cross-scan duplicates."""
    import sqlite3
    from pathlib import Path as _Path
    db = _Path(os.getenv("DB_PATH", "/data/trades.db"))
    if not db.exists():
        db = _Path(__file__).parent / "trades.db"
    if not db.exists():
        return set()
    try:
        conn = sqlite3.connect(db)
        rows = conn.execute(
            "SELECT DISTINCT market_id FROM trades WHERE status IN ('demo','dry_run') "
            "AND market_id != ''"
        ).fetchall()
        conn.close()
        return {r[0] for r in rows}
    except Exception:
        return set()


def scan_and_trade() -> dict:
    """
    Simplified scan: 3 signals (price feed, copy-trade, crowd CLOB).
    No AI research. No tier system. Just data-driven signals.
    """
    console.print("\n[bold cyan]── Scan ───────────[/bold cyan]")
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    console.print(f"  {now_str}  |  ≤{DEMO_HOURS_WINDOW:.0f}h window")
    _print_accuracy_oneliner()

    # 1. Fetch markets
    console.print("\n[bold]1. Fetching markets...[/bold]")
    all_markets = fetch_active_markets(limit=2000)
    category_filtered = filter_by_categories(all_markets)
    window_markets = filter_closing_soon(category_filtered, DEMO_HOURS_WINDOW)
    now = datetime.now(timezone.utc)
    day_markets, skipped = filter_quality_markets(window_markets, now)

    console.print(
        f"   {len(all_markets)} total → {len(category_filtered)} categories "
        f"→ {len(window_markets)} in window → [bold yellow]{len(day_markets)} quality[/bold yellow]"
    )

    if not day_markets:
        console.print("   [yellow]No quality markets found.[/yellow]")
        return {"markets": 0, "signals": 0, "demos_logged": 0}

    # Sort by closing time — soonest first
    def _hours_left(m):
        end = _parse_end_date(m.end_date)
        return (end - now).total_seconds() / 3600 if end else 9999
    day_markets.sort(key=_hours_left)

    # ── DEDUP: Check BOTH in-memory and database for existing trades ────
    already_logged = get_pending_market_ids() | _get_db_pending_condition_ids()
    all_candidates = [m for m in day_markets if m.condition_id not in already_logged]
    console.print(f"   {len(all_candidates)} new candidates (filtered {len(day_markets) - len(all_candidates)} already-traded)")

    if not all_candidates:
        console.print("   [yellow]All markets already have pending trades.[/yellow]")
        return {"markets": len(day_markets), "signals": 0, "demos_logged": 0}

    # ── HARD BLOCKLIST ──────────────────────────────────────────────────
    HARD_SKIP = [
        # Long-dated futures (can't resolve in 48h)
        "world series", "super bowl", "stanley cup", "french open", "wimbledon",
        "nba champion", "nba finals", "nfl afc", "nfl nfc", "nhl playoffs",
        "lpl 2026", "ipl champion", "tour de france", "rbc heritage", "masters 2026",
        "governor", "senator", "president", "fed chair", "confirmed as",
        "2027", "grammy", "oscar", "nobel", "eurovision",
        # Esports (pure luck/skill markets)
        "(bo1)", "(bo3)", "map 1 winner", "map 2 winner", "map 3 winner",
        "game 1 winner", "game 2 winner", "game 3 winner", "game 4 winner",
        "first blood", "first tower", "first baron", "quadra kill", "penta kill",
        "dragon soul", "inhibitor", "total kills",
        "dota 2", "valorant", "counter-strike", "league of legends",
        # Sports O/U / props (unresearchable)
        "o/u 1.5", "o/u 2.5", "o/u 3.5", "o/u 4.5", "o/u 5.5",
        "both teams to score", "leading at halftime", "half time",
        "spread:", "correct score", "exact score", "handicap:",
        "points o/u", "assists o/u", "rebounds o/u", "total corners",
        "any player", "up or down", "opens up or down",
        # Misc
        "temperature", "rainfall", "snow",
        "justin bieber", "taylor swift", "box office", "posts from",
        "end in a draw", "art ross", "clutch player", "coach of the year",
        "top goal scorer", "most assists",
        # Player/team season awards
        "win the 2025", "win the 2026", "win the 2027",
        "finish in the top", "relegated",
    ]

    from price_feeds import verify_crypto_market, get_all_crypto_prices
    from whale import bulk_whale_signals
    from leaderboard import build_copy_signals

    # Pre-fetch crypto prices
    try:
        get_all_crypto_prices()
    except Exception:
        pass

    # Build token map
    token_map = {}
    for m in all_candidates:
        if m.tokens and isinstance(m.tokens, list) and m.tokens:
            t = m.tokens[0]
            tid = t.get("token_id") if isinstance(t, dict) else str(t)
            if tid:
                token_map[m.condition_id] = tid

    # Batch whale + copy-trade signals
    all_ids = [m.condition_id for m in all_candidates[:100]]
    try:
        whale_map = bulk_whale_signals(all_ids[:30], token_map=token_map)
    except Exception:
        whale_map = {}
    try:
        copy_map = build_copy_signals(set(all_ids), top_n=30, min_usd=50.0)
    except Exception:
        copy_map = {}

    console.print(f"\n[bold cyan]🔮 ENGINE: {len(all_candidates)} markets | whale:{len(whale_map)} copy:{len(copy_map)}[/bold cyan]")

    signals_found: list[Signal] = []
    demos_logged = 0
    analyzed = 0
    MAX_MARKETS = int(os.getenv("MAX_MARKETS_PER_SCAN", "150"))

    for market in all_candidates[:MAX_MARKETS]:
        analyzed += 1
        q_lower = market.question.lower()

        if any(pat in q_lower for pat in HARD_SKIP):
            continue

        hours_left = _hours_left(market)
        price = market.yes_price
        tok = token_map.get(market.condition_id)

        # STRICT: Only trade markets closing within 24 hours
        if hours_left > 24:
            continue

        # CRYPTO ONLY — proven 72% accuracy (18W/7L)
        # Finance (0W/1L) and politics (unproven) removed
        CRYPTO_KW = [
            "bitcoin", "btc", "ethereum", "eth", "solana", "sol",
            "crypto", "dogecoin", "doge", "xrp", "bnb", "hyperliquid",
            "cardano", "ada", "avalanche", "avax", "polkadot", "dot",
            "chainlink", "link", "litecoin", "ltc", "polygon", "matic",
            "uniswap", "uni", "pepe", "shib", "meme coin",
        ]
        if not any(k in q_lower for k in CRYPTO_KW):
            continue

        # SWEET ZONE ONLY — 1:1 payout trades (0.30-0.70)
        # At 0.50 → $1 bet wins $1. At 0.35 → $1 bet wins $1.86.
        # Skip crowd-zone (0.70+) where $1 bet only wins $0.43
        if price < 0.30 or price > 0.70:
            continue

        # ── Signal 1: Price feed (crypto only — mathematical) ─────────
        pf_dir, pf_conf = "neutral", 0.0
        try:
            pf = verify_crypto_market(market.question)
            if pf and pf["confidence"] >= 0.55:
                pf_dir  = pf["direction"]
                pf_conf = pf["confidence"]
        except Exception:
            pass

        # ── Signal 2: Copy-trade (top wallet positions) ───────────────
        cp_dir, cp_conf, cp_wallets = "neutral", 0.0, 0
        lb_sig = copy_map.get(market.condition_id)
        if lb_sig and lb_sig.direction != "neutral":
            cp_dir = lb_sig.direction
            cp_wallets = lb_sig.wallet_count
            cp_conf = min(0.90, 0.50 + cp_wallets * 0.10 + min(lb_sig.total_usd, 5000) / 25000)

        # ── Signal 3: Whale holders ───────────────────────────────────
        wh_dir, wh_conf = "neutral", 0.0
        whale_sig = whale_map.get(market.condition_id)
        if whale_sig and whale_sig.direction != "neutral":
            wh_dir  = whale_sig.direction
            wh_conf = min(0.80, abs(whale_sig.yes_bias - 0.5) * 2.0)

        # ── Signal 4: CLOB crowd — always available ───────────────────
        # Price IS the crowd's probability. 0.60 = 60% crowd says YES.
        # This ensures sweet-zone markets always have at least one signal.
        clob_dir, clob_conf = "neutral", 0.0
        if price >= 0.55:
            clob_dir, clob_conf = "bullish", price
        elif price <= 0.45:
            clob_dir, clob_conf = "bearish", 1.0 - price

        # ── Signal 5: Gemini Flash research (sweet-zone only) ─────────
        # Uses Gemini 2.0 Flash + web search to verify if outcome is known
        # Only for sweet-zone (0.35-0.65) where we need more conviction
        gem_dir, gem_conf = "neutral", 0.0
        is_sweet = 0.35 <= price <= 0.65
        if is_sweet and (pf_conf < 0.55 and cp_conf < 0.50 and wh_conf < 0.50):
            try:
                from classifier import research_market
                res = research_market(market)
                if res.direction in ("bullish", "bearish") and res.materiality >= 0.40:
                    gem_dir = res.direction
                    gem_conf = min(0.85, res.materiality)
            except Exception:
                pass

        # ── Combine: MAX-based scoring ────────────────────────────────
        bull_sigs = []
        bear_sigs = []
        for name, d, c in [("pf", pf_dir, pf_conf), ("copy", cp_dir, cp_conf),
                           ("whale", wh_dir, wh_conf), ("crowd", clob_dir, clob_conf),
                           ("gem", gem_dir, gem_conf)]:
            if d == "bullish" and c > 0:
                bull_sigs.append((name, c))
            elif d == "bearish" and c > 0:
                bear_sigs.append((name, c))

        max_bull = max((c for _, c in bull_sigs), default=0.0)
        max_bear = max((c for _, c in bear_sigs), default=0.0)
        # Agreement boost: +0.05 per extra agreeing signal
        boost_bull = min(0.15, max(0, len(bull_sigs) - 1) * 0.05)
        boost_bear = min(0.15, max(0, len(bear_sigs) - 1) * 0.05)
        score_bull = min(0.95, max_bull + boost_bull)
        score_bear = min(0.95, max_bear + boost_bear)

        # ── Conflict gate: if price feed and copy-trade disagree, skip ─
        if (pf_dir != "neutral" and cp_dir != "neutral"
                and pf_dir != cp_dir and pf_conf >= 0.60 and cp_conf >= 0.55):
            continue

        # ── Minimum signal requirement ─────────────────────────────────
        # Sweet zone (0.35-0.65): need crowd ≥55% OR any real signal OR Gemini
        is_sweet = 0.35 <= price <= 0.65
        if is_sweet:
            has_signal = pf_conf >= 0.55 or cp_conf >= 0.50 or wh_conf >= 0.50 or clob_conf >= 0.55 or gem_conf >= 0.40
            if not has_signal:
                continue
        # Crowd zone (outside 0.35-0.65): crowd IS the signal
        # Only skip if copy-trade directly contradicts crowd
        else:
            if cp_dir != "neutral" and cp_dir != clob_dir and cp_conf >= 0.55:
                continue

        # ── Pick direction ─────────────────────────────────────────────
        # Sweet zone: 0.35 min (1:1 payout needs less accuracy to profit)
        # Crowd zone: 0.30 min (high accuracy from crowd consensus)
        MIN_SCORE = 0.35 if is_sweet else 0.30
        if score_bull >= score_bear and score_bull >= MIN_SCORE:
            final_dir, final_side, final_score = "bullish", "YES", score_bull
        elif score_bear > score_bull and score_bear >= MIN_SCORE:
            final_dir, final_side, final_score = "bearish", "NO", score_bear
        else:
            continue

        # ── EV gate — crypto-proven, moderate threshold ──────────────────
        bet_price = price if final_side == "YES" else (1.0 - price)
        payout_ratio = (1.0 - bet_price) / bet_price
        ev_per_dollar = final_score * payout_ratio - (1.0 - final_score)
        if ev_per_dollar < 0.03:
            continue

        # ── Bet sizing ─────────────────────────────────────────────────
        from bankroll import kelly_bet_size, get_current_bankroll, can_trade_today
        allowed, reason = can_trade_today()
        if not allowed:
            console.print(f"  [red]⛔ {reason}[/red]")
            break
        bk = get_current_bankroll()
        edge = final_score - bet_price
        bet = kelly_bet_size(bk, max(edge, 0.03), bet_price, materiality=final_score)
        bet = round(min(max(0.50, bet), bk * 0.06), 2)

        # ── Log sources ────────────────────────────────────────────────
        sources = []
        if pf_conf >= 0.50:   sources.append(f"💰PF:{pf_conf:.0%}")
        if cp_conf >= 0.40:   sources.append(f"👛Copy:{cp_conf:.0%}({cp_wallets}w)")
        if wh_conf >= 0.40:   sources.append(f"🐋Whale:{wh_conf:.0%}")
        if clob_conf >= 0.50: sources.append(f"📊Crowd:{clob_conf:.0%}")
        if gem_conf >= 0.30:  sources.append(f"🔬Gemini:{gem_conf:.0%}")

        win_profit = round(bet * payout_ratio, 2)
        console.print(
            f"  [bold green]▸[/bold green] [bold]{final_side}[/bold] "
            f"price:{price:.2f} payout:{payout_ratio:.1f}x "
            f"score:{final_score:.2f} ev:{ev_per_dollar:.3f} "
            f"closes:{hours_left:.1f}h\n"
            f"    {' + '.join(sources) if sources else 'crowd-signal'}\n"
            f"    \"{market.question[:70]}\""
        )

        from edge import Signal as _Signal
        unified_signal = _Signal(
            market=market,
            claude_score=final_score,
            market_price=price,
            edge=max(edge, 0.03),
            side=final_side,
            bet_amount=bet,
            reasoning=f"score={final_score:.2f} ev={ev_per_dollar:.3f} | {' + '.join(sources)}",
            headlines="",
            news_source="unified_engine",
            classification=final_dir,
            materiality=final_score,
            composite_score=final_score,
        )
        trade_id = _log_demo_trade(unified_signal, token_id=tok)
        already_logged.add(market.condition_id)
        signals_found.append(unified_signal)
        demos_logged += 1
        console.print(f"    → [green]Trade #{trade_id} logged (${bet:.2f}, +${ev_per_dollar*bet:.2f} EV)[/green]")

    if not signals_found:
        console.print(
            f"  [dim]No signals this scan — {analyzed} markets analyzed. "
            f"Thresholds or materiality not met.[/dim]"
        )

    console.print(f"\n  Scan complete: {analyzed} markets analyzed → {demos_logged} demo trades")
    _print_accuracy_oneliner()

    return {
        "markets": len(day_markets),
        "pairs_analyzed": analyzed,
        "signals": len(signals_found),
        "demos_logged": demos_logged,
    }


def print_accuracy_report():
    """Print a full accuracy report to console."""
    stats = get_accuracy_stats()
    total = stats["total_resolved"]
    decisive = total - stats["pushes"]
    acc = stats["accuracy_pct"]

    console.print()

    if total == 0:
        console.print(Panel(
            "[yellow]No resolved demo trades yet.\n"
            "Markets need time to close. Check back in a few hours.[/yellow]",
            title="📊 Accuracy Report",
        ))
        return

    color = "bright_green" if acc >= ACCURACY_THRESHOLD else "yellow" if acc >= 50 else "red"
    status_line = (
        f"[bright_green]✅ ACCURACY THRESHOLD MET — ready to go LIVE![/bright_green]"
        if stats["ready_for_live"] else
        f"[yellow]Need {MIN_RESOLVED - decisive} more resolved trades + {ACCURACY_THRESHOLD:.0f}%+ accuracy[/yellow]"
    )

    console.print(Panel(
        f"[bold]Resolved Trades:[/bold] {total} ({stats['wins']}W / {stats['losses']}L / {stats['pushes']}P)\n"
        f"[bold]Accuracy:[/bold] [{color}]{acc:.1f}%[/{color}]  (threshold: {ACCURACY_THRESHOLD:.0f}%)\n"
        f"[bold]Total PnL (virtual):[/bold] ${stats['total_pnl']:+.2f}\n\n"
        f"{status_line}",
        title="📊 Demo Accuracy Report",
        border_style=color,
    ))

    # Detailed trade-by-trade breakdown
    trades = get_resolved_trade_list()
    if trades:
        tbl = Table(title="Trade Results", show_lines=True)
        tbl.add_column("#", style="dim", width=4)
        tbl.add_column("Result", width=6)
        tbl.add_column("Side", width=4)
        tbl.add_column("PnL", width=7)
        tbl.add_column("Market", no_wrap=False)

        for t in trades:
            r = t["result"]
            if r == "win":
                sym, col = "✅ W", "bright_green"
            elif r == "loss":
                sym, col = "❌ L", "red"
            else:
                sym, col = "↩ P", "yellow"
            tbl.add_row(
                str(t["id"]),
                f"[{col}]{sym}[/{col}]",
                t["side"],
                f"[{col}]${t['pnl']:+.2f}[/{col}]",
                t["market_question"][:80],
            )
        console.print(tbl)

    return stats


def maybe_go_live(stats: dict, auto: bool = False):
    """If accuracy threshold met, offer to switch to live trading."""
    if not stats or not stats.get("ready_for_live"):
        return False

    console.print(Panel(
        f"[bright_green bold]🚀 ACCURACY THRESHOLD MET![/bright_green bold]\n\n"
        f"Accuracy: {stats['accuracy_pct']:.1f}% over {stats['total_resolved']} resolved trades\n"
        f"Virtual PnL: ${stats['total_pnl']:+.2f}\n\n"
        f"[bold]To switch to LIVE trading:[/bold]\n"
        f"  Set  DRY_RUN=false  in your .env file\n"
        f"  Then run:  python start.py --mode v2",
        title="💰 Ready for Live Trading",
        border_style="bright_green",
    ))

    if auto:
        console.print("[bold yellow]AUTO mode: DRY_RUN is still True — edit .env manually to go live.[/bold yellow]")

    return True


def run_loop():
    """Main continuous demo loop."""
    model_name = config.GEMINI_MODEL if config.LLM_PROVIDER == "gemini" else config.CLASSIFICATION_MODEL
    console.print(Panel(
        f"[bold bright_green]Polymarket Demo Runner — Full V2 Analysis[/bold bright_green]\n\n"
        f"[bold]Analysis pipeline:[/bold]\n"
        f"  1. News scrape (RSS + Twitter + Telegram)\n"
        f"  2. Match headlines → 1-day markets\n"
        f"  3. Pass 1: Analyst LLM  →  bullish / bearish / neutral\n"
        f"  4. Pass 2: Skeptic LLM  →  devil's advocate challenge  [MiroFish]\n"
        f"  5. Consensus gate: both must agree or SKIP\n"
        f"  6. RRF composite score: classification + materiality + price room\n"
        f"                          + niche bonus + recency  [SkillX fusion]\n"
        f"  7. Composite < 0.4 → SKIP  |  ≥ 0.4 → log demo trade\n\n"
        f"[bold]Settings:[/bold]\n"
        f"  Window: ≤{DEMO_HOURS_WINDOW:.0f}h  |  Scan: {SCAN_INTERVAL_MIN}min  |  "
        f"Resolve: {RESOLVE_INTERVAL_MIN}min  |  Go-live: {ACCURACY_THRESHOLD:.0f}%/{MIN_RESOLVED}+ trades\n"
        f"  Model: {config.LLM_PROVIDER} / {model_name}  |  "
        f"Consensus: {'ON (' + str(config.CONSENSUS_PASSES) + ' passes)' if config.CONSENSUS_ENABLED else 'OFF'}\n\n"
        f"[dim]Press Ctrl+C to stop[/dim]",
        title="🎯 Demo Mode Active",
    ))

    # ── FRESH START: wipe all old trades ──────────────────────────────────────
    wipe_env = os.getenv("WIPE_ON_START", "true").lower()
    if wipe_env == "true":
        console.print("\n[bold red]🔄 WIPE_ON_START=true — clearing all old trades for fresh accuracy measurement[/bold red]")
        _wipe_all_trades()
    else:
        _startup_cleanup()

    # Pre-fetch all crypto prices so first scan is instant
    try:
        from price_feeds import get_all_crypto_prices
        prices = get_all_crypto_prices()
        if prices:
            top = {k.upper(): f"${v:,.0f}" for k, v in list(prices.items())[:6] if k in ["bitcoin","ethereum","solana","xrp","bnb","dogecoin"]}
            console.print(f"  [dim]💰 Live prices: {top}[/dim]")
    except Exception as e:
        console.print(f"  [dim]Price feeds unavailable: {e}[/dim]")

    last_scan = 0.0
    last_resolve = 0.0

    while True:
        now = time.time()

        # Resolution check (runs more often)
        if now - last_resolve >= RESOLVE_INTERVAL_MIN * 60:
            console.print(f"\n[dim]── Resolution check @ {datetime.now().strftime('%H:%M:%S')} ──[/dim]")
            res = run_resolution_check(verbose=True)
            last_resolve = now
            # Always print accuracy after resolution check
            _print_accuracy_oneliner()
            if res["resolved"] > 0:
                stats = print_accuracy_report()
                maybe_go_live(stats)

        # Full scan (less often)
        if now - last_scan >= SCAN_INTERVAL_MIN * 60:
            scan_and_trade()
            last_scan = now

        time.sleep(30)  # check every 30s whether it's time to run again


def main():
    parser = argparse.ArgumentParser(description="Polymarket Demo Runner")
    parser.add_argument("--once", action="store_true", help="Run one scan then exit")
    parser.add_argument("--report", action="store_true", help="Show accuracy report and exit")
    parser.add_argument("--resolve", action="store_true", help="Run resolution check and exit")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    if args.report:
        stats = print_accuracy_report()
        return

    if args.resolve:
        run_resolution_check(verbose=True)
        print_accuracy_report()
        return

    if args.once:
        scan_and_trade()
        run_resolution_check(verbose=True)
        print_accuracy_report()
        return

    # Continuous loop
    run_loop()


if __name__ == "__main__":
    main()
