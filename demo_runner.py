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
from scraper import scrape_all
from classifier import classify, research_market, Classification
from matcher import match_news_to_markets
from edge import detect_edge_v2, Signal
from news_stream import NewsEvent
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
    Void trades that were logged before DEMO_HOURS_WINDOW was set to 24h.
    Only voids trades older than 2 hours that have no market_id or whose
    market_question contains known season-long keywords.
    Does NOT touch recently logged trades.
    """
    import sqlite3
    from pathlib import Path as _Path
    db = _Path(os.getenv("DB_PATH", "/data/trades.db"))
    if not db.exists():
        return
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row

    # Only consider trades logged more than 2 hours ago (not fresh ones)
    old_cutoff = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    rows = conn.execute(
        "SELECT id, market_id, market_question, created_at FROM trades "
        "WHERE status IN ('demo','dry_run') AND created_at < ?",
        (old_cutoff,)
    ).fetchall()

    if not rows:
        console.print(f"  [dim]Startup cleanup: no old trades to check.[/dim]")
        conn.close()
        return

    console.print(f"\n[bold]Startup cleanup:[/bold] checking {len(rows)} old trades (>2h)...")

    JUNK_KW = [
        # Season-long futures
        "2027", "world series", "french open", "wimbledon", "us open",
        "nba champion", "nba finals", "super bowl", "afc champion", "nfc champion",
        "eurovision", "lpl 2026 season", "ipl champion", "grammy", "oscar",
        "nobel", "governor 2026", "senator 2026", "president", "fed chair",
        "confirmed as", "rbc heritage", "masters 2026", "tour de france",
        # Sports win/loss coin flips
        "nfl", "nhl playoff", "art ross", "clutch player of the year",
        "coach of the year", "top goal scorer", "most assists",
        "will the new york yankees", "will los angeles chargers",
        "will macklin celebrini", "will omar marmoush", "will morgan rogers",
        "will yoane wissa", "will joe mazzulla", "will anthony edwards",
        "will the columbus blue jackets",
        "will sunderland finish", "will wolverhampton",
        "will qingdao", "will fc nordsjælland", "will viborg",
        # Esports maps
        "map 1 winner", "map 2 winner", "map 3 winner", "(bo1)", "(bo3)",
        "kills over", "kills under", "nodwin", "counter-strike",
        # Sports match results (short-dated but still coin flips)
        "o/u 2.5", "o/u 3.5", "o/u 4.5", "o/u 1.5",
        "both teams to score", "halftime result", "leading at halftime",
        # Celebrity/entertainment
        "justin bieber", "taylor swift", "feature ", "album drop",
        "box office", "weekend gross",
    ]

    void_ids = []
    for r in rows:
        q = r["market_question"].lower()
        if any(k in q for k in JUNK_KW):
            void_ids.append(r["id"])
            console.print(f"  VOID #{r['id']}: {r['market_question'][:65]}")

    if void_ids:
        conn.execute(
            f"UPDATE trades SET status='voided' WHERE id IN ({','.join('?'*len(void_ids))})",
            void_ids,
        )
        conn.commit()
        console.print(f"  [green]Voided {len(void_ids)} long-dated trades.[/green]")
    else:
        console.print(f"  [dim]All old trades look fine — nothing voided.[/dim]")
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


def _news_item_to_event(news_item) -> NewsEvent:
    """Convert a scraper NewsItem into a NewsEvent for the V2 pipeline."""
    now = datetime.now(timezone.utc)
    age_secs = int(news_item.age_hours() * 3600)
    published = now - timedelta(seconds=age_secs)
    return NewsEvent(
        headline=news_item.headline,
        source=news_item.source,
        url=getattr(news_item, "url", ""),
        received_at=now,
        published_at=published,
        summary=getattr(news_item, "summary", ""),
        latency_ms=age_secs * 1000,
    )


def scan_and_trade() -> dict:
    """
    One full scan cycle using the FULL V2 analysis engine:
      News → Match → Analyst+Skeptic Consensus → RRF Composite → Demo trade
    """
    console.print("\n[bold cyan]── Demo Scan (Full V2 Analysis) ───────────[/bold cyan]")
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    consensus_tag = f"consensus={'ON' if config.CONSENSUS_ENABLED else 'OFF'} passes={config.CONSENSUS_PASSES}"
    console.print(f"  {now_str}  |  ≤{DEMO_HOURS_WINDOW:.0f}h window  |  {consensus_tag}  |  model={config.LLM_PROVIDER}")

    # Show accuracy at the top of every scan
    _print_accuracy_oneliner()

    # 1. News scraping (Polycool removed — leaderboard used instead)
    console.print("\n[bold]1. Scraping news...[/bold]")
    bot_markets: list = []  # Polycool disabled; placeholder for polycool_signal()
    def polycool_signal(_q, _mkts): return None  # no-op stub

    news_items = scrape_all(config.NEWS_LOOKBACK_HOURS)
    # Count by source type
    rss_count     = sum(1 for n in news_items if not n.source.startswith("Reddit") and n.source != "Hacker News" and n.source != "CryptoPanic" and n.source != "Twitter")
    reddit_count  = sum(1 for n in news_items if n.source.startswith("Reddit"))
    hn_count      = sum(1 for n in news_items if n.source == "Hacker News")
    crypto_count  = sum(1 for n in news_items if n.source == "CryptoPanic")
    twitter_count = sum(1 for n in news_items if n.source == "Twitter")
    console.print(
        f"   {len(news_items)} headlines "
        f"[dim](RSS:{rss_count} Reddit:{reddit_count} HN:{hn_count} "
        f"CryptoPanic:{crypto_count} Twitter:{twitter_count})[/dim]"
    )

    # 2. Markets
    console.print("\n[bold]2. Fetching live markets...[/bold]")
    all_markets = fetch_active_markets(limit=2000)
    category_filtered = filter_by_categories(all_markets)
    window_markets = filter_closing_soon(category_filtered, DEMO_HOURS_WINDOW)
    now = datetime.now(timezone.utc)
    day_markets, skipped = filter_quality_markets(window_markets, now)

    console.print(
        f"   {len(all_markets)} total → {len(category_filtered)} in categories "
        f"→ {len(window_markets)} in {DEMO_HOURS_WINDOW:.0f}h window "
        f"→ [bold yellow]{len(day_markets)} quality markets[/bold yellow] "
        f"[dim](dropped: {skipped['too_soon']} too-soon, {skipped['price_extreme']} price-extreme, "
        f"{skipped['low_volume']} low-vol, {skipped['micro_window']} micro-window, {skipped['weather']} weather)[/dim]"
    )

    if not day_markets:
        console.print("   [yellow]No quality markets found this scan.[/yellow]")
        return {"markets": 0, "signals": 0, "demos_logged": 0}

    # Sort by closing time — soonest first so fast-resolving markets get priority
    # This means accuracy shows up much faster (hours not days)
    now = datetime.now(timezone.utc)
    def _hours_left(m):
        end = _parse_end_date(m.end_date)
        return (end - now).total_seconds() / 3600 if end else 9999
    day_markets.sort(key=_hours_left)

    # Print the shortlist
    now = datetime.now(timezone.utc)
    table = Table(title=f"1-Day Markets ({len(day_markets)} found)", show_header=True, header_style="bold magenta")
    table.add_column("#", width=3)
    table.add_column("Question", no_wrap=False, max_width=52)
    table.add_column("YES", justify="right", width=5)
    table.add_column("Vol $", justify="right", width=10)
    table.add_column("Closes In", justify="right", width=9)
    for i, m in enumerate(day_markets[:20], 1):
        end = _parse_end_date(m.end_date)
        hours_left = ((end - now).total_seconds() / 3600) if end else 0
        table.add_row(str(i), m.question[:52], f"{m.yes_price:.2f}", f"${m.volume:,.0f}", f"{hours_left:.1f}h")
    console.print(table)

    # 3. TWO-TRACK ANALYSIS:
    #   TRACK 1 — Fast markets (≤24h): research_market() with Gemini live search — no news needed
    #   TRACK 2 — Slow markets (>24h): news matching + classify() (existing approach)

    MAX_FAST = int(os.getenv("MAX_FAST_PER_SCAN", "80"))   # research up to 80 fast markets
    MAX_SLOW = int(os.getenv("MAX_PAIRS_PER_SCAN", "25"))  # keep top 25 slow news pairs

    already_logged = get_pending_market_ids()

    fast_markets = [m for m in day_markets if _hours_left(m) <= 24 and m.condition_id not in already_logged]
    # Priority: fastest-ending first (they resolve soonest → fastest feedback + most urgent)
    fast_markets.sort(key=lambda m: _hours_left(m))
    slow_markets = [m for m in day_markets if _hours_left(m) > 24 and m.condition_id not in already_logged]

    console.print(
        f"\n[bold]3. Two-Track Analysis:[/bold] "
        f"⚡ {len(fast_markets)} fast (≤24h, Gemini search) | "
        f"📅 {len(slow_markets)} slow (>24h, news match)"
    )

    signals_found: list[Signal] = []
    demos_logged = 0
    analyzed = 0

    # ══════════════════════════════════════════════════════════════════════════
    # UNIFIED SIGNAL ENGINE
    # Every market goes through ALL signal sources. Each source votes.
    # Final score = weighted combination. One bet per market. No duplicates.
    #
    # Signal sources (all considered together):
    #   S1: CLOB price   — crowd consensus (how confident is the market?)
    #   S2: Live price   — CoinGecko math (is threshold already crossed?)
    #   S3: Gemini 2.5   — AI research (what does live web search say?)
    #   S4: Whale signal — smart money direction
    #
    # Scoring weights:
    #   S2 (price feed) = 0.40  ← most reliable, pure math
    #   S3 (Gemini)     = 0.35  ← research quality
    #   S1 (CLOB)       = 0.15  ← crowd wisdom
    #   S4 (whale)      = 0.10  ← smart money
    #
    # Sweet spot bonus: if market price 0.35-0.65, multiply EV by 2x
    # (same confidence but earns 2x more per share)
    # ══════════════════════════════════════════════════════════════════════════

    from price_feeds import verify_crypto_market, get_all_crypto_prices
    from orderbook import fetch_book
    from whale import bulk_whale_signals, copy_trade_signal
    from leaderboard import build_copy_signals
    from matcher import match_news_to_markets
    from classifier import classify

    # Pre-fetch all crypto prices once (cache for whole scan)
    try:
        get_all_crypto_prices()
    except Exception:
        pass

    # Build token map
    token_map = {}
    all_candidates = [m for m in day_markets if m.condition_id not in already_logged]
    for m in all_candidates:
        if m.tokens and isinstance(m.tokens, list) and m.tokens:
            t = m.tokens[0]
            tid = t.get("token_id") if isinstance(t, dict) else str(t)
            if tid:
                token_map[m.condition_id] = tid

    # Pre-match news to markets (used as Gemini fallback when 429)
    news_map: dict[str, list] = {}
    try:
        _news_ev = [_news_item_to_event(n) for n in news_items]
        pairs = match_news_to_markets(_news_ev, all_candidates, top_k=5)
        for market, headlines in pairs:
            news_map[market.condition_id] = headlines
        log.info(f"[engine] News pre-matched {len(news_map)} markets")
    except Exception as e:
        log.warning(f"[engine] News matching failed: {e}")

    # Batch whale signals for all candidates
    all_ids = [m.condition_id for m in all_candidates[:100]]
    try:
        whale_map = bulk_whale_signals(all_ids[:30], token_map=token_map)
    except Exception:
        whale_map = {}
    try:
        copy_map = build_copy_signals(set(all_ids), top_n=20)
    except Exception:
        copy_map = {}

    console.print(f"\n[bold cyan]🔮 UNIFIED ENGINE: scoring {len(all_candidates)} markets across all signals[/bold cyan]")

    MAX_MARKETS = int(os.getenv("MAX_MARKETS_PER_SCAN", "120"))

    for market in all_candidates[:MAX_MARKETS]:
        analyzed += 1
        q_lower = market.question.lower()

        # Hard blocklist — always skip
        HARD_SKIP = [
            "win on 2026", "win on april", "win on 2025",
            "will sc ", "will cf ", "will fc ", "will cd ", "will ca ",
            "will ac ", "will as ", "(bo1)", "(bo3)",
            "map 1 winner", "map 2 winner", "map 3 winner",
            "both teams to score", "leading at halftime", "half time",
            "o/u 2.5", "o/u 3.5", "o/u 4.5", "o/u 1.5",
            "spread:", "correct score", "exact score",
            "total kills", "first blood", "first tower",
            "end in a draw", "posts from",
            "world series", "super bowl", "stanley cup",
            "art ross", "clutch player", "coach of the year",
            "top goal scorer", "most assists",
            "nfl afc", "nfl nfc", "nba finals", "nhl playoffs",
            "french open", "wimbledon", "lpl 2026",
            "justin bieber", "taylor swift", "box office",
            # Unpredictable direction questions — skip always
            "up or down", "opens up or down", "up or down on",
            "up or down -", "up or down –",
            # Esports / gaming — unpredictable, no news coverage
            "game 1 winner", "game 2 winner", "game 3 winner",
            "game 4 winner", "game 5 winner",
            "quadra kill", "penta kill", "first blood", "first baron",
            "dota 2", "valorant", "counter-strike", "league of legends",
            "any player", "dragon soul", "inhibitor",
        ]
        if any(pat in q_lower for pat in HARD_SKIP):
            continue

        # Soft blocklist — skip markets we absolutely cannot research
        CANT_RESEARCH = [
            # Micro esports in-game events (no news exists)
            "quadra kill", "penta kill", "first blood", "first baron", "first tower",
            "inhibitor", "dragon soul", "any player",
            # Pure player props without team context
            "points o/u", "assists o/u", "rebounds o/u",
            # Weather (no edge)
            "temperature", "rainfall", "snow",
        ]
        if any(pat in q_lower for pat in CANT_RESEARCH):
            continue

        hours_left = _hours_left(market)
        price = market.yes_price  # crowd's current probability
        tok = token_map.get(market.condition_id)

        # ── S1: CLOB crowd price → base direction + confidence ───────────
        # The market price IS the crowd's probability estimate.
        # THREE tiers by price — priority order:
        # TIER 1 (BEST): 0.45-0.55 → near 1:1 payout, win $1 per $1 bet
        # TIER 2 (GOOD): 0.35-0.45 or 0.55-0.65 → 1.2x-1.9x payout
        # TIER 3 (OK):   0.72-0.92 or 0.08-0.28 → crowd confident, small payout
        clob_dir = "neutral"
        clob_conf = 0.0
        is_tier1  = 0.45 <= price <= 0.55   # near 1:1 payout — BEST
        is_tier2  = (0.35 <= price < 0.45) or (0.55 < price <= 0.65)
        is_sweet  = is_tier1 or is_tier2

        if 0.72 <= price <= 0.92:
            clob_dir  = "bullish"
            clob_conf = price
        elif 0.08 <= price <= 0.28:
            clob_dir  = "bearish"
            clob_conf = 1.0 - price
        elif is_sweet:
            clob_conf = 0.10  # uncertain — other signals provide direction
        else:
            continue  # dead zone — skip

        # ── S2: Live price feed (CoinGecko) — pure math, highest weight ──
        price_feed_dir  = "neutral"
        price_feed_conf = 0.0
        try:
            pf = verify_crypto_market(market.question)
            if pf:
                if pf["confidence"] >= 0.55:
                    price_feed_dir  = pf["direction"]
                    price_feed_conf = pf["confidence"]
                    log.info(f"[pricefeed] {market.question[:50]} → {pf['direction']} {pf['confidence']:.0%} (${pf.get('current_price',0):,.0f} vs ${pf.get('threshold',0):,.0f})")
                else:
                    log.debug(f"[pricefeed] Low conf {pf['confidence']:.0%} for {market.question[:40]}")
            else:
                log.debug(f"[pricefeed] No signal for {market.question[:40]}")
        except Exception as e:
            log.debug(f"[pricefeed] Error: {e}")

        # ── S3: Research signal — Gemini web search first, news-match fallback
        gemini_dir  = "neutral"
        gemini_conf = 0.0
        if hours_left <= 72:
            try:
                cl = research_market(market)
                if cl.direction != "neutral" and cl.materiality >= 0.35:
                    gemini_dir  = cl.direction
                    gemini_conf = cl.materiality
            except Exception:
                pass
            # Fallback: if Gemini gave nothing, use RSS news matching via Groq/classify
            if gemini_dir == "neutral":
                matched_headlines = news_map.get(market.condition_id, [])
                if matched_headlines:
                    try:
                        cl2 = classify(market, matched_headlines)
                        if cl2.direction != "neutral" and cl2.materiality >= 0.30:
                            gemini_dir  = cl2.direction
                            gemini_conf = cl2.materiality * 0.85  # slight discount vs live search
                            log.info(f"[engine] News-match signal {market.question[:40]}: {cl2.direction} {cl2.materiality:.2f}")
                    except Exception:
                        pass

        # ── S4: Whale / leaderboard signal ───────────────────────────────
        whale_dir  = "neutral"
        whale_conf = 0.0
        whale_sig  = whale_map.get(market.condition_id)
        if whale_sig and whale_sig.direction != "neutral":
            whale_dir  = whale_sig.direction
            whale_conf = min(0.65, abs(whale_sig.yes_bias - 0.5) * 2)
        lb_sig = copy_map.get(market.condition_id)
        if lb_sig and lb_sig.get("direction","neutral") != "neutral":
            whale_dir  = lb_sig["direction"]
            whale_conf = max(whale_conf, min(0.65, lb_sig.get("confidence", 0.5)))

        # ── Weighted score combination ────────────────────────────────────
        # For high-confidence CLOB markets: crowd IS the best signal
        # For sweet spot: Gemini + price feed must provide direction
        if clob_dir != "neutral":
            # High-confidence zone — CLOB gets biggest weight
            W_PRICE, W_GEMINI, W_CLOB, W_WHALE = 0.35, 0.30, 0.25, 0.10
        else:
            # Sweet spot — Gemini + price feed must decide direction
            W_PRICE, W_GEMINI, W_CLOB, W_WHALE = 0.45, 0.40, 0.05, 0.10

        score_bull = 0.0
        score_bear = 0.0
        if price_feed_dir == "bullish":  score_bull += W_PRICE * price_feed_conf
        elif price_feed_dir == "bearish": score_bear += W_PRICE * price_feed_conf
        if gemini_dir == "bullish":      score_bull += W_GEMINI * gemini_conf
        elif gemini_dir == "bearish":    score_bear += W_GEMINI * gemini_conf
        if clob_dir == "bullish":        score_bull += W_CLOB * clob_conf
        elif clob_dir == "bearish":      score_bear += W_CLOB * clob_conf
        if whale_dir == "bullish":       score_bull += W_WHALE * whale_conf
        elif whale_dir == "bearish":     score_bear += W_WHALE * whale_conf

        # ══════════════════════════════════════════════════════════════════
        # KILL GATES — applied BEFORE final score
        # Sweet/1:1 markets need STRICTER gates because crowd is uncertain
        # (no free CLOB confidence to lean on — must earn the edge ourselves)
        # ══════════════════════════════════════════════════════════════════

        # Gate A: Hard conflict — price feed vs Gemini disagree → always skip
        if (price_feed_dir != "neutral" and gemini_dir != "neutral"
                and price_feed_dir != gemini_dir):
            console.print(f"  [dim]⚡ CONFLICT skip: {market.question[:45]}[/dim]")
            continue

        # Gate B: Contra-crowd — only skip if price feed is NOT backing our signal
        # Exception: if price feed is very confident (>= 0.75), allow contra-crowd bet
        # (mathematical evidence > crowd consensus)
        if clob_dir == "bearish" and score_bull > score_bear:
            if price_feed_conf < 0.75 or price_feed_dir != "bullish":
                console.print(f"  [dim]⚡ CONTRA-CROWD skip: {market.question[:40]}[/dim]")
                continue
        if clob_dir == "bullish" and score_bear > score_bull:
            if price_feed_conf < 0.75 or price_feed_dir != "bearish":
                console.print(f"  [dim]⚡ CONTRA-CROWD skip: {market.question[:40]}[/dim]")
                continue

        # Gate C: Tier 1 (1:1) — need price feed OR Gemini strong
        # Price feed alone at ≥0.65 is sufficient (e.g. ETH $1,580 vs $2,355 threshold = 87% NO)
        if is_tier1:
            strong_price  = price_feed_conf >= 0.65 and price_feed_dir != "neutral"
            strong_gemini = gemini_conf >= 0.60 and gemini_dir != "neutral"
            both_agree    = (price_feed_dir == gemini_dir and
                             price_feed_dir != "neutral" and
                             price_feed_conf >= 0.50 and gemini_conf >= 0.50)
            if not (strong_price or strong_gemini or both_agree):
                console.print(f"  [dim]💎 1:1 needs signal (pf:{price_feed_conf:.0%} gem:{gemini_conf:.0%}) skip: {market.question[:35]}[/dim]")
                continue

        # Gate D: Tier 2 (sweet) — need at least one signal ≥ 0.55
        elif is_sweet:
            strong_price  = price_feed_conf >= 0.55 and price_feed_dir != "neutral"
            strong_gemini = gemini_conf >= 0.50 and gemini_dir != "neutral"
            if not (strong_price or strong_gemini):
                console.print(f"  [dim]💎 Sweet needs signal (pf:{price_feed_conf:.0%} gem:{gemini_conf:.0%}) skip: {market.question[:35]}[/dim]")
                continue

        # Gate E: Tier 3 (crowd-confident) — Gemini or price feed must agree with crowd
        else:
            if price_feed_conf < 0.45 and gemini_conf < 0.40:
                console.print(f"  [dim]⚡ Crowd confident but no research confirmation skip[/dim]")
                continue

        # ── Final direction ───────────────────────────────────────────────
        MIN_SCORE = 0.20 if is_tier1 else (0.18 if is_sweet else 0.15)
        if score_bull >= score_bear and score_bull >= MIN_SCORE:
            final_dir, final_side, raw_score = "bullish", "YES", score_bull
        elif score_bear > score_bull and score_bear >= MIN_SCORE:
            final_dir, final_side, raw_score = "bearish", "NO",  score_bear
        else:
            console.print(f"  [dim]Score too low ({max(score_bull,score_bear):.2f} < {MIN_SCORE}) skip[/dim]")
            continue

        # ── Normalize raw_score → probability estimate ────────────────────
        # raw_score is a weighted sum of (confidence × weight) for active signals.
        # Dividing by sum of active weights gives actual probability estimate.
        active_w = 0.0
        if price_feed_dir != "neutral": active_w += W_PRICE
        if gemini_dir    != "neutral": active_w += W_GEMINI
        if clob_dir      != "neutral": active_w += W_CLOB
        if whale_dir     != "neutral": active_w += W_WHALE
        if active_w < 0.01: active_w = W_CLOB  # fallback
        final_score = min(0.97, raw_score / active_w)  # normalized probability

        # ── EV gate ───────────────────────────────────────────────────────
        bet_price    = price if final_side == "YES" else (1.0 - price)
        payout_ratio = (1.0 - bet_price) / bet_price
        ev_per_dollar = final_score * payout_ratio - (1.0 - final_score)

        # Min EV: sweet=0.04, tier3=0.005 (small positive edge sufficient for crowd-aligned tier3)
        min_ev = 0.04 if is_sweet else 0.005
        if ev_per_dollar < min_ev:
            console.print(f"  [dim]EV={ev_per_dollar:.3f} < {min_ev} skip: {market.question[:40]}[/dim]")
            continue

        # ── Bet sizing ────────────────────────────────────────────────────
        from bankroll import kelly_bet_size, get_current_bankroll, can_trade_today
        allowed, reason = can_trade_today()
        if not allowed:
            console.print(f"  [red]⛔ {reason}[/red]")
            break
        bk = get_current_bankroll()

        edge = final_score - bet_price
        bet = kelly_bet_size(bk, max(edge, 0.03), bet_price, materiality=final_score)

        # Bet sizing by tier:
        # Tier 1 (0.45-0.55, near 1:1 payout): biggest bet — best risk/reward
        # Tier 2 (0.35-0.65): good payout — larger bet
        # Tier 3 (crowd confident): smaller bet — small payout
        if is_tier1:
            bet = min(bet * 2.0, bk * 0.08)  # 8% cap — best payout tier
            spot_tag = "💎1:1"
        elif is_sweet:
            bet = min(bet * 1.8, bk * 0.07)  # 7% cap
            spot_tag = "💎SWEET"
        elif final_score >= 0.75:
            bet = min(bet * 1.5, bk * 0.06)  # sureshot
            spot_tag = "🎯SURE"
        else:
            bet = min(bet, bk * 0.05)
            spot_tag = "⚡STD"

        bet = round(max(0.50, bet), 2)

        # Signal sources summary
        sources = []
        if price_feed_conf >= 0.65: sources.append(f"💰LivePrice:{price_feed_conf:.0%}")
        if gemini_conf >= 0.55:     sources.append(f"🤖Gemini:{gemini_conf:.0%}")
        if clob_conf >= 0.60:       sources.append(f"📊CLOB:{clob_conf:.0%}")
        if whale_conf >= 0.40:      sources.append(f"🐋Whale:{whale_conf:.0%}")

        win_profit = round(bet * payout_ratio, 2)
        loss_cost  = round(bet, 2)
        console.print(
            f"  [bold green]{spot_tag}[/bold green] "
            f"[bold]{final_side}[/bold] | "
            f"price:{price:.2f} payout:{payout_ratio:.1f}x | "
            f"WIN:+${win_profit} LOSE:-${loss_cost} | "
            f"score:{final_score:.2f} ev:+${ev_per_dollar*bet:.2f} | "
            f"closes:{hours_left:.1f}h\n"
            f"    {' + '.join(sources) if sources else 'multi-signal'}\n"
            f"    \"{market.question[:65]}\""
        )

        from edge import Signal as _Signal
        unified_signal = _Signal(
            market=market,
            claude_score=final_score,
            market_price=price,
            edge=max(edge, 0.03),
            side=final_side,
            bet_amount=bet,
            reasoning=(
                f"[Unified] score={final_score:.2f} ev={ev_per_dollar:.3f}/$ | "
                + " | ".join(sources)
            ),
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
        console.print(f"    → [green]Trade #{trade_id} logged (${bet:.2f} virtual, EV:+{ev_per_dollar*bet:.3f}$)[/green]")

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
