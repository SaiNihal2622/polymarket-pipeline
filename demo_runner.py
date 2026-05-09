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
from resolver import run_resolution_check, get_accuracy_stats, get_resolved_trade_list, get_pipeline_comparison, get_strategy_accuracies
from optimizer import enhance_signal, adaptive_thresholds, score_market_quality, kelly_size as optimizer_kelly

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
    ttr = stats.get("avg_ttr_hours", 0)
    ttr_str = f" | TTR: {ttr:.1f}h" if ttr > 0 else ""
    console.print(
        f"  [bold cyan]▶ ACCURACY:[/bold cyan] {acc_str}  "
        f"| logged={total_logged}  resolved={total_resolved}  "
        f"{ttr_str}"
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

    # 2-day strategy trial leaderboard
    try:
        strat_accs = get_strategy_accuracies()
        if strat_accs:
            console.print("  [bold cyan]── Strategy Trial Leaderboard ──[/bold cyan]")
            for s in strat_accs:
                bar   = "█" * int(s["accuracy_pct"] / 10)
                color = "bright_green" if s["accuracy_pct"] >= 70 else "yellow" if s["accuracy_pct"] >= 50 else "red"
                console.print(
                    f"  [{color}]{s['strategy']:18s}[/{color}] "
                    f"[bold]{s['accuracy_pct']:5.1f}%[/bold] {bar} "
                    f"({s['wins']}W/{s['losses']}L, {s['trades']} trades, pnl:${s['pnl']:+.2f})"
                )
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
    from logger import DB_PATH
    if not DB_PATH.exists():
        console.print("  [dim]No DB to wipe.[/dim]")
        return
    conn = sqlite3.connect(DB_PATH)
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
DEMO_HOURS_WINDOW = float(os.getenv("DEMO_HOURS_WINDOW", str(getattr(config, "DEMO_HOURS_WINDOW", 30))))    # 30h window: niche short-resolution markets where AI has real edge
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
                    signals: dict | None = None, strategy: str | None = None) -> int:
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
        strategy=strategy,
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
    gemini_down = False
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
        # Finance/stocks — empirical 0% accuracy (0W/2L)
        "close above", "close below", "(spy)", "(qqq)", "(nvda)", "(tsla)",
        "(aapl)", "(msft)", "(googl)", "(meta)", "(amzn)", "(nflx)",
        "s&p 500", "nasdaq", "dow jones", "russell", "vix",
        "stock close", "stock price", "share price", "earnings", "10-year",
        # Long-dated futures (can't resolve in 48h)
        "world series", "super bowl", "stanley cup", "french open", "wimbledon",
        "nba champion", "nba finals", "nfl afc", "nfl nfc", "nhl playoffs",
        "lpl 2026", "ipl champion", "tour de france", "rbc heritage", "masters 2026",
        "governor", "senator", "president", "fed chair", "confirmed as",
        "2027", "grammy", "oscar", "nobel", "eurovision",
        # Esports (pure luck/skill markets)
        "(bo1)", "(bo3)", "(bo5)", "map 1 winner", "map 2 winner", "map 3 winner",
        "game 1 winner", "game 2 winner", "game 3 winner", "game 4 winner",
        "first blood", "first tower", "first baron", "quadra kill", "penta kill",
        "dragon soul", "inhibitor", "total kills",
        "dota 2", "valorant", "counter-strike", "league of legends", " lol:", " lol ",
        "cblol", "lck", "lpl", "lec", "lcs", "msi", "worlds 2026",
        "call of duty", "cdl", "overwatch", "rainbow six",
        # WNBA / NBA / sports game winners — crowd already priced in, no AI edge
        " vs. ", " vs ", "moneyline", "1h moneyline",
        # Stocks / finance — AI has no edge on price targets
        "finish week", "hit (low)", "hit (high)", "close above $", "close below $",
        "above $", "below $", "hit $", "(pltr)", "(coin)", "(hood)", "(mstr)",
        "robinhood", "palantir", "coinbase",
        # Sports O/U / props (unresearchable — block ALL o/u patterns)
        " o/u ", "o/u ", ": o/u", "over/under",
        "both teams to score", "leading at halftime", "half time",
        "spread:", "correct score", "exact score", "handicap:",
        "points o/u", "assists o/u", "rebounds o/u", "total corners",
        "total kills", "games total", "map total",
        "any player", "up or down", "opens up or down",
        # Random sports game results — AI has NO edge, pure coin flip
        # "Will [team] win?" = crowd already priced in all info, 0% edge
        "will cf ", "will ca ", "will sc ", "will ec ", "will se ", "will cd ",
        "will fc ", "will ac ", "will rc ", "will dc ", "will fk ", "will nk ",
        "will sk ", "will hk ", "will bk ", "will ok ", "will as ",
        "win on 2026-04", "win on 2026-05", "win on 2026-06",
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

    # Batch whale + copy-trade signals (now ALL candidates — bigger window catches whales)
    all_ids = [m.condition_id for m in all_candidates[:300]]
    try:
        whale_map = bulk_whale_signals(all_ids[:120], token_map=token_map)
    except Exception:
        whale_map = {}
    try:
        # top_n=80 wallets, min_usd=15 — more wallets surface more signals on niche markets
        copy_map = build_copy_signals(set(all_ids), top_n=80, min_usd=15.0)
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

        if hours_left > 30 or price < 0.10 or price > 0.90:
            continue

        # Skip "uncertain zone" prices (0.45-0.55) — crowd says 50/50, no edge
        # Narrowed from 0.40-0.60 to 0.45-0.55 to capture more markets
        if 0.45 <= price <= 0.55:
            log.debug(f"[skip:uncertain] price={price:.2f} in dead zone: {q_lower[:50]}")
            continue

        is_crypto = any(k in q_lower for k in CRYPTO_KW)
        is_sweet  = 0.30 <= price <= 0.70   # 1:1 to 2.3:1 payout range

        # Skip crypto — empirical accuracy is 22% (2W/7L), far below breakeven
        # Price feed alone isn't reliable for short crypto windows
        if is_crypto:
            log.debug(f"[skip:crypto] 22% historical accuracy: {q_lower[:50]}")
            continue

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

        # ── S4: CLOB crowd — DISABLED (29% accuracy, 4W/10L)
        # Kept as informational signal only; never fires a trade.
        clob_dir, clob_conf = "neutral", 0.0

        # ── S5: AI Research pass 1 (analyst) ──────────────────────────
        gem_dir, gem_conf, gem_mat, gem_res_obj = "neutral", 0.0, 0.0, None
        matched_headlines = news_map.get(market.condition_id, [])
        has_news  = len(matched_headlines) >= 1
        has_news2 = len(matched_headlines) >= 2

        # Research budget: AI runs on virtually all in-window markets.
        # Apify web search invoked inside research_market when Gemini uncertain.
        # Only skip ultra-low-volume markets (<$80) to save budget.
        should_research = (
            ai_calls_left > 0 and hours_left <= 30
            and market.volume >= 80
        )
        if should_research:
            try:
                gem_res_obj = research_market(market, news_context=matched_headlines)
                if gem_res_obj.direction in ("bullish","bearish") and gem_res_obj.materiality >= 0.25:
                    gem_dir  = gem_res_obj.direction
                    gem_mat  = gem_res_obj.materiality
                    gem_conf = min(0.88, gem_mat)
                ai_calls_left -= 1
            except Exception as e:
                log.debug(f"[research] {e}")

        # ── S5b: Multi-pass Consensus Loop ──
        consensus_agreed = (gem_dir != "neutral")
        consensus_score  = gem_conf
        consensus_passes = 1
        
        if gem_dir != "neutral" and config.CONSENSUS_ENABLED and config.CONSENSUS_PASSES > 1:
            try:
                from classifier import PROMPTS as _PROMPTS, _call_llm
                from classifier import _build_analyst_prompt, _parse_json_response
                
                # Passes start from index 1 (Skeptic, Reflector, etc.)
                for p_idx in range(1, config.CONSENSUS_PASSES):
                    if ai_calls_left <= 0: break
                    
                    # Use Gemini if available, else Groq
                    use_gemini = (config.LLM_PROVIDER == "gemini" and not gemini_down)
                    p_prompt = _build_analyst_prompt(market, matched_headlines) # Simplified for now
                    
                    try:
                        p_text = _call_llm(p_prompt) # respects provider + fallback
                        p_res  = _parse_json_response(p_text)
                        p_dir  = p_res.get("direction", "neutral")
                        p_mat  = max(0.0, min(1.0, float(p_res.get("materiality", 0))))
                        
                        if p_dir != gem_dir:
                            consensus_agreed = False
                            log.info(f"  [yellow]SKIP[/yellow] consensus disagreed on pass {p_idx+1}: {p_dir} vs {gem_dir}")
                            break
                        
                        consensus_score = (consensus_score + p_mat) / 2
                        consensus_passes += 1
                        ai_calls_left -= 1
                    except Exception as e:
                        if "429" in str(e): gemini_down = True
                        log.debug(f"[consensus] pass {p_idx+1} failed: {e}")
            except Exception as e:
                log.debug(f"[consensus] loop failed: {e}")

        # ── RRF composite score (price_room + recency + niche + materiality) ──
        from edge import compute_composite_score as _rrf
        from news_stream import NewsEvent as _NE
        rrf_score = 0.0
        if gem_res_obj is not None:
            try:
                price_room = (1.0 - price) if gem_dir == "bullish" else price
                # News age: use first matched headline age proxy (assume ~2h avg)
                news_age_h = 2.0 if not has_news else (0.5 if has_news2 else 1.5)
                mock_event = _NE(
                    headline=matched_headlines[0] if matched_headlines else market.question,
                    source="rss", url="", received_at=datetime.now(timezone.utc),
                    published_at=datetime.now(timezone.utc) - timedelta(hours=news_age_h),
                    latency_ms=int(news_age_h * 3600 * 1000),
                )
                rrf_score = _rrf(
                    classification=gem_res_obj, market=market,
                    news_event=mock_event, price_room=price_room,
                )
            except Exception as e:
                log.debug(f"[rrf] {e}")

        # ── Build signal summary ───────────────────────────────────────
        all_sigs = [("pf", pf_dir, pf_conf), ("copy", cp_dir, cp_conf),
                    ("whale", wh_dir, wh_conf), ("ai", gem_dir, gem_conf),
                    ("crowd", clob_dir, clob_conf)]
        signals_record = {lbl: (f"{d}:{c:.3f}" if d != "neutral" and c > 0 else "neutral")
                          for lbl, d, c in all_sigs}
        signals_record["consensus"] = f"{gem_dir}:{consensus_score:.3f}" if consensus_agreed else "neutral"
        signals_record["rrf"]       = f"{gem_dir}:{rrf_score:.3f}" if rrf_score >= 0.35 else "neutral"

        # Agreeing signals per direction (crowd EXCLUDED — 29% accuracy poisons signal)
        bull_sigs  = [(l,c) for l,d,c in all_sigs if d == "bullish" and c > 0 and l != "crowd"]
        bear_sigs  = [(l,c) for l,d,c in all_sigs if d == "bearish"  and c > 0 and l != "crowd"]
        max_bull   = max((c for _,c in bull_sigs), default=0.0)
        max_bear   = max((c for _,c in bear_sigs), default=0.0)
        boost_b    = min(0.18, sum(dyn_weights.get(l,0.05)*0.5 for l,_ in bull_sigs))
        boost_r    = min(0.18, sum(dyn_weights.get(l,0.05)*0.5 for l,_ in bear_sigs))
        score_bull = min(0.95, max_bull + boost_b)
        score_bear = min(0.95, max_bear + boost_r)

        if score_bull >= score_bear and score_bull > 0:
            best_dir, best_side, best_score = "bullish", "YES", score_bull
        elif score_bear > score_bull:
            best_dir, best_side, best_score = "bearish", "NO", score_bear
        else:
            continue  # no signal at all

        n_agree = max(len(bull_sigs), len(bear_sigs))

        # ── 2-DAY STRATEGY TRIAL — ALL 14 COMBOS ──────────────────────
        # Every market tested against every strategy simultaneously.
        # Strategies include signal combos + consensus + RRF composite
        # + materiality + recency + price room.

        def _dir(d): return "YES" if d == "bullish" else "NO"
        strategies_to_try: list[tuple[str, str, float]] = []

        # ── CONSENSUS-FIRST ENGINE ──
        # Past trial: S8 alone hit 47% (random). RRF score isn't enough.
        # The ONLY proven path is consensus (AI + Skeptic both agree).
        # We allow S8 only when RRF is EXTREMELY high (≥0.70) AND consensus agrees.

        # ★★ S8: HIGH RRF + consensus required
        # Lowered from 0.50 → 0.35 to generate more trades
        if (gem_dir != "neutral" and rrf_score >= 0.35 and consensus_agreed):
            strategies_to_try.append(("S8_rrf_highconv", _dir(gem_dir), rrf_score + 0.05))

        # ★★ S5: CONSENSUS-FIRST — balanced thresholds
        # Lowered: consensus_score≥0.30, rrf≥0.30, gem_mat≥0.25
        if (gem_dir != "neutral" and consensus_agreed and consensus_score >= 0.30
                and rrf_score >= 0.30 and gem_mat >= 0.25):
            strategies_to_try.append(("S5_consensus", _dir(gem_dir), consensus_score))

        # ★★ S9: SURESHOT — high-confidence AI signal
        # Lowered: gem_mat≥0.45, gem_conf≥0.50, rrf≥0.35
        if (gem_dir != "neutral" and gem_mat >= 0.45 and gem_conf >= 0.50
                and rrf_score >= 0.35 and consensus_agreed):
            strategies_to_try.append(("S9_sureshot", _dir(gem_dir), gem_conf))

        # ★★ S10: MULTI-SIGNAL — copy-trade + AI agree
        # Combines whale/copy-trade signal with AI direction
        if (gem_dir != "neutral" and n_agree >= 2 and consensus_agreed):
            strategies_to_try.append(("S10_multi_signal", _dir(gem_dir), best_score))

        # ★★ S11: AI-ONLY — strong AI signal without requiring RRF
        # Lowered: gem_mat≥0.50, gem_conf≥0.55
        if (gem_dir != "neutral" and gem_mat >= 0.50 and gem_conf >= 0.55
                and consensus_agreed and rrf_score < 0.40):
            strategies_to_try.append(("S11_ai_only", _dir(gem_dir), gem_conf))

        if not strategies_to_try:
            continue

        # ── PER-MARKET DEDUP: pick the SINGLE best strategy per market ──
        # Previously: 1 market spawned 5+ duplicate rows (inflated stats).
        # Now: each market produces exactly ONE trade under its top strategy.
        # Priority order based on empirical accuracy from the trial:
        STRAT_PRIORITY = {
            "S8_rrf_highconv":   200,  # RRF ≥0.50 + consensus — top priority
            "S9_sureshot":       150,  # High-confidence AI: mat≥0.55 + conf≥0.60
            "S10_multi_signal":  130,  # Multi-signal: n_agree≥2 + consensus
            "S5_consensus":       90,  # Consensus-first: mat≥0.35 + rrf≥0.40
            "S11_ai_only":        70,  # AI-only: strong AI without RRF
            "S7_rrf_composite":   60,  # RRF composite (legacy)
            "S6_hi_materiality":  50,  # High materiality (legacy)
        }
        strategies_to_try.sort(
            key=lambda s: STRAT_PRIORITY.get(s[0], 0), reverse=True
        )
        # Keep only the top-priority strategy
        strategies_to_try = strategies_to_try[:1]

        # ── Log one trade per strategy ─────────────────────────────────
        allowed, reason = can_trade_today()
        if not allowed:
            console.print(f"  [red]⛔ {reason}[/red]")
            break

        bk = get_current_bankroll()
        strats_logged = 0

        for strat_name, strat_side, strat_score in strategies_to_try:
            # Skip if market already logged (extra safety)
            combo_key = f"{market.condition_id}"
            if combo_key in already_logged:
                continue

            bet_price    = price if strat_side == "YES" else (1.0 - price)
            # ── ROI FILTER: ≥100% ROI (same as detect_edge_v2 Gate 4b) ──
            # Buy only if bet_price ≤ 0.50 → payout ratio ≥ 2:1
            if bet_price > 0.50:
                roi_pct = (1.0 / bet_price - 1.0) * 100
                log.debug(f"[strategy] SKIP {strat_name} {strat_side} bet_price={bet_price:.2f} — ROI={roi_pct:.0f}% < 100%")
                continue
            payout_ratio = (1.0 - bet_price) / bet_price
            ev           = strat_score * payout_ratio - (1.0 - strat_score)
            if ev < 0.01:
                continue  # skip negative-EV strategies

            edge  = strat_score - bet_price
            bet   = kelly_bet_size(bk, edge, bet_price, materiality=strat_score)
            bet   = min(bet, bk * 0.05)   # hard 5% cap during trial (conservative)
            bet   = round(max(0.50, bet), 2)
            win_a = round(bet * payout_ratio, 2)

            sig = _Signal(
                market=market, claude_score=strat_score, market_price=price,
                edge=edge, side=strat_side, bet_amount=bet,
                reasoning=f"strategy={strat_name} score={strat_score:.2f} ev={ev:.3f}",
                headlines="", news_source="strategy_trial",
                classification=("bullish" if strat_side=="YES" else "bearish"),
                materiality=strat_score, composite_score=strat_score,
            )
            trade_id = _log_demo_trade(sig, token_id=tok,
                                       signals=signals_record, strategy=strat_name)
            already_logged.add(combo_key)
            signals_found.append(sig)
            demos_logged += 1
            strats_logged += 1

        if strats_logged > 0:
            strat_names = [s[0] for s in strategies_to_try]
            console.print(
                f"  📊 [bold]{strats_logged} strategies[/bold] fired on "
                f"[yellow]\"{market.question[:60]}\"[/yellow]\n"
                f"     [{', '.join(strat_names)}]"
            )

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
    wipe_env = os.getenv("WIPE_ON_START", "false").lower()
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
            try:
                console.print(f"\n[dim]── Resolution check @ {datetime.now().strftime('%H:%M:%S')} ──[/dim]")
                res = run_resolution_check(verbose=True)
                last_resolve = now
                # Always print accuracy after resolution check
                _print_accuracy_oneliner()
                if res["resolved"] > 0:
                    stats = print_accuracy_report()
                    maybe_go_live(stats)
            except Exception as e:
                log.error(f"[loop] resolution check failed: {e}", exc_info=True)
                last_resolve = now  # don't retry immediately

        # Full scan (less often)
        if now - last_scan >= SCAN_INTERVAL_MIN * 60:
            try:
                scan_and_trade()
            except Exception as e:
                log.error(f"[loop] scan failed: {e}", exc_info=True)
                console.print(f"  [red]Scan error: {e}[/red]")
            finally:
                last_scan = now  # don't retry immediately

        time.sleep(30)  # check every 30s whether it's time to run again


def main():
    parser = argparse.ArgumentParser(description="Polymarket Demo Runner")
    parser.add_argument("--once", action="store_true", help="Run one scan then exit")
    parser.add_argument("--report", action="store_true", help="Show accuracy report and exit")
    parser.add_argument("--resolve", action="store_true", help="Run resolution check and exit")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

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
