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
import time
from datetime import datetime, timezone, timedelta

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

import config
import logger
from markets import fetch_active_markets, filter_by_categories
from scraper import scrape_all
from classifier import classify, Classification
from matcher import match_news_to_markets
from edge import detect_edge_v2, Signal
from news_stream import NewsEvent
from resolver import run_resolution_check, get_accuracy_stats

console = Console()
log = logging.getLogger(__name__)

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


def _log_demo_trade(signal: Signal) -> int:
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

    # 1. News
    console.print("\n[bold]1. Scraping news...[/bold]")
    news_items = scrape_all(config.NEWS_LOOKBACK_HOURS)
    console.print(f"   {len(news_items)} headlines from RSS/Twitter/Telegram")

    # 2. Markets
    console.print("\n[bold]2. Fetching live markets...[/bold]")
    all_markets = fetch_active_markets(limit=200)
    category_filtered = filter_by_categories(all_markets)
    day_markets = filter_closing_soon(category_filtered, DEMO_HOURS_WINDOW)

    console.print(
        f"   {len(all_markets)} total → {len(category_filtered)} in categories "
        f"→ [bold yellow]{len(day_markets)} closing within {DEMO_HOURS_WINDOW:.0f}h[/bold yellow]"
    )

    if not day_markets:
        console.print("   [yellow]No 1-day markets found. Try expanding DEMO_HOURS_WINDOW in .env.[/yellow]")
        return {"markets": 0, "signals": 0, "demos_logged": 0}

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

    # 3. Full V2 Analysis: match news → consensus classify → RRF score
    console.print(f"\n[bold]3. Full V2 Analysis (Analyst + Skeptic + RRF) on {len(day_markets)} markets...[/bold]")
    signals_found: list[Signal] = []
    demos_logged = 0
    analyzed = 0

    for news_item in news_items:
        # Match this headline to relevant 1-day markets
        matched_markets = match_news_to_markets(news_item.headline, day_markets)
        if not matched_markets:
            continue

        news_event = _news_item_to_event(news_item)

        for market in matched_markets:
            analyzed += 1

            # ── Pass 1: Analyst + Pass 2: Skeptic (MiroFish debate) ──────────
            classification: Classification = classify(
                headline=news_item.headline,
                market=market,
                source=news_item.source,
            )

            # Log what the analysis said
            if classification.direction == "neutral":
                log.debug(f"  neutral: {market.question[:45]}")
                continue

            if config.CONSENSUS_ENABLED and not classification.consensus_agreed:
                console.print(
                    f"  [yellow]DEBATE SPLIT[/yellow] analyst vs skeptic disagreed on "
                    f"\"{market.question[:45]}\" — skipping"
                )
                continue

            # ── RRF Multi-Signal Edge Detection ──────────────────────────────
            signal = detect_edge_v2(market, classification, news_event)

            if signal:
                end = _parse_end_date(market.end_date)
                hours_left = ((end - now).total_seconds() / 3600) if end else 0
                console.print(
                    f"  [bright_green]SIGNAL ✓CON[/bright_green] "
                    f"[bold]{signal.side}[/bold] | "
                    f"mat:{classification.materiality:.2f} "
                    f"composite:{signal.composite_score:.2f} "
                    f"edge:{signal.edge:.1%} "
                    f"closes:{hours_left:.1f}h\n"
                    f"    Market: \"{market.question[:55]}\"\n"
                    f"    News:   [{news_item.source}] {news_item.headline[:70]}\n"
                    f"    Reason: {classification.reasoning[:100]}"
                )
                trade_id = _log_demo_trade(signal)
                console.print(f"    → [green]Demo trade #{trade_id} logged (${signal.bet_amount:.2f} virtual)[/green]")
                signals_found.append(signal)
                demos_logged += 1
            else:
                log.debug(
                    f"  edge too low: {market.question[:45]} "
                    f"mat={classification.materiality:.2f} dir={classification.direction}"
                )

    if not signals_found:
        console.print(
            f"  [dim]No signals this scan — analyzed {analyzed} market×news pairs. "
            f"Consensus or composite threshold not met.[/dim]"
        )

    console.print(f"\n  Scan complete: {len(news_items)} headlines → {analyzed} pairs analyzed → {demos_logged} demo trades")

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

    last_scan = 0.0
    last_resolve = 0.0

    while True:
        now = time.time()

        # Resolution check (runs more often)
        if now - last_resolve >= RESOLVE_INTERVAL_MIN * 60:
            console.print(f"\n[dim]── Resolution check @ {datetime.now().strftime('%H:%M:%S')} ──[/dim]")
            res = run_resolution_check(verbose=True)
            last_resolve = now

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
