#!/usr/bin/env python3
"""Lightweight Polymarket pipeline dashboard — reads bot.db (demo_trades table).

Usage:
    python web_dashboard.py                   # default port 8080
    python web_dashboard.py --port 9000       # custom port
    python web_dashboard.py --diagnostics     # print db config then exit
    python web_dashboard.py --setup-token VALUE
    python web_dashboard.py --delete-token VALUE
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from flask import Flask, jsonify, render_template_string, request

    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False

try:
    import config as cfg
except Exception:
    cfg = None

# Use the SAME DB as logger.py and demo_runner.py
from logger import DB_PATH

# ── CLI ──────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="Polymarket pipeline dashboard")
parser.add_argument("--port", type=int, default=8080)
parser.add_argument("--bind", default="0.0.0.0")
parser.add_argument("--diagnostics", action="store_true",
                    help="Print DB config and exit")
parser.add_argument("--setup-token", type=str, default=None,
                    help="Store a Polymarket auth token (CLOB API key) for on-chain CTF exchange resolution via the setup page")
parser.add_argument("--delete-token", type=str, default=None,
                    help="Delete a stored Polymarket auth token by 4-char prefix")
CLI_ARGS, _ = parser.parse_known_args()

if CLI_ARGS.diagnostics:
    print(f"DB_PATH={DB_PATH}")
    print(f"EXISTS={Path(DB_PATH).is_file()}")
    sys.exit(0)

if CLI_ARGS.setup_token:
    sys.exit(0)
if CLI_ARGS.delete_token:
    sys.exit(0)

if not HAS_FLASK:
    print("Flask is required: pip install flask", file=sys.stderr)
    sys.exit(1)

# ── Helpers ──────────────────────────────────────────────────────────────────

def _q(sql: str, params: tuple = ()) -> list[dict]:
    if not Path(DB_PATH).is_file():
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    except Exception:
        return []
    finally:
        conn.close()


def _cfg(name: str, default):
    """Read config/env values safely."""
    env_val = os.getenv(name)
    if env_val is not None:
        return env_val
    if cfg and hasattr(cfg, name):
        return getattr(cfg, name)
    return default


def _cfg_bool(name: str, default: bool) -> bool:
    val = _cfg(name, default)
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("true", "1", "yes", "on")
    return bool(val)


def _cfg_list(name: str, default: list) -> list:
    val = _cfg(name, default)
    if isinstance(val, (list, tuple)):
        return list(val)
    if isinstance(val, str):
        return [x.strip() for x in val.split(",") if x.strip()]
    return default


# ── Data helpers (demo_trades schema) ────────────────────────────────────────
# demo_trades columns: id, run_id, market_id, market_question, market_slug,
#   side, entry_price, bet_amount, win_amount, result, pnl, reasoning,
#   news_source, model, confidence, market_outcome, created_at, resolved_at,
#   token_id, strategy, materiality, edge, composite_score, news_context,
#   signals_json, close_time, close_hours

def _get_summary() -> dict:
    """Aggregate stats from demo_trades."""
    total_trades = 0
    try:
        total_trades = _q("SELECT COUNT(*) as c FROM demo_trades")[0]["c"]
    except Exception:
        pass

    try:
        total_resolved = _q(
            "SELECT COUNT(*) as c FROM demo_trades WHERE result != 'pending' AND result IS NOT NULL AND result != ''"
        )[0]["c"]
    except Exception:
        total_resolved = 0
    try:
        pending = _q(
            "SELECT COUNT(*) as c FROM demo_trades WHERE result IS NULL OR result = '' OR result = 'pending'"
        )[0]["c"]
    except Exception:
        pending = 0
    try:
        wins = _q("SELECT COUNT(*) as c FROM demo_trades WHERE result = 'win'")[0]["c"]
    except Exception:
        wins = 0
    try:
        losses = _q("SELECT COUNT(*) as c FROM demo_trades WHERE result = 'loss'")[0]["c"]
    except Exception:
        losses = 0

    # PnL: use the stored pnl column directly
    total_pnl = 0.0
    accuracy_pct = 0.0
    if total_resolved > 0:
        accuracy_pct = round(wins / total_resolved * 100, 1)
        try:
            pnl_row = _q("SELECT COALESCE(SUM(pnl), 0) as p FROM demo_trades WHERE result != 'pending' AND result IS NOT NULL")
            total_pnl = round(pnl_row[0]["p"] or 0, 2)
        except Exception:
            total_pnl = 0.0

    # Today's PnL
    todays_pnl = 0.0
    try:
        today_start = datetime.utcnow().strftime("%Y-%m-%d 00:00:00")
        pnl_today_row = _q(
            "SELECT COALESCE(SUM(pnl), 0) as p FROM demo_trades WHERE result != 'pending' AND result IS NOT NULL AND created_at >= ?",
            (today_start,),
        )
        todays_pnl = round(pnl_today_row[0]["p"] or 0, 2)
    except Exception:
        pass

    min_resolved = int(_cfg("MIN_RESOLVED_TRADES", 20))
    acc_threshold = float(_cfg("ACCURACY_THRESHOLD", 80.0))
    can_go = total_resolved >= min_resolved and accuracy_pct >= acc_threshold

    return {
        "bankroll": round(float(_cfg("BANKROLL_USD", 30)), 2),
        "todays_pnl": todays_pnl,
        "total_pnl": total_pnl,
        "trades_today_allowed": True,
        "trade_block_reason": "ok",
        "accuracy_pct": accuracy_pct,
        "wins": wins,
        "losses": losses,
        "resolved": total_resolved,
        "pending": pending,
        "total_trades": total_trades,
        "go_live_remaining": max(0, min_resolved - total_resolved),
        "can_go_live": can_go,
    }


def _get_recent_trades(limit: int = 30) -> list[dict]:
    """Read recent trades from demo_trades table in bot.db."""
    try:
        rows = _q(
            """SELECT id, created_at, market_question, market_slug,
                      side, entry_price, bet_amount, win_amount,
                      edge, pnl, confidence, materiality,
                      result, resolved_at, strategy, signals_json,
                      news_source, close_time, close_hours, reasoning,
                      composite_score, news_context, market_outcome
               FROM demo_trades
               ORDER BY id DESC LIMIT ?""",
            (limit,),
        )
    except Exception:
        return []

    now = datetime.utcnow()
    for r in rows:
        # Parse signals_json
        r["signals_parsed"] = {}
        if r.get("signals_json"):
            try:
                r["signals_parsed"] = json.loads(r["signals_json"])
            except Exception:
                r["signals_parsed"] = {}

        # Compute time-to-resolve
        r["time_to_resolve"] = ""
        if r.get("resolved_at") and r.get("created_at"):
            try:
                created = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
                resolved = datetime.fromisoformat(r["resolved_at"].replace("Z", "+00:00"))
                resolved = resolved.replace(tzinfo=None)
                created = created.replace(tzinfo=None)
                delta = resolved - created
                total_secs = int(delta.total_seconds())
                if total_secs < 0:
                    r["time_to_resolve"] = ""
                elif total_secs < 3600:
                    r["time_to_resolve"] = f"{total_secs // 60}m"
                elif total_secs < 86400:
                    r["time_to_resolve"] = f"{total_secs // 3600}h {(total_secs % 3600) // 60}m"
                else:
                    r["time_to_resolve"] = f"{total_secs // 86400}d {(total_secs % 86400) // 3600}h"
            except Exception:
                pass

        # Resolution Duration
        r["resolution_duration"] = ""
        close_time = r.get("close_time")
        resolved_at = r.get("resolved_at")
        created_at = r.get("created_at")
        duration_source = close_time or resolved_at
        if created_at:
            try:
                create_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00")).replace(tzinfo=None)
                if duration_source:
                    close_dt = datetime.fromisoformat(duration_source.replace("Z", "+00:00")).replace(tzinfo=None)
                else:
                    close_dt = now
                delta = close_dt - create_dt
                total_secs = int(delta.total_seconds())
                if total_secs < 0:
                    r["resolution_duration"] = "closed"
                elif total_secs < 60:
                    r["resolution_duration"] = f"{total_secs}s"
                elif total_secs < 3600:
                    r["resolution_duration"] = f"{total_secs // 60}m"
                elif total_secs < 86400:
                    r["resolution_duration"] = f"{total_secs // 3600}h {(total_secs % 3600) // 60}m"
                else:
                    r["resolution_duration"] = f"{total_secs // 86400}d {(total_secs % 86400) // 3600}h"
            except Exception:
                pass

        # Expected Profit (EV calculation)
        r["expected_profit"] = 0.0
        price = r.get("entry_price", 0.5)
        score = r.get("confidence", 0.5)
        if score is not None:
            score = max(0.0, min(1.0, float(score)))
        amount = r.get("bet_amount", 1.0)
        side = r.get("side", "YES")
        edge = r.get("edge", 0.0) or 0.0
        edge = max(-1.0, min(1.0, float(edge)))
        if amount:
            try:
                entry_price = None
                if price and price > 0.01 and price < 0.99:
                    entry_price = price
                elif edge and score:
                    entry_price = max(0.01, min(0.99, score - edge))

                if entry_price and entry_price > 0.01 and entry_price < 0.99:
                    if side == "YES":
                        potential_profit = amount * (1.0 / entry_price - 1.0)
                    else:
                        potential_profit = amount * (1.0 / (1.0 - entry_price) - 1.0)
                    ev = score * potential_profit - (1.0 - score) * amount
                    r["expected_profit"] = round(ev, 2)
                elif edge:
                    r["expected_profit"] = round(edge * amount, 2)
            except Exception:
                r["expected_profit"] = 0.0
    return rows


def _get_news(limit: int = 25) -> list[dict]:
    """Try demo_news first, fall back to news_events."""
    try:
        rows = _q(
            "SELECT headline, source as news_source, received_at, latency_ms, matched_markets, "
            "triggered_trades FROM demo_news ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        if rows:
            return rows
    except Exception:
        pass
    return _q(
        "SELECT headline, source as news_source, received_at, latency_ms, matched_markets, "
        "triggered_trades FROM news_events ORDER BY id DESC LIMIT ?",
        (limit,),
    )


def _get_runs(limit: int = 15) -> list[dict]:
    """Try demo_runs first, fall back to pipeline_runs."""
    try:
        rows = _q(
            "SELECT id, started_at, ended_at as finished_at, markets as markets_scanned, "
            "signals as signals_found, trades as trades_placed, status FROM demo_runs "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        if rows:
            return rows
    except Exception:
        pass
    return _q(
        "SELECT id, started_at, finished_at, markets_scanned, signals_found, "
        "trades_placed, status FROM pipeline_runs ORDER BY id DESC LIMIT ?",
        (limit,),
    )


def _get_expectations() -> dict:
    """Compute expected values from demo_trades."""
    try:
        resolved = _q(
            "SELECT COUNT(*) as c FROM demo_trades WHERE result IS NOT NULL AND result != '' AND result != 'pending'"
        )[0]["c"]
        wins = _q("SELECT COUNT(*) as c FROM demo_trades WHERE result = 'win'")[0]["c"]
        losses = _q("SELECT COUNT(*) as c FROM demo_trades WHERE result = 'loss'")[0]["c"]
        total = _q("SELECT COUNT(*) as c FROM demo_trades")[0]["c"]
    except Exception:
        return {"accuracy": 0.0, "trades_today": 0, "trades_24h": 0,
                "wins": 0, "losses": 0, "pending": 0, "total": 0,
                "avg_edge": 0.0, "avg_pnl": 0.0, "total_pnl": 0.0}

    accuracy = round(wins / resolved * 100, 1) if resolved else 0.0
    pending = total - resolved

    # 24h activity
    now = datetime.utcnow()
    cutoff_24h = (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S")
    try:
        trades_24h = _q(
            "SELECT COUNT(*) as c FROM demo_trades WHERE created_at >= ?", (cutoff_24h,)
        )[0]["c"]
    except Exception:
        trades_24h = 0

    # Today's trades
    today_start = now.strftime("%Y-%m-%d 00:00:00")
    try:
        trades_today = _q(
            "SELECT COUNT(*) as c FROM demo_trades WHERE created_at >= ?", (today_start,)
        )[0]["c"]
    except Exception:
        trades_today = 0

    # Avg edge
    try:
        avg_edge_row = _q("SELECT COALESCE(AVG(edge), 0) as v FROM demo_trades WHERE edge IS NOT NULL")
        avg_edge = round(avg_edge_row[0]["v"] or 0, 3)
    except Exception:
        avg_edge = 0.0

    # PnL stats
    try:
        total_pnl_row = _q("SELECT COALESCE(SUM(pnl), 0) as v FROM demo_trades WHERE result IS NOT NULL AND result != '' AND result != 'pending'")
        total_pnl = round(total_pnl_row[0]["v"] or 0, 2)
        avg_pnl_row = _q("SELECT COALESCE(AVG(pnl), 0) as v FROM demo_trades WHERE result IS NOT NULL AND result != '' AND result != 'pending'")
        avg_pnl = round(avg_pnl_row[0]["v"] or 0, 2)
    except Exception:
        total_pnl = 0.0
        avg_pnl = 0.0

    return {
        "accuracy": accuracy,
        "trades_today": trades_today,
        "trades_24h": trades_24h,
        "wins": wins,
        "losses": losses,
        "pending": pending,
        "total": total,
        "avg_edge": avg_edge,
        "avg_pnl": avg_pnl,
        "total_pnl": total_pnl,
    }


def _get_diagnostics() -> dict:
    """Count rows in all tables."""
    result: dict = {}
    if not Path(DB_PATH).is_file():
        return {"error": "DB not found", "db_path": DB_PATH}
    try:
        conn = sqlite3.connect(DB_PATH)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        for (tbl,) in tables:
            result[tbl] = conn.execute(f"SELECT COUNT(*) FROM [{tbl}]").fetchone()[0]
        conn.close()
    except Exception as e:
        result["error"] = str(e)
    result["db_path"] = DB_PATH
    return result


# ── Flask app ────────────────────────────────────────────────────────────────
app = Flask(__name__)


@app.route("/")
def index():
    bankroll = round(float(_cfg("BANKROLL_USD", 30)), 2)
    pct = float(_cfg("MAX_BET_PCT", 0.10))
    strategy = _cfg("BET_STRATEGY", "edge_weighted")
    max_usd = round(bankroll * pct, 2)
    ml = _cfg_bool("ENABLE_ML_SCORING", False)
    adaptive = _cfg_bool("ADAPTIVE_THRESHOLDS", False)
    risk_on = _cfg_bool("RISK_ENGINE_ENABLED", True)
    rake_pct = float(_cfg("REFERRAL_RAKE_PCT", 0.0))
    rake_cap = float(_cfg("REFERRAL_RAKE_CAP", 0.0))

    summary = _get_summary()
    trades = _get_recent_trades(limit=20)
    exp = _get_expectations()
    diag = _get_diagnostics()
    _ = _get_news(limit=1)
    _ = _get_runs(limit=3)
    now_ist = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    ist_str = now_ist.strftime("%a %d %b %Y, %I:%M %p IST")

    return render_template_string(
        TEMPLATE,
        summary=summary,
        trades=trades,
        exp=exp,
        diag=diag,
        now_ist=ist_str,
        bets=[],
        bankroll=bankroll,
        bankroll_pct=pct,
        max_bet_pct=pct,
        strategy=strategy,
        max_usd=max_usd,
        ml_enabled=ml,
        ml_model_version="",
        ml_features_json="[]",
        adaptive=adaptive,
        risk_on=risk_on,
        rake_pct=rake_pct,
        rake_cap=rake_cap,
        pair_desk_enabled=True,
        risk_engine_enabled=risk_on,
        risk_exposure=0.0,
        risk_max=0.0,
        risk_style="",
        risk_latest={},
        risk_history=[],
        resolutions_enabled=True,
        resolver_pending=summary.get("pending", 0),
        resolver_resolved=summary.get("resolved", 0),
        resolver_method="polymarket-clob-client",
        resolver_schedule="afternoon",
        news_enabled=True,
        news_sources_count=0,
        news_events_count=0,
        news_latest_source="",
        news_latest_latency="",
        scanner_enabled=True,
        scanner_name="Polygon.io",
        scanner_interval=int(_cfg("SCAN_INTERVAL_SECS", 15)),
        scanner_categories=_cfg_list("CATEGORIES", []),
        scanner_markets=0,
        scanner_min_volume=float(_cfg("MIN_VOLUME_USD", 1000)),
        scanner_min_liquidity=float(_cfg("MIN_LIQUIDITY", 1000)),
        calibrator_enabled=False,
        calibrator_schedule="",
        calibrator_thresholds="",
        calibrator_last_run="",
        trade_log=trades,
        pnl_history_json="[]",
        pnl_chart_labels="[]",
        pnl_chart_data="[]",
        pnl_chart_edge_data="[]",
        pnl_chart_ev_data="[]",
        pnl_chart_brier_data="[]",
        pnl_chart_pot_data="[]",
        total_pnl=summary.get("total_pnl", 0.0),
        todays_pnl=summary.get("todays_pnl", 0.0),
        today_trades=0,
        today_wins=0,
        today_losses=0,
        today_pending=0,
        today_win_rate=0.0,
        today_avg_edge=0.0,
        today_pnl_color="gray",
        pnl_color="gray",
        max_win="N/A",
        max_loss="N/A",
        win_count=str(summary.get("wins", 0)),
        loss_count=str(summary.get("losses", 0)),
        avg_win=0.0,
        avg_loss=0.0,
        win_loss_ratio="N/A",
        hot_streak="N/A",
        cold_streak="N/A",
        risk_streak_desc="",
        streak_is_hot=False,
        streak_is_cold=False,
        go_live_status="LIVE" if summary.get("can_go_live") else "DRY-RUN",
        go_live_class="enabled" if summary.get("can_go_live") else "disabled",
        go_live_remaining=summary.get("go_live_remaining", 0),
        go_live_accuracy=summary.get("accuracy_pct", 0),
        go_live_resolved=summary.get("resolved", 0),
        bankroll_history_json="[]",
        kelly_pct="0.0",
        drawdown_current="0.0%",
        drawdown_max="0.0%",
        bankroll_chart_labels="[]",
        bankroll_chart_data="[]",
        bankroll_chart_wins="[]",
        bankroll_chart_losses="[]",
        go_live_confirmed=_cfg_bool("GO_LIVE_CONFIRMED", False),
        accuracy=summary.get("accuracy_pct", 0),
        accuracy_color="#f5f5f5",
        accuracy_history_json="[]",
        accuracy_chart_labels="[]",
        accuracy_chart_data="[]",
        accuracy_chart_brier="[]",
        accuracy_chart_ci_lower="[]",
        accuracy_chart_ci_upper="[]",
        resolved_count=summary.get("resolved", 0),
        brier_score="N/A",
        log_score="N/A",
        testnet_mode=False,
    )


@app.route("/diagnostics")
def diagnostics():
    return jsonify(_get_diagnostics())


@app.route("/expectations")
def expectations():
    return jsonify(_get_expectations())


@app.route("/debug_duration")
def debug_duration():
    try:
        if not Path(DB_PATH).is_file():
            return jsonify({"error": "DB not found", "db_path": DB_PATH}), 404
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            trades = [dict(r) for r in conn.execute(
                "SELECT id, market_question, created_at, resolved_at, close_time, result "
                "FROM demo_trades ORDER BY id DESC LIMIT 10"
            ).fetchall()]
        except Exception:
            trades = []
        conn.close()
        now = datetime.utcnow()
        for t in trades:
            created_at = t.get("created_at")
            close_time = t.get("close_time")
            resolved_at = t.get("resolved_at")
            duration_source = close_time or resolved_at
            t["computed_duration"] = None
            if created_at:
                try:
                    create_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00")).replace(tzinfo=None)
                    if duration_source:
                        close_dt = datetime.fromisoformat(duration_source.replace("Z", "+00:00")).replace(tzinfo=None)
                    else:
                        close_dt = now
                    delta = close_dt - create_dt
                    t["computed_duration"] = f"{int(delta.total_seconds() // 3600)}h {int((delta.total_seconds() % 3600) // 60)}m"
                except Exception as e:
                    t["computed_duration"] = f"error: {e}"
            t["status"] = t.get("result", "unknown")
            t["has_close_time"] = close_time is not None
            t["has_resolved_at"] = resolved_at is not None
        return jsonify({"db_path": DB_PATH, "sample": trades})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/health")
def api_health():
    """Health check endpoint."""
    trades = _q("SELECT COUNT(*) as c FROM demo_trades")
    return jsonify({
        "status": "ok",
        "db_exists": Path(DB_PATH).is_file(),
        "total_trades": trades[0]["c"] if trades else 0,
        "uptime": "running",
    })

@app.route("/api/summary")
def api_summary():
    """JSON API: summary stats."""
    return jsonify(_get_summary())


@app.route("/api/trades")
def api_trades():
    """JSON API: recent trades."""
    limit = request.args.get("limit", 50, type=int)
    return jsonify({"trades": _get_recent_trades(limit=limit)})


@app.route("/api/news")
def api_news():
    """JSON API: recent news events."""
    limit = request.args.get("limit", 25, type=int)
    return jsonify({"news": _get_news(limit=limit)})


@app.route("/api/runs")
def api_runs():
    """JSON API: pipeline runs."""
    limit = request.args.get("limit", 15, type=int)
    return jsonify({"runs": _get_runs(limit=limit)})


@app.route("/api/profits")
def api_profits():
    """JSON API: profit summary focused on P&L metrics."""
    summary = _get_summary()
    exp = _get_expectations()
    recent_wins = _q(
        "SELECT market_question, side, bet_amount, pnl, created_at FROM demo_trades "
        "WHERE result = 'win' ORDER BY id DESC LIMIT 20"
    )
    recent_losses = _q(
        "SELECT market_question, side, bet_amount, pnl, created_at FROM demo_trades "
        "WHERE result = 'loss' ORDER BY id DESC LIMIT 20"
    )
    total_invested = summary.get("bankroll", 30)
    total_pnl = summary.get("total_pnl", 0)
    roi_pct = round(total_pnl / total_invested * 100, 1) if total_invested > 0 else 0
    return jsonify({
        "total_pnl": total_pnl,
        "todays_pnl": summary.get("todays_pnl", 0),
        "accuracy_pct": summary.get("accuracy_pct", 0),
        "total_trades": summary.get("total_trades", 0),
        "total_resolved": summary.get("resolved", 0),
        "wins": summary.get("wins", 0),
        "losses": summary.get("losses", 0),
        "pending": summary.get("pending", 0),
        "roi_pct": roi_pct,
        "avg_edge": exp.get("avg_edge", 0),
        "avg_pnl": exp.get("avg_pnl", 0),
        "recent_wins": recent_wins,
        "recent_losses": recent_losses,
    })


@app.route("/api/config")
def api_config():
    """JSON API: current configuration."""
    return jsonify({
        "bankroll": round(float(_cfg("BANKROLL_USD", 30)), 2),
        "max_bet_pct": float(_cfg("MAX_BET_PCT", 0.10)),
        "strategy": _cfg("BET_STRATEGY", "edge_weighted"),
        "dry_run": _cfg_bool("DRY_RUN", True),
        "llm_provider": _cfg("LLM_PROVIDER", "mimo"),
        "consensus_enabled": _cfg_bool("CONSENSUS_ENABLED", True),
        "consensus_passes": int(_cfg("CONSENSUS_PASSES", 3)),
        "accuracy_threshold": float(_cfg("ACCURACY_THRESHOLD", 80.0)),
        "min_resolved_trades": int(_cfg("MIN_RESOLVED_TRADES", 20)),
        "scan_interval_min": int(_cfg("SCAN_INTERVAL_MIN", 5)),
        "resolve_interval_min": int(_cfg("RESOLVE_INTERVAL_MIN", 6)),
        "max_buy_price": float(_cfg("MAX_BUY_PRICE", 0.30)),
        "edge_threshold": float(_cfg("EDGE_THRESHOLD", 0.15)),
        "materiality_threshold": float(_cfg("MATERIALITY_THRESHOLD", 0.55)),
    })


@app.route("/api/logs")
def api_logs():
    """JSON API: recent log lines from the log file."""
    log_path = os.getenv("LOG_FILE", "polymarket_bot.log")
    lines = []
    try:
        if Path(log_path).exists():
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
                lines = [l.rstrip() for l in all_lines[-50:]]
    except Exception:
        pass
    return jsonify({"logs": lines})


@app.route("/live")
def live_dashboard():
    """Serve the live dashboard HTML file."""
    live_path = Path(__file__).parent / "dashboard_live.html"
    if live_path.exists():
        return live_path.read_text(encoding="utf-8")
    return "dashboard_live.html not found", 404


@app.route("/reset_db", methods=["POST", "GET"])
def reset_db():
    """Reset the database — delete all demo_trades for a fresh start."""
    try:
        if not Path(DB_PATH).exists():
            return jsonify({"status": "no_db", "message": "Database not found"}), 404
        conn = sqlite3.connect(DB_PATH)
        trades_before = conn.execute("SELECT COUNT(*) FROM demo_trades").fetchone()[0]
        conn.execute("DELETE FROM demo_trades")
        conn.commit()
        conn.close()
        return jsonify({
            "status": "ok",
            "message": f"Deleted {trades_before} demo trades. Fresh start.",
            "trades_deleted": trades_before,
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ── HTML TEMPLATE ────────────────────────────────────────────────────────────
TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Polymarket Dashboard</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    :root{--bg:#0d1117;--surface:#161b22;--border:#21262d;--fg:#e6edf3;
    --muted:#8b949e;--accent:#58a6ff;--green:#3fb950;--red:#f85149;
    --orange:#d29922;--purple:#bc8cff;--font:system-ui,-apple-system,sans-serif}
    *{margin:0;padding:0;box-sizing:border-box}
    body{font-family:var(--font);background:var(--bg);color:var(--fg);line-height:1.5;font-size:14px}
    .container{max-width:1600px;margin:0 auto;padding:16px 24px}
    .top{display:flex;justify-content:space-between;align-items:center;margin-bottom:24px}
    .top h1{font-size:20px;font-weight:600;display:flex;align-items:center;gap:8px}
    .top h1 .dot{width:10px;height:10px;border-radius:50%;background:var(--green);display:inline-block}
    .meta{color:var(--muted);font-size:12px;text-align:right}
    .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin-bottom:24px}
    .card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:16px 18px}
    .card h3{font-size:11px;text-transform:uppercase;color:var(--muted);margin-bottom:4px;letter-spacing:.05em}
    .card .v{font-size:24px;font-weight:700;font-variant-numeric:tabular-nums}
    .card .sub{font-size:11px;color:var(--muted);margin-top:2px}
    .green{color:var(--green)}.red{color:var(--red)}.orange{color:var(--orange)}.blue{color:var(--accent)}.purple{color:var(--purple)}
    .section{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:18px;margin-bottom:20px;overflow-x:auto}
    .section h2{font-size:14px;font-weight:600;margin-bottom:12px;display:flex;align-items:center;gap:8px}
    table{width:100%;border-collapse:collapse;font-size:13px}
    th{text-align:left;padding:8px 10px;border-bottom:1px solid var(--border);color:var(--muted);font-weight:500;font-size:11px;text-transform:uppercase;letter-spacing:.04em}
    td{padding:8px 10px;border-bottom:1px solid var(--border)}
    tr:last-child td{border-bottom:none}
    tr:hover td{background:rgba(88,166,255,.04)}
    .win{color:var(--green);font-weight:600}.loss{color:var(--red);font-weight:600}.pending{color:var(--orange);font-weight:600}
    .pill{display:inline-block;padding:2px 8px;border-radius:9999px;font-size:11px;font-weight:500}
    .pill.yes{background:rgba(63,185,80,.15);color:var(--green)}.pill.no{background:rgba(248,81,73,.15);color:var(--red)}
    .pill.pending{background:rgba(210,153,34,.15);color:var(--orange)}
    .pulse{animation:pulse 2s ease-in-out infinite}@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
    a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
    .bar{height:6px;background:var(--border);border-radius:3px;margin-top:4px;overflow:hidden}
    .bar .fill{height:100%;border-radius:3px;transition:width .3s}
    .chip{display:inline-block;padding:1px 6px;border-radius:4px;font-size:10px;font-weight:600;margin-right:4px;background:rgba(88,166,255,.15);color:var(--accent)}
    .chip.news{background:rgba(188,140,255,.15);color:var(--purple)}
    .chip.signal{background:rgba(63,185,80,.12);color:var(--green)}
    .flex{display:flex;gap:12px;flex-wrap:wrap}.flex .card{flex:1;min-width:200px}
    @media(max-width:900px){.grid{grid-template-columns:1fr 1fr}.flex{flex-direction:column}}
  </style>
</head>
<body>
<div class="container">
  <div class="top">
    <h1><span class="dot pulse"></span> Polymarket Dashboard</h1>
    <div class="meta">{{ now_ist }}<br>DB: {{ diag.get('db_path', 'unknown') }}</div>
  </div>

  <!-- KPI Cards -->
  <div class="grid">
    <div class="card">
      <h3>Accuracy</h3>
      <div class="v {{ 'green' if summary.accuracy_pct >= 60 else 'orange' if summary.accuracy_pct >= 50 else 'red' }}">{{ summary.accuracy_pct }}%</div>
      <div class="sub">{{ summary.wins }}W / {{ summary.losses }}L ({{ summary.resolved }} resolved)</div>
    </div>
    <div class="card">
      <h3>Total PnL</h3>
      <div class="v {{ 'green' if summary.total_pnl >= 0 else 'red' }}">${{ "%.2f"|format(summary.total_pnl) }}</div>
      <div class="sub">Today: ${{ "%.2f"|format(summary.todays_pnl) }}</div>
    </div>
    <div class="card">
      <h3>Trades</h3>
      <div class="v">{{ summary.total_trades }}</div>
      <div class="sub">{{ summary.pending }} pending · {{ summary.resolved }} resolved</div>
    </div>
    <div class="card">
      <h3>Go-Live</h3>
      <div class="v {{ 'green' if summary.can_go_live else 'orange' }}">{{ "✅ READY" if summary.can_go_live else "🔒 " ~ summary.go_live_remaining ~ " more needed" }}</div>
      <div class="sub">Need {{ "%.0f"|format(summary.accuracy_pct) }}% accuracy ({{ "%.1f"|format(summary.accuracy_pct) }}% current)</div>
    </div>
    <div class="card">
      <h3>Bankroll</h3>
      <div class="v">${{ "%.2f"|format(bankroll) }}</div>
      <div class="sub">Max bet: ${{ "%.2f"|format(max_usd) }} ({{ "%.0f"|format(max_bet_pct*100) }}%)</div>
    </div>
    <div class="card">
      <h3>Avg Edge</h3>
      <div class="v blue">{{ "%.2f"|format(exp.avg_edge) }}</div>
      <div class="sub">Avg PnL/trade: ${{ "%.2f"|format(exp.avg_pnl) }}</div>
    </div>
  </div>

  <!-- Trade Log -->
  <div class="section">
    <h2>📋 Trade Log ({{ trades|length }} most recent)</h2>
    <table>
      <thead>
        <tr>
          <th>#</th><th>Market</th><th>Side</th><th>Entry</th>
          <th>Edge</th><th>Confidence</th><th>Bet $</th><th>Result</th>
          <th>PnL</th><th>Expected Profit</th><th>Strategy</th><th>Duration</th>
        </tr>
      </thead>
      <tbody>
        {% for t in trades %}
        <tr>
          <td>{{ t.id }}</td>
          <td><a href="https://polymarket.com/event/{{ t.market_slug }}" target="_blank" title="{{ t.market_question }}">{{ t.market_question[:50] }}{% if t.market_question|length > 50 %}…{% endif %}</a></td>
          <td><span class="pill {{ 'yes' if t.side == 'YES' else 'no' }}">{{ t.side }}</span></td>
          <td>{{ "%.3f"|format(t.entry_price) if t.entry_price else '—' }}</td>
          <td class="{{ 'green' if (t.edge or 0) > 0 else 'red' }}">{{ "%.3f"|format(t.edge) if t.edge else '—' }}</td>
          <td>{{ "%.2f"|format(t.confidence) if t.confidence else '—' }}</td>
          <td>${{ "%.2f"|format(t.bet_amount) if t.bet_amount else '—' }}</td>
          <td>
            {% if t.result == 'win' %}
              <span class="win" style="font-weight: 700;">WIN</span>
            {% elif t.result == 'loss' %}
              <span class="loss" style="font-weight: 700;">LOSS</span>
            {% elif t.result == 'void' %}
              <span style="color: var(--muted); font-weight: 700;">VOID</span>
            {% else %}
              <span class="pending pulse">⏳ PENDING</span>
            {% endif %}
          </td>
          <td>
            {% if t.pnl is not none and t.result and t.result != 'pending' %}
              <span class="{{ 'green' if t.pnl >= 0 else 'red' }}">${{ "%.2f"|format(t.pnl) }}</span>
            {% else %}
              <span style="color:var(--muted)">—</span>
            {% endif %}
          </td>
          <td>
            {% if t.expected_profit is defined and t.expected_profit %}
              <span class="{{ 'green' if t.expected_profit >= 0 else 'red' }}">${{ "%.2f"|format(t.expected_profit) }}</span>
            {% else %}
              <span style="color:var(--muted)">—</span>
            {% endif %}
          </td>
          <td>{{ t.strategy or '—' }}</td>
          <td>{{ t.resolution_duration or t.time_to_resolve or '—' }}</td>
        </tr>
        {% endfor %}
        {% if not trades %}
        <tr><td colspan="12" style="text-align:center;color:var(--muted);padding:24px">No trades yet — the demo runner will start placing trades soon.</td></tr>
        {% endif %}
      </tbody>
    </table>
  </div>

  <!-- Diagnostics -->
  <div class="section">
    <h2>🔧 Database Diagnostics</h2>
    <table>
      <thead><tr><th>Table</th><th>Row Count</th></tr></thead>
      <tbody>
        {% for table, count in diag.items() %}
          {% if table not in ('error', 'db_path') %}
          <tr><td>{{ table }}</td><td>{{ count }}</td></tr>
          {% endif %}
        {% endfor %}
        {% if diag.get('error') %}
        <tr><td style="color:var(--red)" colspan="2">{{ diag.error }}</td></tr>
        {% endif %}
      </tbody>
    </table>
    <div style="margin-top:12px">
      <a href="/reset_db" onclick="return confirm('Reset all trades? This cannot be undone.')"
         style="font-size:12px;color:var(--red)">🗑 Reset DB</a>
    </div>
  </div>

  <!-- Config -->
  <div class="section">
    <h2>⚙️ Configuration</h2>
    <table>
      <thead><tr><th>Setting</th><th>Value</th></tr></thead>
      <tbody>
        <tr><td>Bankroll</td><td>${{ "%.2f"|format(bankroll) }}</td></tr>
        <tr><td>Max Bet %</td><td>{{ "%.0f"|format(max_bet_pct*100) }}%</td></tr>
        <tr><td>Strategy</td><td>{{ strategy }}</td></tr>
        <tr><td>ML Scoring</td><td>{{ "ON" if ml_enabled else "OFF" }}</td></tr>
        <tr><td>Adaptive Thresholds</td><td>{{ "ON" if adaptive else "OFF" }}</td></tr>
        <tr><td>Risk Engine</td><td>{{ "ON" if risk_on else "OFF" }}</td></tr>
        <tr><td>Referral Rake</td><td>{{ rake_pct }}% (cap ${{ rake_cap }})</td></tr>
      </tbody>
    </table>
  </div>

</div>
</body>
</html>"""

# ── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host=CLI_ARGS.bind, port=CLI_ARGS.port, debug=False)