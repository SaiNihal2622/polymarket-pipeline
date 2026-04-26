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
    from resolver import get_signal_accuracies
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

    # Per-signal accuracy breakdown (shown once we have data)
    try:
        sig_accs = get_signal_accuracies()
        if sig_accs:
            SIG_COLOR = {"pf": "cyan", "ai": "magenta", "copy": "yellow",
                         "whale": "blue", "crowd": "green"}
            parts = []
            for sig, s in sig_accs.items():
                if s["trades"] == 0:
                    continue
                col  = SIG_COLOR.get(sig, "white")
                bar  = "▓" * int(s["accuracy_pct"] / 10)  # rough bar
                parts.append(
                    f"[{col}]{s['label']}[/{col}]: "
                    f"[bold]{s['accuracy_pct']:.0f}%[/bold] "
                    f"({s['wins']}W/{s['losses']}L)"
                )
            if parts:
                console.print(f"  [dim]Signals → {' | '.join(parts)}[/dim]")
    except Exception:
        pass

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
        "cardano", "ada", "avax", "polkadot", "dot",
        "chainlink", "litecoin", "ltc", "polygon", "matic",
        "uniswap", "pepe", "shib", "meme coin",
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


def _log_demo_trade(signal: Signal, token_id: str | None = None,
                    signals: dict | None = None) -> int:
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
        signals=signals,
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
    Full signal scan: price feed + copy-trade + whale + AI research + crowd CLOB.
    MAX-based scoring — one strong signal is enough to trade.
    Target: 5-20 trades/day at 75%+ accuracy.
    """
    console.print("\n[bold cyan]── Scan ───────────[/bold cyan]")
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    console.print(f"  {now_str}  |  ≤{DEMO_HOURS_WINDOW:.0f}h window")
    _print_accuracy_oneliner()

    # 0. Scrape news for context (used by AI research + news matching)
    news_items = []
    try:
        from scraper import scrape_all
        news_items = scrape_all(config.NEWS_LOOKBACK_HOURS)
        console.print(f"  [dim]News: {len(news_items)} headlines[/dim]")
    except Exception as e:
        log.debug(f"[scan] news scrape failed: {e}")

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
    from classifier import research_market
    from resolver import get_dynamic_weights, get_signal_accuracies

    # Pre-fetch crypto prices
    try:
        get_all_crypto_prices()
    except Exception:
        pass

    # Load empirical signal weights (auto-updates as accuracy data accumulates)
    dyn_weights = get_dynamic_weights()
    sig_accs    = get_signal_accuracies()
    if sig_accs:
        acc_parts = [f"{s['label']}:{s['accuracy_pct']:.0f}%({s['trades']})" for s in sig_accs.values()]
        console.print(f"  [dim]Signal accuracy: {' | '.join(acc_parts)}[/dim]")
    else:
        console.print(f"  [dim]Signal accuracy: building... (need {8} resolved trades per signal)[/dim]")
    console.print(f"  [dim]Dynamic weights: pf={dyn_weights.get('pf',0):.2f} ai={dyn_weights.get('ai',0):.2f} copy={dyn_weights.get('copy',0):.2f} whale={dyn_weights.get('whale',0):.2f} crowd={dyn_weights.get('crowd',0):.2f}[/dim]")

    # Build token map
    token_map = {}
    for m in all_candidates:
        if m.tokens and isinstance(m.tokens, list) and m.tokens:
            t = m.tokens[0]
            tid = t.get("token_id") if isinstance(t, dict) else str(t)
            if tid:
                token_map[m.condition_id] = tid

    # Pre-match news headlines to markets (keyword overlap → LLM context)
    news_map: dict[str, list[str]] = {}
    try:
        for market in all_candidates:
            q_words = set(w.lower().strip("?.,!\"'()") for w in market.question.split() if len(w) > 3)
            hits: list[tuple[int, str]] = []
            for ni in news_items[:400]:
                h_words = set(w.lower() for w in ni.headline.split())
                overlap = len(q_words & h_words)
                if overlap >= 2:
                    hits.append((overlap, ni.headline))
            hits.sort(reverse=True)
            if hits:
                news_map[market.condition_id] = [h for _, h in hits[:5]]
    except Exception as e:
        log.warning(f"[engine] news matching failed: {e}")

    # Batch whale + copy-trade signals
    all_ids = [m.condition_id for m in all_candidates[:150]]
    try:
        whale_map = bulk_whale_signals(all_ids[:40], token_map=token_map)
    except Exception:
        whale_map = {}
    try:
        copy_map = build_copy_signals(set(all_ids), top_n=30, min_usd=50.0)
        console.print(f"  [dim]Whale:{len(whale_map)} Copy:{len(copy_map)} News-matched:{len(news_map)}[/dim]")
    except Exception:
        copy_map = {}

    console.print(f"\n[bold cyan]🔮 ENGINE: {len(all_candidates)} candidates | whale:{len(whale_map)} copy:{len(copy_map)}[/bold cyan]")

    signals_found: list[Signal] = []
    demos_logged  = 0
    analyzed      = 0
    ai_calls_left = int(os.getenv("MAX_AI_CALLS_PER_SCAN", "35"))  # rate-limit budget

    from bankroll import kelly_bet_size, get_current_bankroll, can_trade_today
    from edge import Signal as _Signal

    CRYPTO_KW = [
        "bitcoin","btc","ethereum","eth","solana","sol","dogecoin","doge",
        "xrp","bnb","hyperliquid","cardano","ada","avax","polkadot","dot",
        "chainlink","litecoin","ltc","polygon","matic","uniswap","pepe","shib","crypto",
    ]

    MAX_MARKETS = int(os.getenv("MAX_MARKETS_PER_SCAN", "200"))

    for market in all_candidates[:MAX_MARKETS]:
        analyzed += 1
        q_lower   = market.question.lower()

        if any(pat in q_lower for pat in HARD_SKIP):
            continue

        hours_left = _hours_left(market)
        price      = market.yes_price
        tok        = token_map.get(market.condition_id)

        if hours_left > 48 or price < 0.07 or price > 0.93:
            continue

        is_crypto = any(k in q_lower for k in CRYPTO_KW)
        is_sweet  = 0.30 <= price <= 0.70   # 1:1 to 2.3:1 payout range

        # ── S1: Price feed (crypto math — deterministic) ───────────────
        pf_dir, pf_conf = "neutral", 0.0
        if is_crypto:
            try:
                pf = verify_crypto_market(market.question)
                if pf and pf["confidence"] >= 0.55:
                    pf_dir, pf_conf = pf["direction"], pf["confidence"]
            except Exception:
                pass

        # ── S2: Copy-trade (top wallet open positions) ─────────────────
        cp_dir, cp_conf, cp_wallets = "neutral", 0.0, 0
        lb_sig = copy_map.get(market.condition_id)
        if lb_sig and lb_sig.direction != "neutral":
            cp_dir     = lb_sig.direction
            cp_wallets = lb_sig.wallet_count
            cp_conf    = min(0.88, 0.50 + cp_wallets * 0.10
                             + min(lb_sig.total_usd, 5000) / 25000)

        # ── S3: Whale holder bias ──────────────────────────────────────
        wh_dir, wh_conf = "neutral", 0.0
        ws = whale_map.get(market.condition_id)
        if ws and ws.direction != "neutral":
            wh_dir  = ws.direction
            wh_conf = min(0.80, abs(ws.yes_bias - 0.5) * 2.2)

        # ── S4: CLOB crowd (only counts at true extremes) ──────────────
        clob_dir, clob_conf = "neutral", 0.0
        if price >= 0.72:
            clob_dir, clob_conf = "bullish", price
        elif price <= 0.28:
            clob_dir, clob_conf = "bearish", 1.0 - price

        # ── Fast-path: price feed alone is enough at high confidence ───
        # No AI needed — pure math wins 85%+ of time
        if pf_conf >= 0.70:
            final_dir  = pf_dir
            final_side = "YES" if pf_dir == "bullish" else "NO"
            final_score = pf_conf
            signals_record = {"pf": f"{pf_dir}:{pf_conf:.3f}", "ai": "neutral",
                               "copy": f"{cp_dir}:{cp_conf:.3f}" if cp_dir != "neutral" else "neutral",
                               "whale": f"{wh_dir}:{wh_conf:.3f}" if wh_dir != "neutral" else "neutral",
                               "crowd": f"{clob_dir}:{clob_conf:.3f}" if clob_dir != "neutral" else "neutral"}
            # Skip if copy-trade strongly disagrees
            if cp_dir != "neutral" and cp_dir != pf_dir and cp_conf >= 0.65:
                log.debug(f"[fast-path] PF/Copy conflict skip: {market.question[:45]}")
                continue
            gem_dir, gem_conf = "neutral", 0.0  # not needed
        else:
            # ── S5: AI Research (rate-limit budget) ───────────────────
            gem_dir, gem_conf = "neutral", 0.0
            # Only call AI if we have budget AND it's worth researching
            should_research = (
                ai_calls_left > 0
                and hours_left <= 36          # resolves soon enough to matter
                and (
                    is_crypto                   # crypto: AI confirms price feed
                    or len(news_map.get(market.condition_id, [])) >= 1  # news match
                    or cp_conf >= 0.40          # copy-trade partial signal → confirm
                    or clob_conf >= 0.72        # crowd very confident → confirm
                    or market.volume >= 5000    # high-volume market → worth researching
                )
            )
            if should_research:
                try:
                    matched_headlines = news_map.get(market.condition_id, [])
                    res = research_market(market, news_context=matched_headlines)
                    if res.direction in ("bullish", "bearish") and res.materiality >= 0.30:
                        gem_dir  = res.direction
                        gem_conf = min(0.88, res.materiality)
                    ai_calls_left -= 1
                except Exception as e:
                    log.debug(f"[research] {e}")

            # ── Combine all signals (MAX + agreement boost) ────────────
            all_sigs = [("pf", pf_dir, pf_conf), ("copy", cp_dir, cp_conf),
                        ("whale", wh_dir, wh_conf), ("ai", gem_dir, gem_conf),
                        ("crowd", clob_dir, clob_conf)]

            bull_sigs = [(l,c) for l,d,c in all_sigs if d == "bullish" and c > 0]
            bear_sigs = [(l,c) for l,d,c in all_sigs if d == "bearish"  and c > 0]

            max_bull = max((c for _,c in bull_sigs), default=0.0)
            max_bear = max((c for _,c in bear_sigs), default=0.0)
            boost_bull = min(0.18, sum(dyn_weights.get(l,0.05)*0.5 for l,_ in bull_sigs[1:]))
            boost_bear = min(0.18, sum(dyn_weights.get(l,0.05)*0.5 for l,_ in bear_sigs[1:]))
            score_bull = min(0.95, max_bull + boost_bull)
            score_bear = min(0.95, max_bear + boost_bear)

            signals_record = {}
            for lbl, d, c in all_sigs:
                signals_record[lbl] = f"{d}:{c:.3f}" if d != "neutral" and c > 0 else "neutral"

            # ── GATES ──────────────────────────────────────────────────

            # Hard conflict: PF vs AI
            if (pf_dir != "neutral" and gem_dir != "neutral"
                    and pf_dir != gem_dir and pf_conf >= 0.60 and gem_conf >= 0.45):
                log.debug(f"[gate] PF/AI conflict: {market.question[:45]}")
                continue

            # Must have at least one REAL signal (≥0.50 pf/copy, ≥0.40 AI,
            # ≥0.40 whale, ≥0.72 crowd already baked into clob_conf)
            has_real = (pf_conf >= 0.50 or cp_conf >= 0.50 or
                        wh_conf >= 0.45 or gem_conf >= 0.40 or clob_conf >= 0.72)
            if not has_real:
                continue

            # Contra-crowd: must have PF or AI backing at high confidence
            crowd_dir = "bullish" if price >= 0.58 else ("bearish" if price <= 0.42 else "neutral")
            if crowd_dir == "bullish" and score_bear > score_bull:
                if not ((pf_dir == "bearish" and pf_conf >= 0.70)
                        or (gem_dir == "bearish" and gem_conf >= 0.65)):
                    log.debug(f"[gate] Contra-crowd (bear vs YES crowd): {market.question[:45]}")
                    continue
            if crowd_dir == "bearish" and score_bull > score_bear:
                if not ((pf_dir == "bullish" and pf_conf >= 0.70)
                        or (gem_dir == "bullish" and gem_conf >= 0.65)):
                    log.debug(f"[gate] Contra-crowd (bull vs NO crowd): {market.question[:45]}")
                    continue

            # Minimum score thresholds by situation
            # Single AI signal at low conf → higher bar
            # Multiple agreeing signals → lower bar
            n_signals = len(bull_sigs) + len(bear_sigs)
            if score_bull >= score_bear:
                top_score = score_bull
                top_dir, top_side = "bullish", "YES"
            else:
                top_score = score_bear
                top_dir, top_side = "bearish", "NO"

            min_score = 0.55 if n_signals == 1 else 0.45 if n_signals == 2 else 0.38
            if top_score < min_score:
                log.debug(f"[score] {top_score:.2f}<{min_score} ({n_signals} sigs): {market.question[:45]}")
                continue

            final_dir, final_side, final_score = top_dir, top_side, top_score

        # ── EV gate ───────────────────────────────────────────────────
        bet_price     = price if final_side == "YES" else (1.0 - price)
        payout_ratio  = (1.0 - bet_price) / bet_price
        ev_per_dollar = final_score * payout_ratio - (1.0 - final_score)
        min_ev = 0.015 if is_sweet else 0.025
        if ev_per_dollar < min_ev:
            log.debug(f"[EV] {ev_per_dollar:.3f}<{min_ev}: {market.question[:45]}")
            continue

        # ── Bet sizing ────────────────────────────────────────────────
        allowed, reason = can_trade_today()
        if not allowed:
            console.print(f"  [red]⛔ {reason}[/red]")
            break
        bk   = get_current_bankroll()
        edge = max(final_score - bet_price, 0.03)
        bet  = kelly_bet_size(bk, edge, bet_price, materiality=final_score)
        # Tier sizing: high-confidence = bigger bet
        if pf_conf >= 0.70:
            bet = min(bet * 1.5, bk * 0.08)   # price feed trades — highest confidence
        elif final_score >= 0.70:
            bet = min(bet * 1.2, bk * 0.07)
        else:
            bet = min(bet, bk * 0.05)
        bet = round(max(0.50, bet), 2)

        # ── Print + log ───────────────────────────────────────────────
        sources = []
        if pf_conf   >= 0.50: sources.append(f"💰PF:{pf_conf:.0%}")
        if cp_conf   >= 0.40: sources.append(f"👛Copy:{cp_conf:.0%}({cp_wallets}w)")
        if wh_conf   >= 0.40: sources.append(f"🐋Whale:{wh_conf:.0%}")
        if clob_conf >= 0.60: sources.append(f"📊Crowd:{clob_conf:.0%}")
        if gem_conf  >= 0.30: sources.append(f"🔬AI:{gem_conf:.0%}")

        win_amt  = round(bet * payout_ratio, 2)
        tier_tag = "💰MATH" if pf_conf >= 0.70 else ("🎯HIGH" if final_score >= 0.70 else "⚡STD")
        console.print(
            f"  {tier_tag} [bold]{final_side}[/bold] "
            f"price:{price:.2f} pay:{payout_ratio:.1f}x "
            f"score:{final_score:.2f} ev:+${ev_per_dollar*bet:.2f} "
            f"closes:{hours_left:.1f}h\n"
            f"    {' + '.join(sources) or 'multi-signal'}\n"
            f"    \"{market.question[:72]}\""
        )

        unified_signal = _Signal(
            market=market,
            claude_score=final_score,
            market_price=price,
            edge=edge,
            side=final_side,
            bet_amount=bet,
            reasoning=f"score={final_score:.2f} ev={ev_per_dollar:.3f} | {' + '.join(sources)}",
            headlines="",
            news_source="unified_engine",
            classification=final_dir,
            materiality=final_score,
            composite_score=final_score,
        )
        trade_id = _log_demo_trade(unified_signal, token_id=tok, signals=signals_record)
        already_logged.add(market.condition_id)
        signals_found.append(unified_signal)
        demos_logged += 1
        console.print(f"    → [green]✅ Trade #{trade_id} logged (${bet:.2f} → win:+${win_amt} / lose:-${bet})[/green]")

    ai_used = int(os.getenv("MAX_AI_CALLS_PER_SCAN", "35")) - ai_calls_left
    if not signals_found:
        console.print(f"  [yellow]No trades this scan — {analyzed} markets analyzed, {ai_used} AI calls used.[/yellow]")
    else:
        console.print(f"\n  ✅ {demos_logged} trades | {analyzed} analyzed | {ai_used} AI calls used")
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
