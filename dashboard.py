#!/usr/bin/env python3
"""
Polymarket Pipeline V3 — Live Terminal Dashboard
Shows: news feed, matched markets, classifications, signals, trade log, accuracy stats.
"""
from __future__ import annotations

import time
import sys
from datetime import datetime, timezone

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

import config
import logger

console = Console()

# --- Color Palette ---
ACCENT = "bright_green"
DIM = "bright_black"
WARN = "yellow"
LOSS = "red"
WIN = "bright_green"
MUTED = "dim white"
CYAN = "bright_cyan"


def make_layout() -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=3),
    )
    layout["body"].split_row(
        Layout(name="left", ratio=2),
        Layout(name="right", ratio=3),
    )
    layout["left"].split_column(
        Layout(name="status", ratio=2),
        Layout(name="accuracy", ratio=3),
    )
    layout["right"].split_column(
        Layout(name="news_feed", ratio=2),
        Layout(name="trades", ratio=3),
    )
    return layout


def render_header() -> Panel:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    grid = Table.grid(expand=True)
    grid.add_column(justify="left", ratio=1)
    grid.add_column(justify="center", ratio=2)
    grid.add_column(justify="right", ratio=1)

    mode = "LIVE" if not config.DRY_RUN else "DRY RUN"
    provider = config.LLM_PROVIDER.upper()

    grid.add_row(
        Text(" POLYMARKET PIPELINE V3", style="bold bright_green"),
        Text(f"CONSENSUS TRADING  |  {provider}  |  {mode}", style=DIM),
        Text(f"{now} ", style=MUTED),
    )
    return Panel(grid, style="bright_green", box=box.HEAVY)


def render_status() -> Panel:
    table = Table(show_header=False, box=None, padding=(0, 1), expand=True)
    table.add_column("label", style=MUTED, width=18)
    table.add_column("value", style=ACCENT)

    mode = f"[{WIN}]LIVE[/{WIN}]" if not config.DRY_RUN else f"[{WARN}]DRY RUN[/{WARN}]"
    provider = config.LLM_PROVIDER.upper()
    if provider == "GEMINI":
        model = config.GEMINI_MODEL
    elif provider == "OLLAMA":
        model = config.CLASSIFICATION_MODEL
    else:
        model = config.CLASSIFICATION_MODEL

    stats = logger.get_trade_stats()
    latency = logger.get_latency_stats()
    daily_spent = abs(logger.get_daily_pnl())

    table.add_row("Mode", mode)
    table.add_row("LLM", f"{provider} / {model}")
    table.add_row("Consensus", f"{'ON' if config.CONSENSUS_ENABLED else 'OFF'} ({config.CONSENSUS_PASSES} passes)")
    table.add_row("Bankroll", f"${config.BANKROLL_USD:.0f}")
    table.add_row("Max Bet", f"${config.MAX_BET_USD}")
    table.add_row("Daily Limit", f"${config.DAILY_LOSS_LIMIT_USD}")
    table.add_row("Daily Exposure", f"[{WARN}]${daily_spent:.2f}[/{WARN}]")
    table.add_row("", "")
    table.add_row("Edge Threshold", f"{config.EDGE_THRESHOLD:.0%}")
    table.add_row("Mat. Threshold", f"{config.MATERIALITY_THRESHOLD}")
    table.add_row("Total Signals", f"[{ACCENT}]{stats['total_trades']}[/{ACCENT}]")

    if latency["count"] > 0:
        table.add_row("Avg Latency", f"{latency['avg_total_ms']}ms")

    return Panel(table, title="[bold]PIPELINE STATUS[/bold]", border_style="bright_green", box=box.ROUNDED)


def render_accuracy() -> Panel:
    cal = logger.get_calibration_stats()
    stats = logger.get_trade_stats()

    table = Table(show_header=False, box=None, padding=(0, 1), expand=True)
    table.add_column("label", style=MUTED, width=18)
    table.add_column("value")

    if cal["total"] > 0:
        acc = cal["accuracy"]
        acc_style = WIN if acc >= 55 else (WARN if acc >= 45 else LOSS)
        table.add_row("Calibrated Trades", str(cal["total"]))
        table.add_row("Accuracy", f"[{acc_style}]{acc:.1f}%[/{acc_style}]")

        table.add_row("", "")
        table.add_row("[bold]By Classification[/bold]", "")
        for cls, pct in cal.get("by_classification", {}).items():
            style = WIN if pct >= 55 else (WARN if pct >= 45 else LOSS)
            table.add_row(f"  {cls}", f"[{style}]{pct:.1f}%[/{style}]")

        table.add_row("", "")
        table.add_row("[bold]By Source[/bold]", "")
        for src, pct in cal.get("by_source", {}).items():
            style = WIN if pct >= 55 else (WARN if pct >= 45 else LOSS)
            table.add_row(f"  {src}", f"[{style}]{pct:.1f}%[/{style}]")
    else:
        by_status = stats.get("by_status", {})
        dry_runs = by_status.get("dry_run", 0)
        executed = by_status.get("executed", 0)

        table.add_row("Dry Run Signals", f"[{WARN}]{dry_runs}[/{WARN}]")
        table.add_row("Live Trades", f"[{ACCENT}]{executed}[/{ACCENT}]")
        table.add_row("", "")
        table.add_row(f"[{DIM}]Accuracy tracking[/{DIM}]", "")
        table.add_row(f"[{DIM}]starts after markets[/{DIM}]", "")
        table.add_row(f"[{DIM}]resolve.[/{DIM}]", "")

    return Panel(table, title="[bold]ACCURACY & PERFORMANCE[/bold]", border_style=CYAN, box=box.ROUNDED)


def render_news_feed() -> Panel:
    events = logger.get_recent_news_events(limit=12)

    table = Table(show_header=True, box=box.SIMPLE_HEAD, expand=True, padding=(0, 1))
    table.add_column("Time", width=8, style=MUTED)
    table.add_column("Src", width=5, style=CYAN)
    table.add_column("Headline", ratio=4)
    table.add_column("Lat.", justify="right", width=6, style=DIM)

    if not events:
        table.add_row(f"[{DIM}]Waiting for news...[/{DIM}]", "", "", "")
    else:
        for e in events:
            ts = e.get("received_at", e.get("created_at", ""))
            if ts:
                try:
                    t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    time_str = t.strftime("%H:%M:%S")
                except (ValueError, AttributeError):
                    time_str = ts[:8]
            else:
                time_str = "?"

            source = e.get("source", "?")[:5]
            headline = e.get("headline", "")[:65]
            lat = e.get("latency_ms", 0)
            lat_str = f"{lat}ms" if lat else ""

            table.add_row(time_str, source, headline, lat_str)

    return Panel(table, title="[bold]NEWS FEED[/bold]  ·  Latest headlines matched to markets", border_style=ACCENT, box=box.ROUNDED)


def render_trades() -> Panel:
    trades = logger.get_recent_trades(limit=12)

    table = Table(show_header=True, box=box.SIMPLE_HEAD, expand=True, padding=(0, 1))
    table.add_column("Time", width=8, style=MUTED)
    table.add_column("Market", max_width=30)
    table.add_column("Dir", justify="center", width=5)
    table.add_column("Mat", justify="right", width=4)
    table.add_column("Side", justify="center", width=4)
    table.add_column("Bet", justify="right", width=6)
    table.add_column("Edge", justify="right", width=5)
    table.add_column("Status", justify="center", width=8)

    if not trades:
        table.add_row(f"[{DIM}]No signals yet — pipeline classifying...[/{DIM}]", "", "", "", "", "", "", "")
    else:
        for t in trades:
            ts = t.get("created_at", "")[:8]
            question = t.get("market_question", "")[:30]
            classification = t.get("classification", "?")
            materiality = t.get("materiality", 0)

            dir_style = WIN if classification == "bullish" else (LOSS if classification == "bearish" else DIM)
            side = t.get("side", "?")
            side_style = WIN if side == "YES" else "bright_magenta"

            status = t.get("status", "?")
            if status == "dry_run":
                status_str = f"[{WARN}]DRY[/{WARN}]"
            elif status == "executed":
                status_str = f"[{WIN}]LIVE[/{WIN}]"
            elif "limit" in status:
                status_str = f"[{LOSS}]LIMIT[/{LOSS}]"
            elif status.startswith("error"):
                status_str = f"[{LOSS}]ERR[/{LOSS}]"
            else:
                status_str = f"[{DIM}]{status[:8]}[/{DIM}]"

            mat_str = f"{materiality:.2f}" if materiality else "?"
            edge_str = f"{t.get('edge', 0):.0%}"

            table.add_row(
                ts,
                question,
                f"[{dir_style}]{classification[:5]}[/{dir_style}]",
                mat_str,
                f"[{side_style}]{side}[/{side_style}]",
                f"${t.get('amount_usd', 0):.2f}",
                edge_str,
                status_str,
            )

    return Panel(table, title="[bold]SIGNALS & TRADES[/bold]  ·  Consensus-filtered signals", border_style=CYAN, box=box.ROUNDED)


def render_footer() -> Panel:
    grid = Table.grid(expand=True)
    grid.add_column(justify="left", ratio=2)
    grid.add_column(justify="center", ratio=2)
    grid.add_column(justify="right", ratio=2)

    stats = logger.get_trade_stats()
    latency = logger.get_latency_stats()

    grid.add_row(
        f" [{ACCENT}]Signals: {stats['total_trades']}[/{ACCENT}]  |  "
        f"[{DIM}]Avg latency: {latency.get('avg_total_ms', 0)}ms[/{DIM}]",
        f"[{DIM}]Ctrl+C to exit  |  Refreshes every 2s[/{DIM}]",
        f"[{DIM}]Bankroll: ${config.BANKROLL_USD:.0f}  |  Provider: {config.LLM_PROVIDER.upper()}[/{DIM}] ",
    )
    return Panel(grid, style="bright_green", box=box.HEAVY)


def run_dashboard():
    """Launch the live monitoring dashboard. Reads from SQLite — no pipeline execution."""
    layout = make_layout()

    try:
        with Live(layout, console=console, refresh_per_second=0.5, screen=True) as live:
            while True:
                layout["header"].update(render_header())
                layout["status"].update(render_status())
                layout["accuracy"].update(render_accuracy())
                layout["news_feed"].update(render_news_feed())
                layout["trades"].update(render_trades())
                layout["footer"].update(render_footer())
                time.sleep(2)

    except KeyboardInterrupt:
        stats = logger.get_trade_stats()
        console.print(f"\n[{ACCENT}]Dashboard closed. {stats['total_trades']} signals logged.[/{ACCENT}]")


if __name__ == "__main__":
    run_dashboard()
