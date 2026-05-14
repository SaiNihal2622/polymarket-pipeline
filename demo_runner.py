#!/usr/bin/env python3
"""
demo_runner.py — Scan Polymarket → AI Research → Log demo trades → Auto-resolve.
No real money.  Tracks virtual P&L and accuracy.

Flow:
  1. Fetch all markets closing within N hours
  2. For each market: news scrape → AI research → price-feed verify
  3. If edge exists: log a $1 demo trade
  4. Every RESOLVE_INTERVAL: check if markets resolved, mark W/L/P

Every trade includes full reasoning for the dashboard's Reason panel.

v2.1 — Now also stores news_context per trade so the dashboard can
       show the actual headlines that triggered the trade.
v2.2 — Tuned for high throughput: 3-5x more trades per scan while
       maintaining accuracy through consensus + RRF gating.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import re
import sqlite3
import time
from datetime import datetime, timezone, timedelta
import asyncio

import config
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()
log = logging.getLogger("demo_runner")

# ── Settings ─────────────────────────────────────────────────────────────────
# Use the SAME DB path as logger.py so all trades go to one database
from logger import DB_PATH
DEMO_HOURS_WINDOW  = config.DEMO_HOURS_WINDOW   # 30h — tighter, avoids stale markets
SCAN_INTERVAL_MIN  = config.SCAN_INTERVAL_MIN   # 5 min
RESOLVE_INTERVAL_MIN = config.RESOLVE_INTERVAL_MIN  # 6 min
ACCURACY_THRESHOLD = config.ACCURACY_THRESHOLD  # 80%
MIN_RESOLVED       = config.MIN_RESOLVED        # 30 trades before going live


# ── Database Setup ───────────────────────────────────────────────────────────

def _init_db():
    """Create tables if needed."""
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("""
        CREATE TABLE IF NOT EXISTS demo_trades (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id          TEXT    NOT NULL,
            market_id       TEXT    NOT NULL,
            market_question TEXT    NOT NULL,
            market_slug     TEXT    DEFAULT '',
            side            TEXT    NOT NULL DEFAULT 'YES',
            entry_price     REAL    NOT NULL,
            bet_amount      REAL    NOT NULL DEFAULT 1.00,
            win_amount      REAL    NOT NULL DEFAULT 0.00,
            result          TEXT    DEFAULT 'pending',
            pnl             REAL    DEFAULT 0.0,
            reasoning       TEXT    DEFAULT '',
            news_source     TEXT    DEFAULT '',
            model           TEXT    DEFAULT '',
            confidence      REAL    DEFAULT 0.0,
            market_outcome   TEXT   DEFAULT '',
            created_at      TEXT    NOT NULL,
            resolved_at     TEXT,
            token_id        TEXT    DEFAULT '',
            strategy        TEXT    DEFAULT '',
            materiality     REAL    DEFAULT 0.0,
            edge            REAL    DEFAULT 0.0,
            composite_score REAL    DEFAULT 0.0,
            news_context    TEXT    DEFAULT '',
            signals_json    TEXT    DEFAULT '{}',
            close_time      TEXT,
            close_hours     REAL    DEFAULT 0.0
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS demo_runs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id      TEXT    NOT NULL,
            started_at  TEXT    NOT NULL,
            ended_at    TEXT,
            markets     INTEGER DEFAULT 0,
            signals     INTEGER DEFAULT 0,
            trades      INTEGER DEFAULT 0,
            ai_calls    INTEGER DEFAULT 0,
            status      TEXT    DEFAULT 'running'
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS demo_news (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id      TEXT    NOT NULL,
            headline    TEXT    NOT NULL,
            source      TEXT    DEFAULT '',
            url         TEXT    DEFAULT '',
            fetched_at  TEXT    NOT NULL
        )
    """)
    # Add missing columns safely
    for col, typ in [
        ("token_id", "TEXT"), ("strategy", "TEXT"), ("materiality", "REAL"),
        ("edge", "REAL"), ("composite_score", "REAL"), ("news_context", "TEXT"),
        ("signals_json", "TEXT"), ("close_time", "TEXT"), ("close_hours", "REAL"),
    ]:
        try:
            con.execute(f"ALTER TABLE demo_trades ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError:
            pass
    con.commit()
    con.close()


_init_db()


def _db():
    """Get a connection with WAL mode."""
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA journal_mode=WAL")
    con.row_factory = sqlite3.Row
    return con


# ── Trade Logging ────────────────────────────────────────────────────────────

def _log_demo_trade(signal, token_id: str = "", strategy: str = "",
                    news_context: str = "", signals: dict | None = None) -> int:
    """Log a demo trade to the database. Returns the trade ID."""
    run_id = f"demo_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    now = datetime.now(timezone.utc).isoformat()
    con = _db()
    cur = con.execute("""
        INSERT INTO demo_trades (
            run_id, market_id, market_question, market_slug, side, entry_price,
            bet_amount, win_amount, result, pnl, reasoning, news_source, model,
            confidence, market_outcome, created_at, token_id, strategy,
            materiality, edge, composite_score, news_context, signals_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_id,
        signal.market.condition_id,
        signal.market.question,
        getattr(signal.market, "slug", ""),
        signal.side,
        signal.market_price,
        signal.bet_amount,
        round(signal.bet_amount * (1.0 / signal.market_price - 1.0) if signal.market_price > 0 else 0, 2),
        "pending",
        0.0,
        signal.reasoning,
        signal.news_source,
        config.CLASSIFICATION_MODEL,
        signal.claude_score,
        "pending",
        now,
        token_id,
        strategy,
        signal.materiality,
        signal.edge,
        signal.composite_score,
        news_context,
        json.dumps(signals or {}),
    ))
    trade_id = cur.lastrowid
    con.commit()
    con.close()
    return trade_id


def _wipe_all_trades():
    """Delete ALL trades from the database."""
    con = _db()
    con.execute("DELETE FROM demo_trades")
    con.commit()
    con.close()
    console.print("[bold red]🗑️  All demo trades wiped.[/bold red]")


# ── Accuracy Stats ───────────────────────────────────────────────────────────

def get_accuracy_stats() -> dict:
    """Get overall accuracy statistics."""
    con = _db()
    row = con.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN result = 'win' THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN result = 'loss' THEN 1 ELSE 0 END) as losses,
            SUM(CASE WHEN result = 'push' THEN 1 ELSE 0 END) as pushes,
            SUM(CASE WHEN result = 'void' THEN 1 ELSE 0 END) as voids,
            COALESCE(SUM(pnl), 0) as total_pnl,
            COUNT(CASE WHEN result != 'pending' AND result != 'void' THEN 1 END) as resolved
        FROM demo_trades
    """).fetchone()
    con.close()

    total = row["total"] or 0
    wins = row["wins"] or 0
    losses = row["losses"] or 0
    pushes = row["pushes"] or 0
    voids = row["voids"] or 0
    resolved = row["resolved"] or 0
    total_pnl = row["total_pnl"] or 0.0

    decisive = wins + losses
    accuracy = (wins / decisive * 100) if decisive > 0 else 0.0

    return {
        "total_trades": total,
        "total_resolved": resolved,
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "voids": voids,
        "accuracy_pct": accuracy,
        "total_pnl": total_pnl,
        "ready_for_live": resolved >= MIN_RESOLVED and accuracy >= ACCURACY_THRESHOLD,
    }


def get_resolved_trade_list() -> list[dict]:
    """Get list of resolved trades with outcomes."""
    con = _db()
    rows = con.execute("""
        SELECT id, market_question, side, entry_price, bet_amount,
               result, pnl, reasoning, strategy, materiality, edge,
               composite_score, news_context, signals_json, created_at, resolved_at
        FROM demo_trades
        WHERE result IN ('win', 'loss', 'push')
        ORDER BY resolved_at DESC
        LIMIT 100
    """).fetchall()
    con.close()
    return [dict(r) for r in rows]


def _print_accuracy_oneliner():
    """Print a one-line accuracy summary."""
    stats = get_accuracy_stats()
    if stats["total_resolved"] == 0:
        console.print(f"  [dim]📊 0 resolved trades (pending markets...)[/dim]")
        return
    color = "bright_green" if stats["accuracy_pct"] >= ACCURACY_THRESHOLD else "yellow" if stats["accuracy_pct"] >= 50 else "red"
    console.print(
        f"  [dim]📊 [{color}]{stats['accuracy_pct']:.1f}% accuracy[/] "
        f"({stats['wins']}W/{stats['losses']}L/{stats['pushes']}P) "
        f"PnL: ${stats['total_pnl']:+.2f}[/dim]"
    )


# ── Resolution ───────────────────────────────────────────────────────────────

def run_resolution_check(verbose: bool = False) -> dict:
    """Check pending trades against resolved markets."""
    from resolver import check_market_resolution

    con = _db()
    pending = con.execute("""
        SELECT id, market_id, market_question, side, entry_price, bet_amount, token_id
        FROM demo_trades WHERE result = 'pending'
    """).fetchall()
    con.close()

    resolved_count = 0
    for trade in pending:
        try:
            trade_dict = dict(trade)
            market_result = check_market_resolution(trade_dict)
            if market_result is None:
                continue

            # market_result: 1.0 (YES), 0.0 (NO)
            side = trade["side"]
            entry_price = float(trade["entry_price"])
            bet_amount = float(trade["bet_amount"])

            if (side == "YES" and market_result == 1.0) or \
               (side == "NO" and market_result == 0.0):
                result = "win"
                bet_price = entry_price if side == "YES" else (1.0 - entry_price)
                bet_price = max(0.01, min(0.99, bet_price))
                payout_ratio = (1.0 - bet_price) / bet_price
                pnl = round(bet_amount * payout_ratio, 4)
                outcome = "yes" if market_result == 1.0 else "no"
            else:
                result = "loss"
                pnl = -bet_amount
                outcome = "no" if market_result == 1.0 else "yes"

            con = _db()
            con.execute("""
                UPDATE demo_trades
                SET result = ?, pnl = ?, resolved_at = ?, market_outcome = ?
                WHERE id = ?
            """, (result, pnl, datetime.now(timezone.utc).isoformat(), outcome, trade["id"]))
            con.commit()
            con.close()
            resolved_count += 1

            if verbose:
                sym = "✅" if result == "win" else "❌" if result == "loss" else "↩️"
                console.print(f"  {sym} #{trade['id']} {trade['market_question'][:50]} → {result} (${pnl:+.2f})")
        except Exception as e:
            log.debug(f"[resolve] #{trade['id']} error: {e}")

    return {"resolved": resolved_count, "checked": len(pending)}


# ── Market Fetching ──────────────────────────────────────────────────────────

def _fetch_day_markets():
    """Fetch markets closing within the demo window."""
    from markets import fetch_active_markets, filter_by_categories
    from datetime import datetime, timezone

    all_markets = fetch_active_markets(limit=500)

    # Filter by closing time
    now = datetime.now(timezone.utc)
    window_markets = []
    for m in all_markets:
        try:
            close_str = getattr(m, "end_date_iso", None) or getattr(m, "end_date", None)
            if close_str:
                close_dt = datetime.fromisoformat(close_str.replace("Z", "+00:00"))
                hours_left = (close_dt - now).total_seconds() / 3600
                if 0 < hours_left <= DEMO_HOURS_WINDOW:
                    window_markets.append(m)
        except Exception:
            pass

    # Also include markets without close dates (might be active)
    for m in all_markets:
        if not (getattr(m, "end_date_iso", None) or getattr(m, "end_date", None)):
            window_markets.append(m)

    return window_markets


def _hours_left(market) -> float:
    """Calculate hours until market closes."""
    try:
        close_str = getattr(market, "end_date_iso", None) or getattr(market, "end_date", None)
        if close_str:
            close_dt = datetime.fromisoformat(close_str.replace("Z", "+00:00"))
            return max(0, (close_dt - datetime.now(timezone.utc)).total_seconds() / 3600)
    except Exception:
        pass
    return DEMO_HOURS_WINDOW  # default to window if unknown


# ── Scan & Trade ─────────────────────────────────────────────────────────────

def scan_and_trade() -> dict:
    """Main scan: fetch markets → research → log trades."""
    from news_stream import NewsAggregator
    from markets import fetch_active_markets
    from scraper import scrape_all

    console.print(f"\n[bold cyan]═══ SCAN @ {datetime.now().strftime('%H:%M:%S')} ═══[/bold cyan]")

    # 1. Fetch markets in window
    day_markets = _fetch_day_markets()
    console.print(f"  📊 {len(day_markets)} markets in {DEMO_HOURS_WINDOW:.0f}h window")

    if not day_markets:
        console.print("  [yellow]No markets in window. Skipping scan.[/yellow]")
        return {"markets": 0, "signals": 0}

    # 2. Scrape news
    try:
        news_items = scrape_all(config.NEWS_LOOKBACK_HOURS)
        console.print(f"  📰 {len(news_items)} headlines scraped")
    except Exception as e:
        log.warning(f"[engine] news scrape failed: {e}")
        news_items = []

    # 3. Fetch broader market universe for context
    try:
        all_candidates = fetch_active_markets(limit=500)
    except Exception as e:
        log.warning(f"[engine] market fetch failed: {e}")
        all_candidates = day_markets

    # Use all_candidates for wider coverage (not just day_markets)
    # This catches markets that might not have end_date but are still tradeable
    if len(all_candidates) < len(day_markets):
        all_candidates = day_markets

    # ── Hard Blocklist ────────────────────────────────────────────────────────
    # Proven untradeable patterns: stock tickers, crypto exact prices, esports
    HARD_SKIP = [
        # ── Stock tickers (AI can't predict daily stock movements) ──
        "(aapl)", "(tsla)", "(nvda)", "(amzn)", "(googl)", "(meta)", "(nflx)", "(pltr)", "(coin)",
        "(hood)", "(mstr)",
        "s&p 500 close", "nasdaq close", "dow jones close",
        "stock close", "stock price", "share price",
        # ── Crypto exact price ranges (AI can't predict precise price levels) ──
        "be between $", "be above $", "be below $",
        "price of bitcoin", "price of ethereum", "price of solana",
        "close above $", "close below $",
        # ── Esports (pure luck/skill — 0% AI edge) ──
        "(bo1)", "(bo3)", "(bo5)", "map 1 winner", "map 2 winner", "map 3 winner",
        "first blood", "first tower", "first baron", "quadra kill", "penta kill",
        "dragon soul", "inhibitor",
        "dota 2", "valorant", "counter-strike", "league of legends", " lol:", " lol ",
        "league of legends european championship", "lck 2026", "lcs 2026", "msi 2026",
        "cblol 2026",
        "call of duty", "cdl", "overwatch", "rainbow six",
        # ── Over/Under markets (random coin flips, no informational edge) ──
        "o/u ", "o/u", "over/under", "over under",
        # ── Short-window crypto price (15-min Bitcoin windows = coin flip) ──
        "bitcoin up or down", "ethereum up or down", "sol up or down",
        "btc up or down", "eth up or down",
        # ── Player props (0% accuracy historically — proven money drain) ──
        "anytime goalscorer", "anytime scorer", "first goalscorer",
        "first scorer", "last scorer", "to score first",
        "player props", "player to score",
        "win by ko", "win by tko", "win by submission",
        "ko or tko", "tko or ko", "knockdown", "knock out",
        "fight to go the distance", "go the distance",
        "round betting", "method of victory",
        # ── Exact score props (proven noise) ──
        "correct score", "exact score",
        # ── WEATHER MARKETS (coin flips — AI has NO edge on temperature) ──
        "highest temperature", "lowest temperature", "temperature in",
        "weather in", "rain in", "snow in", "humidity in",
        "wind speed", "heat wave", "cold snap",
        # ── COMMODITY PRICE TARGETS (AI can't predict exact price levels) ──
        "hit (high)", "hit (low)", "natural gas (ng)", "wti crude oil",
        "crude oil", "gold (gc)", "silver (si)", "copper (hg)",
        # ── GAMING SPEEDRUNS (pure skill/luck, no informational edge) ──
        "speedrun", "xqc", "forsen", "minecraft speedrun",
        # ── POLITICAL NOMINATIONS (too uncertain, low signal) ──
        "republican nominee", "democratic nominee",
        # ── ICEMAN / NICHE SHOW PROPS (no reliable data) ──
        "iceman", "be said on",
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
    # ★ HIGH THROUGHPUT: 200 AI calls per scan — covers ~60+ markets
    ai_calls_left = config.MAX_AI_CALLS_PER_SCAN
    skip_reasons: dict[str, int] = {}  # diagnostic: why markets get skipped
    def _skip(reason: str):
        skip_reasons[reason] = skip_reasons.get(reason, 0) + 1

    from bankroll import kelly_bet_size, get_current_bankroll, can_trade_today
    from edge import Signal as _Signal

    CRYPTO_KW = [
        "bitcoin","btc","ethereum","eth","solana","sol","dogecoin","doge",
        "xrp","bnb","hyperliquid","cardano","ada","avax","polkadot","dot",
        "chainlink","litecoin","ltc","polygon","matic","uniswap","pepe","shib","crypto",
    ]

    # ★ HIGH THROUGHPUT: 600 markets per scan — maximum coverage
    MAX_MARKETS = config.MAX_MARKETS_PER_SCAN

    # Get already-logged market IDs to avoid duplicates (ALL trades, not just pending)
    already_logged: set[str] = set()
    try:
        con = _db()
        rows = con.execute(
            "SELECT DISTINCT market_id FROM demo_trades"
        ).fetchall()
        con.close()
        already_logged = {r["market_id"] for r in rows}
    except Exception:
        pass

    for market in all_candidates[:MAX_MARKETS]:
        analyzed += 1
        q_lower   = market.question.lower()

        matched_pat = next((pat for pat in HARD_SKIP if pat in q_lower), None)
        if matched_pat:
            _skip("hard_blocklist")
            log.info(f"  [blocklist] #{market.condition_id[:8]} matched '{matched_pat}' → \"{market.question[:60]}\"")
            continue
        # Regex blocklist patterns — REMOVED "will X win" (too broad, blocks legit markets)
        # The hard blocklist above covers the truly untradeable ones

        hours_left = _hours_left(market)
        price      = market.yes_price
        tok        = token_map.get(market.condition_id)

        if hours_left > DEMO_HOURS_WINDOW:
            _skip("hours_gt_window")
            continue
        # ── FAST-RESOLUTION FILTER: only trade markets closing within MAX_HOURS_TO_CLOSE ──
        if hours_left > config.MAX_HOURS_TO_CLOSE:
            _skip("too_far_out")
            continue
        # ── PRICING TABLE ──
        # YES trades: entry 0.10–0.40 (buy cheap YES, win $1 = 150-900% ROI)
        # NO trades:  entry when YES ≥ 0.65 (NO share ≤ 0.35, win $1 = 186-900% ROI)
        # DEAD ZONE:  YES 0.41–0.64 = low ROI either direction, skip
        if price < config.MIN_YES_ENTRY_PRICE or price > config.MAX_NO_ENTRY_PRICE:
            _skip("price_extreme")
            continue
        # Dead-zone gate: skip markets where YES price is in the middle (low ROI)
        if price >= config.DEAD_ZONE_LOW and price <= config.DEAD_ZONE_HIGH:
            _skip("dead_zone")
            continue

        is_crypto = any(k in q_lower for k in CRYPTO_KW)
        is_sweet  = 0.30 <= price <= 0.70   # 1:1 to 2.3:1 payout range

        # Crypto markets now allowed — new consensus engine can handle them

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

        # ★ WIDE: analyze any market closing within window
        should_research = (
            ai_calls_left > 0 and hours_left <= DEMO_HOURS_WINDOW
            and market.volume >= 0
        )
        if should_research:
            try:
                gem_res_obj = research_market(market, news_context=matched_headlines)
                if gem_res_obj.direction in ("bullish","bearish") and gem_res_obj.materiality >= 0.15:
                    gem_dir  = gem_res_obj.direction
                    gem_mat  = gem_res_obj.materiality
                    # BUG FIX: materiality ≠ probability!
                    # Use actual model probability if available; otherwise
                    # conservatively estimate: market_price ± small edge
                    model_prob = getattr(gem_res_obj, 'probability', None)
                    if model_prob and 0.05 < model_prob < 0.95:
                        gem_conf = model_prob
                    else:
                        # Conservative fallback: assume 10-15% edge over market
                        if gem_dir == "bullish":
                            gem_conf = min(price + 0.12, 0.75)
                        else:
                            gem_conf = min((1 - price) + 0.12, 0.75)
                        gem_conf = max(gem_conf, 0.15)
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
                from classifier import PROMPTS as _PROMPTS, _call_llm_async
                from classifier import SKEPTIC_PROMPT, REFLECTOR_PROMPT
                
                for p_idx in range(1, config.CONSENSUS_PASSES):
                    if ai_calls_left <= 0: break
                    
                    # Use the CORRECT skeptic/reflector prompt for each pass
                    prompt_tmpl = _PROMPTS[p_idx % len(_PROMPTS)]
                    p_prompt = prompt_tmpl.format(
                        question=market.question,
                        yes_price=market.yes_price,
                        headline=matched_headlines[0] if matched_headlines else market.question,
                        source="consensus_pass",
                    )
                    
                    try:
                        p_text = asyncio.run(_call_llm_async(p_prompt, temperature=0.15))
                        p_res  = _parse_json_response(p_text)
                        p_dir  = p_res.get("direction", "neutral")
                        p_mat  = max(0.0, min(1.0, float(p_res.get("materiality", 0))))
                        
                        if p_dir not in ("bullish", "bearish", "neutral"):
                            p_dir = "neutral"
                        
                        # Only block on OPPOSITE direction (bearish vs bullish).
                        # "neutral" from skeptic is NOT a disagreement — the skeptic
                        # just didn't find strong counter-evidence, which is fine.
                        if p_dir != "neutral" and p_dir != gem_dir:
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
        signals_record["rrf"]       = f"{gem_dir}:{rrf_score:.3f}" if rrf_score >= 0.45 else "neutral"

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

        # ── 2-DAY STRATEGY TRIAL — ALL COMBOS ─────────────────────────
        # Every market tested against every strategy simultaneously.
        # Strategies include signal combos + consensus + RRF composite
        # + materiality + recency + price room.

        def _dir(d): return "YES" if d == "bullish" else "NO"
        strategies_to_try: list[tuple[str, str, float]] = []

        # ── CONSENSUS-FIRST ENGINE ──
        # Past trial: S8 alone hit 47% (random). RRF score isn't enough.
        # The ONLY proven path is consensus (AI + Skeptic both agree).
        # We allow S8 only when RRF is EXTREMELY high (≥0.70) AND consensus agrees.

        non_neutral_count = sum(1 for l,d,c in all_sigs if d != "neutral" and c > 0)

        # ★ HIGH-VOLUME STRATEGY ENGINE — More trades, price-window = safety net
        # Breakeven at ~25% accuracy (avg entry $0.25), so we can afford volume.
        # The dead-zone filter + price caps already guarantee high-ROI setups.

        # ── HIGH-VOLUME STRATEGY ENGINE ──
        # Goal: take MANY trades with any edge signal. Dead-zone (0.35-0.65)
        # + price caps already guarantee 1.5x-6x payout. Breakeven at 20-40%.
        # We fire aggressively — AI direction alone is enough to trade.

        # S1: AI SIGNAL — any AI direction with decent confidence (PRIMARY DRIVER)
        # S1: AI SIGNAL — 35%+ confidence triggers (PRIMARY VOLUME DRIVER)
        if gem_dir != "neutral" and gem_conf >= 0.35:
            strategies_to_try.append(("S1_ai_signal", _dir(gem_dir), gem_conf))

        # S2: AI + NEWS — AI direction + news materiality (lowered from 0.40)
        if gem_dir != "neutral" and gem_mat >= 0.25 and has_news:
            strategies_to_try.append(("S2_ai_news", _dir(gem_dir), max(gem_conf, 0.35)))

        # S3: MULTI-SIGNAL — any 2+ non-neutral signals agree direction
        if n_agree >= 2:
            strategies_to_try.append(("S3_multi_signal", best_side, max(best_score, 0.30)))

        # S4: PRICE-FLOW — price flow signal + any AI agreement
        if pf_dir != "neutral" and pf_conf >= 0.35 and (gem_dir == "neutral" or gem_dir == pf_dir):
            strategies_to_try.append(("S4_price_flow", _dir(pf_dir), pf_conf))

        # S5: COPY-WHALE — whale or copy signal + any AI agreement
        if ((cp_dir != "neutral" and cp_conf >= 0.35) or (wh_dir != "neutral" and wh_conf >= 0.35)):
            sig_conf = max(cp_conf, wh_conf)
            sig_dir = cp_dir if cp_dir != "neutral" else wh_dir
            if gem_dir == "neutral" or gem_dir == sig_dir:
                strategies_to_try.append(("S5_copy_whale", _dir(sig_dir), max(sig_conf, gem_conf)))

        # S6: HIGH-RRF — RRF composite score indicates edge
        # S6: HIGH-RRF — require 0.45+ RRF for quality trades
        if gem_dir != "neutral" and rrf_score >= 0.45:
            strategies_to_try.append(("S6_high_rrf", _dir(gem_dir), max(gem_conf, rrf_score)))

        # S7: CONSENSUS — AI + skeptic agree (highest quality)
        # S7: CONSENSUS — AI + skeptic agree (lowered for volume)
        if gem_dir != "neutral" and consensus_agreed and consensus_score >= 0.30:
            strategies_to_try.append(("S7_consensus", _dir(gem_dir), max(gem_conf, consensus_score)))

        # S8: SURESHOT — AI very confident + news + multi-signal (top quality)
        if (gem_dir != "neutral" and gem_conf >= 0.50 and gem_mat >= 0.50
                and has_news and n_agree >= 1):
            strategies_to_try.append(("S8_sureshot", _dir(gem_dir), gem_conf))

        # S9: DEAD ZONE NO — bearish on high-price YES markets
        # S9: DEAD ZONE NO — bearish on high-price YES (lowered from 0.55)
        if gem_dir == "bearish" and gem_conf >= 0.45 and price >= 0.65:
            strategies_to_try.append(("S9_deadzone_no", "NO", gem_conf))

        # S10: PRICE OUTCOME — strongly directional price flow in extreme markets
        if price <= 0.20 and pf_dir == "bullish" and pf_conf >= 0.30:
            strategies_to_try.append(("S10_price_yes", "YES", pf_conf))
        elif price >= 0.80 and pf_dir == "bearish" and pf_conf >= 0.30:
            strategies_to_try.append(("S10_price_no", "NO", pf_conf))

        if not strategies_to_try:
            _skip("no_strategy_fired")
            continue

        # ── PER-MARKET DEDUP: pick the SINGLE best strategy per market ──
        # Previously: 1 market spawned 5+ duplicate rows (inflated stats).
        # Now: each market produces exactly ONE trade under its top strategy.
        # Priority order based on empirical accuracy from the trial:
        STRAT_PRIORITY = {
            "S8_sureshot":       200,  # AI very confident + news + multi-signal
            "S7_consensus":       180,  # AI + skeptic agree (highest quality)
            "S2_ai_news":         160,  # AI + news materiality
            "S3_multi_signal":    150,  # 2+ signals agree
            "S5_copy_whale":      140,  # Copy/whale + AI agreement
            "S6_high_rrf":        130,  # RRF composite high
            "S1_ai_signal":       120,  # AI signal alone (primary volume driver)
            "S9_deadzone_no":     110,  # Bearish on high-price YES
            "S4_price_flow":      100,  # Price flow signal
            "S10_price_yes":       90,  # Price flow on extreme YES
            "S10_price_no":        90,  # Price flow on extreme NO
            "S12_ai_solo":        65,  # AI solo — no consensus
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
            # ── ROI FILTER: Target 300% ROI — all strategies use same caps ──
            max_price = config.MAX_BUY_PRICE if strat_side == "YES" else config.MAX_NO_BUY_PRICE
            if bet_price > max_price:
                _skip("roi_too_low")
                roi_pct = (1.0 / bet_price - 1.0) * 100
                log.debug(f"[strategy] SKIP {strat_name} {strat_side} bet_price={bet_price:.2f} — max={max_price:.2f}")
                continue
            payout_ratio = (1.0 - bet_price) / bet_price
            ev           = strat_score * payout_ratio - (1.0 - strat_score)
            # EV filter REMOVED — price caps already guarantee high-ROI setups
            # Breakeven at ~25% accuracy with avg entry 0.25, so volume > precision

            edge  = strat_score - bet_price
            bet   = kelly_bet_size(bk, edge, bet_price, materiality=gem_mat)
            bet   = min(bet, bk * 0.10)   # 10% cap — aggressive during demo phase
            bet   = round(max(0.50, bet), 2)
            win_a = round(bet * payout_ratio, 2)

            sig = _Signal(
                market=market, claude_score=strat_score, market_price=price,
                edge=edge, side=strat_side, bet_amount=bet,
                reasoning=f"strategy={strat_name} score={strat_score:.2f} ev={ev:.3f}",
                headlines="", news_source="strategy_trial",
                classification=("bullish" if strat_side=="YES" else "bearish"),
                materiality=gem_mat, composite_score=rrf_score,
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

    ai_used = int(os.getenv("MAX_AI_CALLS_PER_SCAN", "120")) - ai_calls_left
    if not signals_found:
        console.print(f"  [yellow]No trades this scan — {analyzed} markets analyzed, {ai_used} AI calls used.[/yellow]")
    else:
        console.print(f"\n  ✅ {demos_logged} trades | {analyzed} analyzed | {ai_used} AI calls used")

    # Diagnostic: print skip reasons so we know why markets are filtered
    if skip_reasons:
        parts = [f"{k}:{v}" for k, v in sorted(skip_reasons.items(), key=lambda x: -x[1])]
        console.print(f"  [dim]Skip reasons → {' | '.join(parts)}[/dim]")

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


def _startup_cleanup():
    """Remove orphaned pending trades older than 168h (market probably resolved without us)."""
    try:
        con = _db()
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=168)).isoformat()
        res = con.execute(
            "DELETE FROM demo_trades WHERE result = 'pending' AND created_at < ?",
            (cutoff,)
        )
        if res.rowcount > 0:
            console.print(f"  [dim]🧹 Cleaned {res.rowcount} stale pending trades (>168h)[/dim]")
        con.commit()
        con.close()
    except Exception as e:
        log.debug(f"[cleanup] {e}")


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
        f"  7. Composite < 0.3 → SKIP  |  ≥ 0.3 → log demo trade\n\n"
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