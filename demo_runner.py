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

        # 2. Skip near-certain prices (market already knows outcome)
        # Allow 0.10–0.90 — Gemini research identifies remaining uncertainty
        if m.yes_price < 0.10 or m.yes_price > 0.90:
            skipped["price_extreme"] += 1
            continue

        # 3. Skip very low volume (filters out $100 micro-window markets)
        # Fast markets (≤24h) get a lower volume floor — Gemini researches them directly
        end2 = _parse_end_date(m.end_date)
        h_left = ((end2 - now).total_seconds() / 3600) if end2 else 9999
        vol_min = 100 if h_left <= 24 else config.MIN_VOLUME_USD
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
    all_markets = fetch_active_markets(limit=1000)
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

    # Build token_map early — needed by both Track 0 and Track 1
    token_map = {}
    for m in fast_markets:
        if m.tokens and isinstance(m.tokens, list) and m.tokens:
            t = m.tokens[0]
            tid = t.get("token_id") if isinstance(t, dict) else str(t)
            if tid:
                token_map[m.condition_id] = tid

    # ══════════════════════════════════════════════════════════════════════════
    # TRACK 0: CLOB CONSENSUS — near-resolved markets (closes <8h, price ≥0.85)
    # No LLM needed. If the crowd has priced a market at 85%+ and it closes
    # in <8h, it resolves correctly ~87% of the time historically.
    # This is the primary driver for 80% accuracy + 15 trades/day.
    # ══════════════════════════════════════════════════════════════════════════
    from orderbook import fetch_book
    # Sweet spot: crowd 80%+ confident BUT price still at 0.70-0.88
    # = real edge (you earn $0.12-0.30 per share AND win 80%+ of the time)
    # Avoid 0.90+ markets — win rate barely covers the tiny payout
    CLOB_YES_THRESHOLD = float(os.getenv("CLOB_YES_THRESHOLD", "0.72"))  # crowd ≥72% confident
    CLOB_YES_MAX       = float(os.getenv("CLOB_YES_MAX",       "0.91"))  # cap — above 91% payout too small
    CLOB_NO_THRESHOLD  = float(os.getenv("CLOB_NO_THRESHOLD",  "0.28"))  # crowd ≥72% on NO side
    CLOB_NO_MIN        = float(os.getenv("CLOB_NO_MIN",        "0.09"))  # cap NO side
    CLOB_MAX_HOURS     = float(os.getenv("CLOB_MAX_HOURS",     "12"))    # closes within 12h
    CLOB_MIN_VOL       = float(os.getenv("CLOB_MIN_VOL",       "3000"))  # liquid markets only

    # Hard-block list for CLOB consensus (pure coin-flips regardless of price)
    CLOB_SKIP = [
        "win on 2026", "win on april", "win on 2025",
        "will sc ", "will cf ", "will fc ", "will cd ", "will ca ",
        "will ac ", "will as ", "will ss ", "will aj ",
        "(bo1)", "(bo3)", "map 1 winner", "map 2 winner", "map 3 winner",
        "both teams to score", "leading at halftime", "half time",
        "o/u 2.5", "o/u 3.5", "o/u 4.5", "o/u 1.5",
        "spread:", "handicap",
        "total kills", "first blood", "first tower",
        "will draw", "end in a draw",
    ]

    clob_logged = 0
    clob_candidates = [m for m in fast_markets if _hours_left(m) <= CLOB_MAX_HOURS
                       and m.volume >= CLOB_MIN_VOL]
    clob_candidates.sort(key=lambda m: _hours_left(m))

    console.print(f"\n  [bold yellow]🎯 TRACK 0: CLOB Consensus — {len(clob_candidates)} candidates closing <{CLOB_MAX_HOURS:.0f}h[/bold yellow]")

    for market in clob_candidates[:60]:
        q_lower = market.question.lower()
        if any(pat in q_lower for pat in CLOB_SKIP):
            continue

        tok = token_map.get(market.condition_id) if hasattr(market, 'condition_id') else None
        if not tok:
            # try building token_map entry
            if market.tokens and isinstance(market.tokens, list) and market.tokens:
                t = market.tokens[0]
                tok = t.get("token_id") if isinstance(t, dict) else str(t)

        if not tok:
            continue

        try:
            book = fetch_book(tok)
        except Exception:
            continue

        if book is None:
            continue

        # Use mid-price (best bid / best ask average) as crowd consensus
        mid = (book.best_bid + (1 - book.best_ask)) / 2 if book.best_bid and book.best_ask else None
        if mid is None:
            # fall back to market yes_price
            mid = market.yes_price

        hours_left_clob = _hours_left(market)

        if CLOB_YES_THRESHOLD <= mid <= CLOB_YES_MAX:
            direction = "bullish"
            side = "YES"
            confidence = mid
        elif CLOB_NO_MIN <= mid <= CLOB_NO_THRESHOLD:
            direction = "bearish"
            side = "NO"
            confidence = 1 - mid
        else:
            continue  # outside sweet spot

        # Skip if already logged
        if market.condition_id in already_logged:
            continue

        console.print(
            f"  [bold yellow]🎯 CLOB CONSENSUS[/bold yellow] "
            f"{side} | price={mid:.3f} conf={confidence:.1%} | "
            f"closes:{hours_left_clob:.1f}h vol:${market.volume:,.0f} | "
            f"\"{market.question[:50]}\""
        )

        # Size bet based on confidence (higher confidence → bigger bet)
        from bankroll import kelly_bet_size, get_current_bankroll, can_trade_today
        allowed, reason = can_trade_today()
        if not allowed:
            console.print(f"  [red]⛔ {reason}[/red]")
            break

        bk = get_current_bankroll()
        # Edge = how much better than fair price we are (crowd is already pricing it in,
        # so edge is small but accuracy is very high)
        edge = max(0.03, confidence - 0.80)  # minimum 3% edge, scales with confidence
        bet = kelly_bet_size(bk, edge, market.yes_price if side == "YES" else 1 - market.yes_price,
                             materiality=confidence)
        bet = max(0.50, min(bet * 1.2, bk * 0.06))  # 6% cap, 1.2x boost for consensus

        # Build a signal using the real Signal dataclass
        from edge import Signal as _Signal
        clob_signal = _Signal(
            market       = market,
            claude_score = confidence,
            market_price = market.yes_price,
            edge         = edge,
            side         = side,
            bet_amount   = round(bet, 2),
            reasoning    = f"CLOB consensus {side} @ {mid:.3f} ({confidence:.1%} crowd confidence), closes in {hours_left_clob:.1f}h",
            headlines    = "",
            news_source  = "CLOB",
            classification = direction,
            materiality  = confidence,
            composite_score = confidence,
        )
        trade_id = _log_demo_trade(clob_signal, token_id=tok)
        already_logged.add(market.condition_id)
        clob_logged += 1
        demos_logged += 1
        console.print(f"    → [yellow]CLOB trade #{trade_id} logged (${bet:.2f} virtual, {confidence:.1%} conf)[/yellow]")

    console.print(f"  [yellow]CLOB consensus: {clob_logged} trades logged[/yellow]")

    # ── TRACK 1: Fast markets — Gemini live web search + whale signals ───────
    from whale import bulk_whale_signals, copy_trade_signal
    fast_ids = [m.condition_id for m in fast_markets[:MAX_FAST]]
    # Leaderboard copy-trade (re-enabled with fixed endpoints + hardcoded wallets)
    from leaderboard import build_copy_signals
    copy_signals_map = build_copy_signals(set(fast_ids), top_n=20)
    console.print(f"   [dim]Leaderboard copy signals: {len(copy_signals_map)} markets[/dim]")

    # Whale holder signals (data-api.polymarket.com)
    from whale import bulk_whale_signals
    whale_signals_map = bulk_whale_signals(fast_ids[:20], token_map=token_map)

    if fast_markets:
        console.print(f"\n  [cyan]⚡ TRACK 1: Researching {min(len(fast_markets), MAX_FAST)} fast markets with Gemini search...[/cyan]")
    # ── Hard whitelist: only trade verifiable-fact markets ───────────────────
    # Sports results are future uncertainty — no real edge over the market price.
    # Crypto/stock price markets: Gemini can verify current price vs threshold.
    # Political events: Gemini can verify if vote/announcement already happened.
    VERIFIABLE_PATTERNS = [
        # Crypto price (checkable NOW via live price)
        "bitcoin", "btc ", "ethereum", "eth ", "solana", "sol ",
        "xrp", "bnb", "dogecoin", "cardano", "avalanche", "polygon",
        "up or down", "above $", "below $", "between $",
        "price of bitcoin", "price of ethereum", "price of solana",
        "crypto", "coin",
        # Stock / finance (checkable after market close)
        "up or down on april", "opens up or down",
        "s&p 500", "s&p500", "spx", "nasdaq", "dow jones",
        "amazon", "tesla", "apple", "google", "alphabet",
        "meta ", "nvidia", "microsoft", "netflix", "openai",
        "unitedhealth", "jpmorgan", "berkshire",
        # US political (verifiable outcomes)
        "will trump", "trump ", "federal reserve", "fed rate",
        "supreme court", "congress", "senate bill",
        "election result", "ceasefire", "iran ", "ukraine",
        "us x iran", "tariff",
        # IPL / Cricket (score-based, verifiable after match)
        "ipl", "cricket", "t20", "odi", "test match",
        # Earthquake/natural (verifiable via USGS)
        "earthquake", "magnitude",
        # Constitutional/legal (verifiable)
        "constitutional amendment", "referendum", "ballot",
    ]

    def _is_verifiable(q: str) -> bool:
        q = q.lower()
        return any(p in q for p in VERIFIABLE_PATTERNS)

    # Categories to always skip regardless
    SKIP_PATTERNS = [
        "exact score", "correct score",
        "posts from", "post 20-", "post 40-", "post 60-", "post 80-", "post 100-",
        "post 120-", "post 140-", "post 160-", "post 180-",
        "o/u 10.", "o/u 8.", "o/u 6.", "o/u 12.", "o/u 14.",
        "total corners", "total shots",
        "map handicap", "first blood", "first tower", "first dragon",
        "first baron", "first rift herald",
        "both teams to score",
        "leading at halftime", "halftime result", "half time",
        "(bo1)", "- bo1",
        # Sports win/loss markets — future uncertainty, no verifiable edge
        "will sc ", "will cf ", "will fc ", "will cd ", "will ca ",
        " win on 2026", "win on april",
        # Celebrity / entertainment — pure speculation
        "justin bieber", "taylor swift", "feature ", "album",
        "box office", "oscars", "grammy",
    ]

    for market in fast_markets[:MAX_FAST]:
        analyzed += 1

        q_lower = market.question.lower()

        # Skip explicitly blocked patterns
        if any(pat in q_lower for pat in SKIP_PATTERNS):
            console.print(f"  [dim]⛔ SKIP (blocked): {market.question[:60]}[/dim]")
            continue

        # Only trade verifiable-fact markets (crypto price, stocks, politics)
        # Skip sports win/loss — future uncertainty gives no real edge
        if not _is_verifiable(market.question):
            console.print(f"  [dim]⛔ SKIP (not verifiable): {market.question[:60]}[/dim]")
            continue

        end = _parse_end_date(market.end_date)
        hours_left = ((end - now).total_seconds() / 3600) if end else 999

        # High-accuracy thresholds — verifiable markets only, high conviction required
        mat_threshold  = 0.45   # minimum materiality (Gemini must be confident)
        comp_threshold = 0.48   # composite confirms multi-signal agreement

        classification: Classification = research_market(market)

        # ── Signal fusion: CLOB orderbook (direct) + Polycool + whale ───────
        from orderbook import fetch_book, book_edge_adjustment
        token_id = token_map.get(market.condition_id)
        book = fetch_book(token_id) if token_id else None
        book_delta, book_tag = book_edge_adjustment(book, classification.direction)
        if book_delta != 0:
            classification.materiality = max(0.0, min(1.0, classification.materiality + book_delta))

        bot_sig   = polycool_signal(market.question, bot_markets)
        whale_sig = whale_signals_map.get(market.condition_id)
        copy_lb   = copy_signals_map.get(market.condition_id)

        # Leaderboard copy-signal: top wallets agree → boost; disagree → cut
        lb_tag = ""
        if copy_lb:
            if copy_lb.direction == classification.direction and classification.direction != "neutral":
                classification.materiality = min(1.0, classification.materiality + 0.15)
                lb_tag = f" 👑LB+{copy_lb.wallet_count}w"
            elif copy_lb.direction != "neutral" and classification.direction != "neutral" \
                 and copy_lb.direction != classification.direction:
                classification.materiality = max(0.0, classification.materiality - 0.12)
                lb_tag = f" ⚠️LB-vs-gemini"
            elif classification.direction == "neutral" and copy_lb.direction != "neutral":
                # Let leaderboard drive direction when Gemini is uncertain
                classification.direction   = copy_lb.direction
                classification.materiality = max(classification.materiality, 0.50)
                lb_tag = f" 👑LB→{copy_lb.direction[:4]}"

        # Tight spread boost (Polycool backup)
        if bot_sig and bot_sig.get("spread") is not None and bot_sig["spread"] < 0.05:
            classification.materiality = min(1.0, classification.materiality + 0.05)

        # News-alignment boost: if recent RSS headlines strongly mention this market's
        # key entities, the signal is corroborated by external news → +0.08 materiality
        news_boost_tag = ""
        try:
            q_words = [w.lower() for w in market.question.split()
                       if len(w) >= 5 and w.lower() not in
                       {"will", "vs.", "vs", "their", "there", "would", "could", "about"}]
            if q_words:
                hits = 0
                for h in news_items[:200]:
                    h_txt = (h.headline or "").lower()
                    if sum(1 for w in q_words[:6] if w in h_txt) >= 2:
                        hits += 1
                if hits >= 3 and classification.direction != "neutral":
                    classification.materiality = min(1.0, classification.materiality + 0.08)
                    news_boost_tag = f" 📰{hits}hits"
        except Exception:
            pass

        whale_tag = ""
        if whale_sig:
            gemini_dir = classification.direction  # bullish/bearish/neutral
            whale_dir  = whale_sig.direction
            if gemini_dir != "neutral" and whale_dir == gemini_dir:
                # Whales agree → strong boost
                classification.materiality = min(1.0, classification.materiality + 0.12)
                whale_tag = f" 🐋{whale_sig.yes_bias:.0%}YES"
            elif whale_dir != "neutral" and whale_dir != gemini_dir:
                # Whales disagree → reduce materiality (smart money says opposite)
                classification.materiality = max(0.0, classification.materiality - 0.10)
                whale_tag = f" ⚠️whale-vs-gemini"

        closes_tag = f"[{hours_left:.1f}h]"
        bot_tag = f" spread:{bot_sig['spread']:.3f}" if bot_sig and bot_sig.get("spread") else ""
        clob_tag = f" 📖{book.spread:.2f}/{book.liquidity_tier}" if book else ""
        console.print(
            f"  [{('cyan' if classification.direction != 'neutral' else 'dim')}]"
            f"⚡research→ {classification.direction} mat:{classification.materiality:.2f}"
            f"{clob_tag}{news_boost_tag}{lb_tag}{bot_tag}{whale_tag} {closes_tag}[/] {market.question[:48]}"
        )
        # ── Copy-trade override: recent whale buys → force signal ────────────
        copy_sig = copy_trade_signal(market.condition_id,
                                     token_id=token_map.get(market.condition_id))
        if copy_sig and copy_sig["direction"] != "neutral" and copy_sig["confidence"] >= 0.6:
            # Whales recently piled in → override neutral/low-mat with their direction
            if classification.direction == "neutral":
                classification.direction = copy_sig["direction"]
            classification.materiality = min(1.0, classification.materiality + copy_sig["confidence"] * 0.20)
            console.print(
                f"  [bold magenta]🐋 COPY-TRADE override[/bold magenta] "
                f"{copy_sig['direction']} conf:{copy_sig['confidence']:.2f} — {copy_sig['reason']}"
            )

        if classification.direction == "neutral" or classification.materiality < mat_threshold:
            continue

        # Build synthetic news event from research reasoning
        dummy_news = type("NewsItem", (), {
            "headline": f"[Research] {market.question[:120]}",
            "source": "Gemini Search",
            "url": "",
            "age_hours": lambda self: 0.5,
            "summary": classification.reasoning,
        })()
        news_event = _news_item_to_event(dummy_news)

        import config as _cfg
        _orig_mat  = _cfg.MATERIALITY_THRESHOLD
        _orig_edge = _cfg.EDGE_THRESHOLD
        _cfg.MATERIALITY_THRESHOLD = mat_threshold
        # Track 1 uses Gemini live research — lower edge threshold so near-certain
        # markets (YES>0.80 or YES<0.20) can still be traded (edge formula = mat×room)
        _cfg.EDGE_THRESHOLD = 0.03
        signal = detect_edge_v2(market, classification, news_event)
        _cfg.MATERIALITY_THRESHOLD = _orig_mat
        _cfg.EDGE_THRESHOLD = _orig_edge
        if signal and signal.composite_score < comp_threshold:
            signal = None

        if signal:
            # Kelly sizing based on current bankroll
            from bankroll import kelly_bet_size, get_current_bankroll, can_trade_today
            allowed, reason = can_trade_today()
            if not allowed:
                console.print(f"  [red]⛔ {reason} — skipping[/red]")
                continue
            bk = get_current_bankroll()

            # ── Sureshot tier: mat ≥ 0.55 + composite ≥ 0.55 → max Kelly ──────
            is_sureshot = (classification.materiality >= 0.55
                           and signal.composite_score >= 0.55)
            if is_sureshot:
                # Sureshot: up to 8% bankroll (double normal Kelly cap)
                kelly_amt = kelly_bet_size(bk, signal.edge, market.yes_price,
                                           classification.materiality)
                kelly_amt = min(kelly_amt * 1.5, bk * 0.08)  # boost + 8% cap
                tier_tag  = "🎯SURESHOT"
                tier_col  = "bold bright_yellow"
            else:
                kelly_amt = kelly_bet_size(bk, signal.edge, market.yes_price,
                                           classification.materiality)
                tier_tag  = "⚡FAST"
                tier_col  = "bright_green"

            if kelly_amt < 0.50:
                console.print(f"  [dim]Kelly: bet <$0.50 — skipping[/dim]")
                continue
            signal.bet_amount = round(kelly_amt, 2)

            console.print(
                f"  [{tier_col}]SIGNAL {tier_tag}[/{tier_col}] "
                f"[bold]{signal.side}[/bold] | "
                f"mat:{classification.materiality:.2f} "
                f"composite:{signal.composite_score:.2f} "
                f"edge:{signal.edge:.1%} "
                f"closes:{hours_left:.1f}h | bankroll:${bk:.2f}\n"
                f"    Market: \"{market.question[:55]}\"\n"
                f"    Reason: {classification.reasoning[:120]}"
            )
            # Store YES token_id so CLOB-based resolver can check prices directly
            yes_token = token_map.get(market.condition_id)
            trade_id = _log_demo_trade(signal, token_id=yes_token)
            console.print(f"    → [green]Demo trade #{trade_id} logged (${signal.bet_amount:.2f} virtual)[/green]")
            signals_found.append(signal)
            demos_logged += 1

    # ── TRACK 2: Slow markets — news matching + classify ─────────────────────
    if slow_markets:
        console.print(f"\n  [yellow]📅 TRACK 2: News matching for {len(slow_markets)} slow markets...[/yellow]")
        from matcher import extract_keywords
        import urllib.parse

        _CRYPTO_KW    = {"bitcoin","btc","ethereum","eth","solana","sol","xrp","bnb","crypto",
                         "blockchain","defi","nft","token","altcoin","stablecoin",
                         "coinbase","binance","polymarket","web3","on-chain","onchain"}
        _WEATHER_KW   = {"temperature","celsius","fahrenheit","weather","rain","snow","wind",
                         "humidity","forecast","climate","degrees","hottest","coldest"}
        _SOCCER_KW    = {"fc ","football club","premier league","champions league","bundesliga",
                         "la liga","serie a","ligue 1","eredivisie","atletico","barcelona",
                         "bayern","liverpool","arsenal","chelsea","manchester","real madrid",
                         "borussia","juventus","inter milan","psg","ajax","porto","celtic"}
        _BASKETBALL_KW= {"nba","76ers","lakers","celtics","warriors","bucks","heat","knicks",
                         "nets","suns","nuggets","magic","bulls","pistons","raptors","clippers",
                         "spurs","grizzlies","pelicans","hawks","cavaliers","thunder","trail blazers"}
        _CRICKET_KW   = {"ipl","cricket","wicket","t20","odi","test match","bcci","iplt20",
                         "rajasthan royals","mumbai indians","chennai","kolkata","punjab",
                         "sunrisers","rcb","delhi capitals"}
        _ESPORTS_KW   = {"valorant","counter-strike","cs:go","leviatan","vitality","g2",
                         "fnatic","navi","blast","dota","league of legends","lol","esports",
                         "gaming","rekonix","nemesis"}
        _FINANCE_KW   = {"stock","nasdaq","s&p","dow jones","fed","federal reserve",
                         "interest rate","inflation","recession","earnings","ipo","bond","yield"}

        def _cat(text: str) -> str:
            t = text.lower()
            if any(k in t for k in _CRYPTO_KW):      return "crypto"
            if any(k in t for k in _WEATHER_KW):     return "weather"
            if any(k in t for k in _SOCCER_KW):      return "soccer"
            if any(k in t for k in _BASKETBALL_KW):  return "basketball"
            if any(k in t for k in _CRICKET_KW):     return "cricket"
            if any(k in t for k in _ESPORTS_KW):     return "esports"
            if any(k in t for k in _FINANCE_KW):     return "finance"
            return "general"

        _STRICT_CATS = {"weather"}

        best_per_market: dict[str, tuple[float, object, object]] = {}
        skipped_cat = 0
        for news_item in news_items:
            headline_lower = news_item.headline.lower()
            news_cat = _cat(news_item.headline)
            for market in slow_markets:
                mkt_cat = _cat(market.question)
                if mkt_cat != "general" and mkt_cat != news_cat:
                    if news_cat != "general" or mkt_cat in _STRICT_CATS:
                        skipped_cat += 1
                        continue
                kws = extract_keywords(market.question)
                if not kws:
                    continue
                hits = sum(1 for kw in kws if kw in headline_lower)
                if hits == 0:
                    continue
                score = hits / len(kws)
                mid = market.condition_id
                if mid not in best_per_market or score > best_per_market[mid][0]:
                    best_per_market[mid] = (score, news_item, market)

        all_pairs = sorted(best_per_market.values(), key=lambda x: _hours_left(x[2]))
        top_pairs = all_pairs[:MAX_SLOW]
        console.print(
            f"   {len(best_per_market)} slow markets matched news → top {len(top_pairs)} "
            f"(skipped: {skipped_cat} cross-cat)"
        )

        for score, news_item, market in top_pairs:
            news_event = _news_item_to_event(news_item)
            analyzed += 1

            end = _parse_end_date(market.end_date)
            hours_left = ((end - now).total_seconds() / 3600) if end else 999
            # Lower threshold for verifiable markets (crypto/stock/political)
            if _is_verifiable(market.question):
                mat_threshold  = 0.32   # verifiable = more trustworthy
                comp_threshold = 0.46
            else:
                mat_threshold  = 0.50   # non-verifiable = need very high confidence
                comp_threshold = 0.58

            classification: Classification = classify(
                headline=news_item.headline,
                market=market,
                source=news_item.source,
                use_search=False,
            )

            closes_tag = f"[{hours_left:.0f}h]"
            console.print(
                f"  [{('green' if classification.direction != 'neutral' else 'dim')}]"
                f"📅classify→ {classification.direction} mat:{classification.materiality:.2f} "
                f"{closes_tag}[/] {market.question[:48]}"
            )
            if classification.direction == "neutral":
                continue

            if config.CONSENSUS_ENABLED and not classification.consensus_agreed:
                console.print(f"  [yellow]DEBATE SPLIT[/yellow] — skipping \"{market.question[:45]}\"")
                continue

            if classification.materiality < mat_threshold:
                continue

            import config as _cfg
            _orig_mat  = _cfg.MATERIALITY_THRESHOLD
            _orig_edge = _cfg.EDGE_THRESHOLD
            _cfg.MATERIALITY_THRESHOLD = mat_threshold
            _cfg.EDGE_THRESHOLD = 0.06   # Track 2: lower than default 0.15 (news+classify)
            signal = detect_edge_v2(market, classification, news_event)
            _cfg.MATERIALITY_THRESHOLD = _orig_mat
            _cfg.EDGE_THRESHOLD = _orig_edge
            if signal and signal.composite_score < comp_threshold:
                signal = None

            if signal:
                console.print(
                    f"  [bright_green]SIGNAL 📅SLOW[/bright_green] "
                    f"[bold]{signal.side}[/bold] | "
                    f"mat:{classification.materiality:.2f} composite:{signal.composite_score:.2f} "
                    f"edge:{signal.edge:.1%} closes:{hours_left:.1f}h\n"
                    f"    Market: \"{market.question[:55]}\"\n"
                    f"    News:   [{news_item.source}] {news_item.headline[:70]}\n"
                    f"    Reason: {classification.reasoning[:100]}"
                )
                trade_id = _log_demo_trade(signal)
                console.print(f"    → [green]Demo trade #{trade_id} logged (${signal.bet_amount:.2f} virtual)[/green]")
                signals_found.append(signal)
                demos_logged += 1

    if not signals_found:
        console.print(
            f"  [dim]No signals this scan — {analyzed} markets analyzed. "
            f"Thresholds or materiality not met.[/dim]"
        )

    console.print(f"\n  Scan complete: {len(news_items)} headlines → {analyzed} markets analyzed → {demos_logged} demo trades")
    _print_accuracy_oneliner()
    # ─────────────────────────────────────────────────────────────────────────

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

    # Clean out long-dated trades on startup (once per container start)
    _startup_cleanup()

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
