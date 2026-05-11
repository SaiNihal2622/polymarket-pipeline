#!/usr/bin/env python3
"""
web_dashboard.py — Live web UI for the Polymarket pipeline.

Run locally:  python web_dashboard.py    (then open http://localhost:8080)
Run on Railway: deployed as separate service or alongside, port from $PORT env.

Shows: bankroll, accuracy, strategy leaderboard, signal accuracy, recent trades,
       pending trades, news events, and resolution status.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, render_template_string

try:
    import config
except Exception:
    config = None

# Dashboard reads from bot.db (demo_trades table) — the same DB the demo_runner writes to.
_db_env = os.getenv("DB_PATH", "")
if _db_env:
    DB_PATH = Path(_db_env).absolute()
else:
    _railway_volume = Path("/data")
    if _railway_volume.exists():
        DB_PATH = (_railway_volume / "bot.db").absolute()
    else:
        DB_PATH = (Path(__file__).parent / "bot.db").absolute()
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

try:
    from resolver import (
        get_accuracy_stats,
        get_signal_accuracies,
        get_strategy_accuracies,
    )
except Exception:
    def get_accuracy_stats(): return {"accuracy_pct": 0, "wins": 0, "losses": 0}
    def get_signal_accuracies(): return {}
    def get_strategy_accuracies(): return []

try:
    from bankroll import get_current_bankroll, todays_pnl, can_trade_today
except Exception:
    def get_current_bankroll(): return 0.0
    def todays_pnl(): return 0.0
    def can_trade_today(): return (True, "ok")

app = Flask(__name__)


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def _q(sql: str, args: tuple = ()) -> list[dict]:
    conn = _conn()
    rows = conn.execute(sql, args).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _get_summary() -> dict:
    """Summary stats from demo_trades table in bot.db."""
    try:
        total_trades = _q("SELECT COUNT(*) as c FROM demo_trades")[0]["c"]
    except Exception:
        total_trades = 0
    try:
        total_resolved = _q("SELECT COUNT(*) as c FROM demo_trades WHERE result IS NOT NULL AND result != ''")[0]["c"]
    except Exception:
        total_resolved = 0
    try:
        pending = _q("SELECT COUNT(*) as c FROM demo_trades WHERE result IS NULL OR result = ''")[0]["c"]
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
    total_pnl = 0.0
    accuracy_pct = 0.0
    if total_resolved > 0:
        accuracy_pct = round(wins / total_resolved * 100, 1)
        # PnL: win = +edge*amount, loss = -amount
        try:
            win_pnl = _q("SELECT COALESCE(SUM(edge * amount_usd), 0) as p FROM demo_trades WHERE result = 'win'")[0]["p"]
            loss_pnl = _q("SELECT COALESCE(SUM(-amount_usd), 0) as p FROM demo_trades WHERE result = 'loss'")[0]["p"]
            total_pnl = round((win_pnl or 0) + (loss_pnl or 0), 2)
        except Exception:
            total_pnl = 0.0

    min_resolved = int(_cfg("MIN_RESOLVED_TRADES", 20))
    acc_threshold = float(_cfg("ACCURACY_THRESHOLD", 80.0))
    can_go = total_resolved >= min_resolved and accuracy_pct >= acc_threshold

    return {
        "bankroll": round(float(_cfg("BANKROLL_USD", 30)), 2),
        "todays_pnl": 0.0,  # computed from demo_trades if needed
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
            """SELECT id, created_at, market_question, side,
                      market_price, claude_score, edge, amount_usd,
                      status, strategy, signals, classification,
                      materiality, news_source, end_date_iso,
                      result, resolved_at
               FROM demo_trades
               ORDER BY id DESC LIMIT ?""",
            (limit,),
        )
    except Exception:
        return []
    now = datetime.utcnow()
    for r in rows:
        if r.get("signals"):
            try:
                r["signals_parsed"] = json.loads(r["signals"])
            except Exception:
                r["signals_parsed"] = {}
        else:
            r["signals_parsed"] = {}
        # Compute time-to-resolve
        r["time_to_resolve"] = ""
        if r.get("resolved_at") and r.get("created_at"):
            try:
                created = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
                resolved = datetime.fromisoformat(r["resolved_at"].replace("Z", "+00:00"))
                # Strip tzinfo from both to avoid naive/aware mismatch
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

        # --- Resolution Duration (time from trade creation to resolution/close) ---
        # For resolved: end_date_iso or resolved_at - created_at
        # For pending: now - created_at (time open so far)
        r["resolution_duration"] = ""
        end_iso = r.get("end_date_iso")
        resolved_at = r.get("resolved_at")
        created_at = r.get("created_at")
        duration_source = end_iso or resolved_at  # use whichever is available
        if created_at:
            try:
                create_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                create_dt = create_dt.replace(tzinfo=None)
                if duration_source:
                    close_dt = datetime.fromisoformat(duration_source.replace("Z", "+00:00"))
                    close_dt = close_dt.replace(tzinfo=None)
                else:
                    # Pending trade: use current time
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
        elif r.get("result") and r.get("time_to_resolve"):
            r["resolution_duration"] = r["time_to_resolve"]

        # --- Expected Profit (EV calculation) ---
        # EV = true_prob * potential_profit - (1 - true_prob) * loss
        # For YES: profit_per_dollar = (1/price - 1), loss = $1
        # For NO:  profit_per_dollar = (1/(1-price) - 1), loss = $1
        r["expected_profit"] = 0.0
        price = r.get("market_price", 0.5)
        score = r.get("claude_score", 0.5)
        # Clamp score to [0, 1] — unbounded materiality can exceed 1.0
        if score is not None:
            score = max(0.0, min(1.0, float(score)))
        amount = r.get("amount_usd", 1.0)
        side = r.get("side", "YES")
        edge = r.get("edge", 0.0) or 0.0
        # Clamp edge to sane range
        edge = max(-1.0, min(1.0, float(edge)))
        if amount:
            try:
                # If price is resolved (0 or 1), reconstruct from edge
                # edge = claude_score - market_price_at_entry
                # So entry_price = claude_score - edge
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
                    # Fallback: simple EV from edge
                    r["expected_profit"] = round(edge * amount, 2)
            except Exception:
                r["expected_profit"] = 0.0
    return rows


def _get_news(limit: int = 25) -> list[dict]:
    return _q(
        "SELECT headline, source, received_at, latency_ms, matched_markets, "
        "triggered_trades FROM news_events ORDER BY id DESC LIMIT ?",
        (limit,),
    )


def _get_runs(limit: int = 15) -> list[dict]:
    return _q(
        "SELECT id, started_at, finished_at, markets_scanned, signals_found, "
        "trades_placed, status FROM pipeline_runs ORDER BY id DESC LIMIT ?",
        (limit,),
    )


def _cfg(name: str, default):
    """Read config/env values safely so the dashboard never fails to boot.
    
    IMPORTANT: Always check env vars FIRST (same as demo_runner.py) before
    falling back to config.py module defaults. config.py may have stale
    defaults that don't match the runtime values demo_runner actually uses.
    """
    env_val = os.getenv(name)
    if env_val is not None:
        return env_val
    if config and hasattr(config, name):
        return getattr(config, name)
    return default


def _cfg_bool(name: str, default: bool) -> bool:
    """Parse boolean config value correctly. bool('false') == True in Python,
    so we need explicit string parsing."""
    val = _cfg(name, default)
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("true", "1", "yes", "on")
    return bool(val)


def _cfg_list(name: str, default: list) -> list:
    """Parse list config value. Handles both Python lists and comma-separated strings."""
    val = _cfg(name, default)
    if isinstance(val, (list, tuple)):
        return list(val)
    if isinstance(val, str):
        # Comma-separated string from env var
        return [x.strip() for x in val.split(",") if x.strip()]
    return default


def _get_engine_config() -> dict:
    max_yes = float(_cfg("MAX_YES_ENTRY_PRICE", 0.30))
    min_no_yes = float(_cfg("MIN_NO_ENTRY_PRICE", 0.50))
    # Defaults below must match config.py values exactly
    # Mode is dynamic: DRY_RUN=true → DRY-RUN, else LIVE
    _dry_run = _cfg_bool("DRY_RUN", True)
    return {
        "mode": "DRY-RUN" if _dry_run else "LIVE",
        "bankroll_usd": float(_cfg("BANKROLL_USD", 30)),
        "max_bet_usd": float(_cfg("MAX_BET_USD", 1)),
        "daily_loss_limit_usd": float(_cfg("DAILY_LOSS_LIMIT_USD", 10)),
        "edge_threshold": float(_cfg("EDGE_THRESHOLD", 0.15)),
        "accuracy_threshold": float(_cfg("ACCURACY_THRESHOLD", 80.0)),
        "min_resolved_trades": int(_cfg("MIN_RESOLVED_TRADES", 20)),
        "max_yes_entry_price": max_yes,
        "min_no_entry_yes_price": min_no_yes,
        "max_no_entry_price": round(1.0 - min_no_yes, 4),
        "materiality_threshold": float(_cfg("MATERIALITY_THRESHOLD", 0.55)),
        "consensus_enabled": _cfg_bool("CONSENSUS_ENABLED", True),
        "consensus_passes": int(_cfg("CONSENSUS_PASSES", 3)),
        "strict_consensus": _cfg_bool("STRICT_CONSENSUS", True),
        "demo_hours_window": float(_cfg("DEMO_HOURS_WINDOW", 30)),
        "scan_interval_min": int(_cfg("SCAN_INTERVAL_MIN", 5)),
        "resolve_interval_min": int(_cfg("RESOLVE_INTERVAL_MIN", 6)),
        "min_close_hours": float(_cfg("MIN_CLOSE_HOURS", 0.50)),
        "min_volume_usd": float(_cfg("MIN_VOLUME_USD", 50)),
        "min_window_hours": float(_cfg("MIN_WINDOW_HOURS", 0.25)),
        "market_categories": _cfg_list("MARKET_CATEGORIES", [
            "ai", "technology", "crypto", "politics", "science", "finance", "world", "other"
        ]),
        "llm_provider": _cfg("LLM_PROVIDER", "mimo"),
        "mimo_model": _cfg("MIMO_MODEL", "mimo-v2.5-pro"),
    }




def _get_expectations() -> dict:
    cfg = _get_engine_config()
    # Dynamic predictions based on current state from demo_trades
    try:
        total_resolved = _q(
            "SELECT COUNT(*) as c FROM demo_trades WHERE result IS NOT NULL AND result != ''"
        )[0]["c"]
    except Exception:
        total_resolved = 0

    try:
        total_trades = _q("SELECT COUNT(*) as c FROM demo_trades")[0]["c"]
    except Exception:
        total_trades = 0

    try:
        pending = _q(
            "SELECT COUNT(*) as c FROM demo_trades WHERE result IS NULL OR result = ''"
        )[0]["c"]
    except Exception:
        pending = 0

    try:
        recent_24h = _q(
            "SELECT COUNT(*) as c FROM demo_trades WHERE created_at >= datetime('now', '-24 hours')"
        )[0]["c"]
    except Exception:
        recent_24h = 0

    current_acc = 0
    wins = 0
    losses = 0
    if total_resolved > 0:
        try:
            wins = _q("SELECT COUNT(*) as c FROM demo_trades WHERE result = 'win'")[0]["c"]
            losses = _q("SELECT COUNT(*) as c FROM demo_trades WHERE result = 'loss'")[0]["c"]
            current_acc = round(wins / total_resolved * 100, 1)
        except Exception:
            pass

    max_bet = cfg.get("max_bet_usd", 1.0)
    bankroll = cfg.get("bankroll_usd", 30)

    # Estimate trades in next 24h based on scan rate (every 5min = 288 scans/day)
    # ~20 candidates/scan, 6 pass hard filters, ~0.5-1 trade per 6 candidates
    # Realistic: 0-3 trades/day given strict consensus gates
    est_trades_low = 0
    est_trades_high = 3
    if recent_24h > 0:
        est_trades_high = max(est_trades_high, recent_24h + 2)

    # Expected profit: if trades fire, each is $1 bet, EV depends on edge
    # Typical edge: 15-25%, so EV per trade ≈ $0.15-$0.25
    # But accuracy gate means we need to prove ourselves first
    est_profit_low = round(est_trades_low * max_bet * 0.15, 2)
    est_profit_high = round(est_trades_high * max_bet * 0.25, 2)

    # Accuracy projection: based on current trajectory
    accuracy_projection = ""
    if total_resolved >= 5:
        if current_acc >= 80:
            accuracy_projection = f"On track: {current_acc:.0f}% (above {cfg['accuracy_threshold']:.0f}% target)"
        elif current_acc >= 60:
            accuracy_projection = f"Building: {current_acc:.0f}% → need {cfg['accuracy_threshold']:.0f}% over {cfg['min_resolved_trades']} trades"
        else:
            accuracy_projection = f"Early: {current_acc:.0f}% (small sample, will stabilize)"
    else:
        accuracy_projection = f"Insufficient data ({total_resolved} resolved). Need {cfg['min_resolved_trades']}+ to project."

    return {
        "next_24h_trades": f"{est_trades_low}-{est_trades_high}",
        "next_24h_trades_range": f"{est_trades_low}-{est_trades_high} trades expected (strict consensus gate, ~6 candidates/cycle)",
        "next_24h_resolved_range": f"0-{max(0, pending)} pending trades may resolve if markets close",
        "next_24h_profit_range": f"${est_profit_low:.2f} to +${est_profit_high:.2f} (demo bets)" if cfg.get("mode") != "LIVE" else f"${est_profit_low:.2f} to +${est_profit_high:.2f}",
        "accuracy_target": f"{cfg['accuracy_threshold']:.0f}% after {cfg['min_resolved_trades']}+ resolved trades",
        "accuracy_projection": accuracy_projection,
        "current_accuracy": f"{current_acc:.1f}%" if total_resolved > 0 else "N/A (no resolved trades)",
        "expected_real_profit": "$0.00 — DRY-RUN mode, no real money at risk" if cfg.get("mode") != "LIVE" else f"${est_profit_low:.2f} to +${est_profit_high:.2f}",
        "demo_pnl_range": f"${est_profit_low * 1 - est_trades_high * max_bet:.2f} to +${est_profit_high:.2f} with ${max_bet:.0f} flat demo bets",
        "trial_progress": f"{total_resolved}/{cfg['min_resolved_trades']} resolved trades ({max(0, cfg['min_resolved_trades'] - total_resolved)} remaining)",
        "old_10pct_risk": "Much lower than before. Selective consensus gates reject low-confidence signals.",
        "why_30_50_blocked": "31-49¢ YES prices are coin-flip territory. System favors asymmetric edges only.",
        "recent_24h_activity": f"{recent_24h} trades placed in last 24h",
    }


def _get_diagnostics() -> dict:
    db_exists = Path(DB_PATH).exists()
    tables = []
    counts = {}
    if db_exists:
        try:
            conn = _conn()
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
            for table in tables:
                try:
                    counts[table] = conn.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
                except Exception:
                    pass
            conn.close()
        except Exception as e:
            counts["error"] = str(e)
    return {
        "dashboard_status": "ok",
        "db_path": str(DB_PATH),
        "db_exists": db_exists,
        "tables": tables,
        "counts": counts,
        "available_api_endpoints": [
            "/api/summary", "/api/trades", "/api/news", "/api/runs",
            "/api/config", "/api/expectations", "/api/diagnostics", "/api/logs", "/healthz"
        ],
    }


def _get_logs(limit: int = 120) -> list[str]:
    candidates = [Path("/data/polymarket_bot.log"), Path("polymarket_bot.log"), Path("scan_log.txt")]
    for p in candidates:
        if p.exists():
            try:
                return p.read_text(errors="replace").splitlines()[-limit:]
            except Exception as e:
                return [f"Could not read {p}: {e}"]
    return ["No local log file found. Use Railway runtime logs for process stdout/stderr."]
HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Polymarket Vibe Pipeline</title>
<meta http-equiv="refresh" content="20">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #05070a;
    --panel: rgba(17, 24, 39, 0.7);
    --border: rgba(255, 255, 255, 0.08);
    --text: #f3f4f6;
    --muted: #9ca3af;
    --accent: #10b981;
    --win: #10b981;
    --loss: #ef4444;
    --warn: #f59e0b;
    --cyan: #0ea5e9;
    --glass: rgba(255, 255, 255, 0.03);
  }
  * { box-sizing: border-box; }
  body {
    font-family: 'Inter', sans-serif;
    background: var(--bg);
    background-image: 
        radial-gradient(at 0% 0%, rgba(16, 185, 129, 0.05) 0px, transparent 50%),
        radial-gradient(at 100% 0%, rgba(14, 165, 233, 0.05) 0px, transparent 50%);
    color: var(--text);
    margin: 0;
    padding: 24px;
    min-height: 100vh;
  }
  .container { max-width: 1400px; margin: 0 auto; }
  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 32px;
  }
  h1 { 
    margin: 0; 
    font-size: 24px; 
    font-weight: 700;
    letter-spacing: -0.025em;
    background: linear-gradient(135deg, #fff 0%, #9ca3af 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }
  .refresh-tag {
    font-size: 12px;
    color: var(--muted);
    background: var(--glass);
    padding: 4px 12px;
    border-radius: 100px;
    border: 1px solid var(--border);
  }
  .grid { display: grid; gap: 20px; }
  .grid-3 { grid-template-columns: repeat(3, 1fr); }
  .grid-2 { grid-template-columns: 1fr 1fr; }
  
  .panel {
    background: var(--panel);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 24px;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
    transition: transform 0.2s ease, border-color 0.2s ease;
  }
  .panel:hover {
    border-color: rgba(255, 255, 255, 0.15);
  }
  
  h2 {
    margin: 0 0 20px 0;
    font-size: 14px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
    display: flex;
    align-items: center;
    gap: 8px;
  }
  
  .stat-card {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .stat-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 0;
    border-bottom: 1px solid var(--border);
  }
  .stat-row:last-child { border-bottom: 0; }
  .stat-label { color: var(--muted); font-size: 14px; }
  .stat-value { font-weight: 600; font-size: 16px; }
  .stat-value.large { font-size: 24px; }
  
  .win { color: var(--win); }
  .loss { color: var(--loss); }
  .warn { color: var(--warn); }
  
  table { width: 100%; border-collapse: collapse; margin-top: 10px; }
  th {
    text-align: left;
    padding: 12px 8px;
    font-size: 12px;
    font-weight: 500;
    color: var(--muted);
    border-bottom: 1px solid var(--border);
  }
  td {
    padding: 16px 8px;
    font-size: 13px;
    border-bottom: 1px solid var(--border);
    vertical-align: middle;
  }
  tr:last-child td { border-bottom: 0; }
  tr:hover { background: rgba(255, 255, 255, 0.02); }
  
  .pill {
    display: inline-flex;
    align-items: center;
    padding: 4px 10px;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.025em;
  }
  .pill-yes { background: rgba(16, 185, 129, 0.1); color: #34d399; }
  .pill-no { background: rgba(239, 68, 68, 0.1); color: #f87171; }
  .pill-pending { background: rgba(245, 158, 11, 0.1); color: #fbbf24; }
  .pill-blocked { background: rgba(239, 68, 68, 0.12); color: #fca5a5; }
  .pill-ok { background: rgba(16, 185, 129, 0.12); color: #86efac; }
  .mono { font-family: 'JetBrains Mono', monospace; }
  .small { font-size: 12px; color: var(--muted); line-height: 1.5; }
  .api-link { color: #7dd3fc; text-decoration: none; font-family: 'JetBrains Mono', monospace; font-size: 12px; }
  .api-link:hover { text-decoration: underline; }
  .rule-list { margin: 0; padding-left: 18px; color: var(--text); font-size: 13px; line-height: 1.7; }
  .log-box { max-height: 260px; overflow: auto; background: rgba(0,0,0,0.28); border: 1px solid var(--border); border-radius: 10px; padding: 12px; }
  .log-line { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #cbd5e1; white-space: pre-wrap; border-bottom: 1px solid rgba(255,255,255,0.04); padding: 3px 0; }
  
  .strategy-item {
    margin-bottom: 16px;
  }
  .strategy-header {
    display: flex;
    justify-content: space-between;
    margin-bottom: 8px;
    font-size: 14px;
  }
  .progress-bg {
    width: 100%;
    height: 6px;
    background: var(--border);
    border-radius: 100px;
    overflow: hidden;
  }
  .progress-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--cyan), var(--accent));
    border-radius: 100px;
  }
  
  .signal-badge {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    background: var(--glass);
    border: 1px solid var(--border);
    padding: 2px 6px;
    border-radius: 4px;
    margin-right: 4px;
    color: var(--muted);
  }
  
  .question-cell {
    max-width: 300px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-weight: 500;
  }
  
  .accuracy-circle {
    width: 60px;
    height: 60px;
    border-radius: 50%;
    border: 4px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    position: relative;
  }
  
  .footer {
    margin-top: 48px;
    text-align: center;
    color: var(--muted);
    font-size: 12px;
  }
  
  ::-webkit-scrollbar { width: 8px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 10px; }
  ::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.2); }

  @media (max-width: 1024px) {
    .grid-3 { grid-template-columns: 1fr; }
    .grid-2 { grid-template-columns: 1fr; }
  }
</style>
</head>
<body>

<div class="container">
  <header>
    <h1>Polymarket Accuracy Pipeline <span style="color:var(--muted); font-weight: 300;">v3.1</span></h1>
    <div class="refresh-tag">
      Live • Updates every 20s • {{ now }}
    </div>
  </header>

  <!-- SUMMARY CARDS -->
  <div class="grid grid-3" style="margin-bottom: 32px;">
    
    <div class="panel">
      <h2><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="5" width="20" height="14" rx="2" ry="2"/><line x1="2" y1="10" x2="22" y2="10"/></svg> Performance</h2>
      <div class="stat-card">
        <div class="stat-row">
          <span class="stat-label">Current Bankroll</span>
          <span class="stat-value large accent">${{ s.bankroll }}</span>
        </div>
        <div class="stat-row">
          <span class="stat-label">Today's PnL</span>
          <span class="stat-value {{ 'win' if s.todays_pnl >= 0 else 'loss' }}">${{ s.todays_pnl }}</span>
        </div>
        <div class="stat-row">
          <span class="stat-label">Total Net Profit</span>
          <span class="stat-value {{ 'win' if s.total_pnl >= 0 else 'loss' }}">${{ s.total_pnl }}</span>
        </div>
      </div>
    </div>

    <div class="panel">
      <h2><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20v-6M6 20V10M18 20V4"/></svg> Accuracy Metrics</h2>
      <div class="stat-card">
        <div class="stat-row">
          <span class="stat-label">Win Rate</span>
          <div style="display: flex; align-items: center; gap: 12px;">
            <span class="stat-value large {{ 'win' if s.accuracy_pct >= 75 else ('warn' if s.accuracy_pct >= 60 else 'loss') }}">
              {{ s.accuracy_pct }}%
            </span>
          </div>
        </div>
        <div class="stat-row">
          <span class="stat-label">Wins / Losses</span>
          <span class="stat-value"><span class="win">{{ s.wins }}W</span> / <span class="loss">{{ s.losses }}L</span></span>
        </div>
        <div class="stat-row">
          <span class="stat-label">Resolved / Pending</span>
          <span class="stat-value">{{ s.resolved }} / <span class="warn">{{ s.pending }}</span></span>
        </div>
      </div>
    </div>

    <div class="panel">
      <h2><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg> Readiness</h2>
      <div class="stat-card">
        <div class="stat-row">
          <span class="stat-label">System Mode</span>
          <span class="stat-value {{ 'win' if cfg.mode == 'LIVE' and s.accuracy_pct >= 80 and s.resolved >= cfg.min_resolved_trades else 'warn' }}">
            {{ cfg.mode if cfg.mode == 'LIVE' else 'DRY-RUN / TRIAL' }}
          </span>
        </div>
        <div class="stat-row">
          <span class="stat-label">Trial Progress</span>
          <span class="stat-value">{{ s.resolved }} / {{ cfg.min_resolved_trades }}</span>
        </div>
        <div class="progress-bg"><div class="progress-fill" style="width: {{ (s.resolved / cfg.min_resolved_trades * 100) if cfg.min_resolved_trades > 0 else 0 }}%"></div></div>
        <div class="stat-row" style="margin-top: 4px; border-bottom:0;">
          <span class="stat-label">Go-Live Gate</span>
          <span class="stat-value {{ 'win' if s.can_go_live else ('warn' if s.trades_today_allowed else 'loss') }}">
             {{ 'OPEN' if s.can_go_live else ('ACCUMULATING' if s.trades_today_allowed else 'BLOCKED') }}
          </span>
        </div>
        {% if not s.can_go_live %}
        <div class="small" style="margin-top:4px;">
          Need: {{ s.accuracy_pct }}% → {{ cfg.accuracy_threshold }}% accuracy,
          {{ s.resolved }}/{{ cfg.min_resolved_trades }} resolved
        </div>
        {% endif %}
      </div>
    </div>
  </div>

  <!-- ENGINE TRANSPARENCY -->
  <div class="grid grid-2" style="margin-bottom: 32px;">
    <div class="panel">
      <h2>🧠 Trade Engine Rules</h2>
      <ul class="rule-list">
        <li><strong>Mode:</strong> <span class="warn">{{ cfg.mode }}</span></li>
        <li><strong>LLM:</strong> <span class="mono">{{ cfg.llm_provider }} / {{ cfg.mimo_model }}</span></li>
        <li><strong>YES entry:</strong> only when YES price ≤ <span class="mono">{{ "%.0f"|format(cfg.max_yes_entry_price * 100) }}¢</span></li>
        <li><strong>NO entry:</strong> only when YES price ≥ <span class="mono">{{ "%.0f"|format(cfg.min_no_entry_yes_price * 100) }}¢</span> (NO price ≤ <span class="mono">{{ "%.0f"|format(cfg.max_no_entry_price * 100) }}¢</span>)</li>
        <li><strong>Middle zone:</strong> 31¢–49¢ YES is intentionally blocked to avoid coin-flip trades.</li>
        <li><strong>Edge gate:</strong> model edge must be ≥ <span class="mono">{{ "%.0f"|format(cfg.edge_threshold * 100) }}%</span></li>
        <li><strong>Consensus:</strong> {{ cfg.consensus_passes }} passes, strict={{ cfg.strict_consensus }}, enabled={{ cfg.consensus_enabled }}</li>
        <li><strong>Materiality:</strong> news must score ≥ <span class="mono">{{ "%.0f"|format(cfg.materiality_threshold * 100) }}%</span></li>
        <li><strong>Risk:</strong> max bet ${{ cfg.max_bet_usd }} • daily loss limit ${{ cfg.daily_loss_limit_usd }}</li>
        <li><strong>Categories:</strong> <span class="mono" style="font-size: 11px;">{{ cfg.market_categories|join(', ') }}</span></li>
        <li><strong>Scan interval:</strong> {{ cfg.scan_interval_min }}min • Resolve check: {{ cfg.resolve_interval_min }}min • Window: {{ cfg.demo_hours_window }}h</li>
      </ul>
    </div>

    <div class="panel">
      <h2>📈 Next 24h Expectations</h2>
      <div class="stat-card">
        <div class="stat-row"><span class="stat-label">Expected Trades</span><span class="stat-value">{{ exp.next_24h_trades_range }}</span></div>
        <div class="stat-row"><span class="stat-label">Expected Resolved</span><span class="stat-value">{{ exp.next_24h_resolved_range }}</span></div>
        <div class="stat-row"><span class="stat-label">Expected Profit</span><span class="stat-value">{{ exp.next_24h_profit_range }}</span></div>
        <div class="stat-row"><span class="stat-label">Current Accuracy</span><span class="stat-value {{ 'win' if 'N/A' not in exp.current_accuracy and '%' in exp.current_accuracy and exp.current_accuracy.replace('%','').replace('.','').replace('N/A','').strip().isdigit() and exp.current_accuracy.replace('%','').replace('.','').replace('N/A','').strip()|int >= 75 else 'warn' }}">{{ exp.current_accuracy }}</span></div>
        <div class="stat-row"><span class="stat-label">Accuracy Projection</span><span class="stat-value small">{{ exp.accuracy_projection }}</span></div>
        <div class="stat-row"><span class="stat-label">Accuracy Target</span><span class="stat-value win">{{ exp.accuracy_target }}</span></div>
        <div class="stat-row"><span class="stat-label">Trial Progress</span><span class="stat-value">{{ exp.trial_progress }}</span></div>
        <div class="stat-row"><span class="stat-label">Real Profit</span><span class="stat-value warn">{{ exp.expected_real_profit }}</span></div>
        <div class="stat-row"><span class="stat-label">Recent Activity</span><span class="stat-value">{{ exp.recent_24h_activity }}</span></div>
        <div class="small" style="margin-top:10px;">Risk: {{ exp.old_10pct_risk }}</div>
      </div>
    </div>
  </div>

  <!-- STRATEGIES & SIGNALS -->
  <div class="grid grid-2" style="margin-bottom: 32px;">
    <div class="panel">
      <h2>🏆 Strategy Leaderboard</h2>
      {% if not strategies %}
        <div class="small" style="padding: 20px 0; text-align: center; color: var(--muted);">No strategy data yet. Strategies appear after trades are resolved.</div>
      {% endif %}
      {% for st in strategies %}
        {% set acc = (st.wins / (st.wins + st.losses) * 100) if (st.wins + st.losses) > 0 else 0 %}
        <div class="strategy-item">
          <div class="strategy-header">
            <span style="font-weight: 500;">{{ st.strategy }}</span>
            <span><span class="{{ 'win' if acc >= 75 else 'warn' }}">{{ acc|round(1) }}%</span> <span class="muted">acc</span></span>
          </div>
          <div class="progress-bg"><div class="progress-fill" style="width: {{ acc }}%"></div></div>
          <div style="font-size: 11px; color: var(--muted); margin-top: 4px;">
            {{ st.wins }}W - {{ st.losses }}L • {{ st.trades }} trades • ${{ st.pnl }} PnL
          </div>
        </div>
      {% endfor %}
    </div>

    <div class="panel">
      <h2>📡 Signal Intelligence</h2>
      {% if not signals %}
        <div class="small" style="padding: 20px 0; text-align: center; color: var(--muted);">No signal data yet. Signals are tracked after resolved trades.</div>
      {% endif %}
      <table>
        <thead>
          <tr><th>Signal</th><th>Acc</th><th>Decisive</th><th>Weight</th></tr>
        </thead>
        <tbody>
          {% for sig, d in signals.items() %}
          <tr>
            <td><strong>{{ d.label }}</strong></td>
            <td class="{{ 'win' if d.accuracy_pct >= 75 else 'warn' }}">{{ d.accuracy_pct }}%</td>
            <td>{{ d.trades }}</td>
            <td>
              <div class="progress-bg" style="width: 60px;"><div class="progress-fill" style="width: {{ (d.accuracy_pct or 0) }}%"></div></div>
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>

  <!-- RECENT TRADES -->
  <div class="panel" style="margin-bottom: 32px;">
    <h2>💼 Active & Recent Trades</h2>
    <div style="overflow-x: auto;">
      <table>
        <thead>
          <tr>
            <th>Time</th><th>Market Question</th><th>Side</th><th>Edge</th><th>Amount</th><th>Status</th><th>Exp. Profit</th><th>Res. Duration</th><th>Result</th><th>TTR</th>
          </tr>
        </thead>
        <tbody>
          {% for t in trades %}
          <tr>
            <td class="muted">{{ t.created_at[11:16] }}</td>
            <td class="question-cell" title="{{ t.market_question }}">{{ t.market_question }}</td>
            <td><span class="pill {{ 'pill-yes' if t.side == 'YES' else 'pill-no' }}">{{ t.side }}</span></td>
            <td class="{{ 'win' if t.edge > 0 else 'loss' }}">{{ "%+.1f"|format(t.edge * 100) }}%</td>
            <td>${{ "%.2f"|format(t.amount_usd) }}</td>
            <td><span class="signal-badge">{{ t.status }}</span></td>
            <td style="font-family: 'JetBrains Mono', monospace; font-size: 12px; font-weight: 600; color: {{ '#34d399' if t.expected_profit >= 0 else '#f87171' }};">${{ "%+.2f"|format(t.expected_profit) }}</td>
            <td style="font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--muted);">{{ t.resolution_duration }}</td>
            <td>
              {% if t.result == 'win' %}
                <span class="win" style="font-weight: 700;">WIN <span style="font-size: 11px; font-weight: 400; color: var(--muted);">${{ "%.2f"|format(t.edge * t.amount_usd if t.edge and t.amount_usd else 0) }}</span></span>
              {% elif t.result == 'loss' %}
                <span class="loss" style="font-weight: 700;">LOSS <span style="font-size: 11px; font-weight: 400; color: var(--muted);">${{ "%.2f"|format(-t.amount_usd if t.amount_usd else 0) }}</span></span>
              {% else %}
                <span class="pill pill-pending">PENDING</span>
              {% endif %}
            </td>
            <td style="font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--muted);">{{ t.time_to_resolve }}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>

  <div class="grid grid-2" style="margin-bottom: 32px;">
    <div class="panel">
      <h2>🩺 Diagnostics + API Links</h2>
      <div class="stat-card">
        <div class="stat-row"><span class="stat-label">DB Exists</span><span class="stat-value {{ 'win' if diag.db_exists else 'loss' }}">{{ diag.db_exists }}</span></div>
        <div class="stat-row"><span class="stat-label">DB Path</span><span class="stat-value mono" style="font-size:12px;">{{ diag.db_path }}</span></div>
        <div class="stat-row"><span class="stat-label">Counts</span><span class="stat-value mono" style="font-size:12px;">{{ diag.counts }}</span></div>
      </div>
      <div style="margin-top:14px; display:flex; flex-wrap:wrap; gap:10px;">
        {% for ep in diag.available_api_endpoints %}
          <a class="api-link" href="{{ ep }}">{{ ep }}</a>
        {% endfor %}
      </div>
    </div>

    <div class="panel">
      <h2>🧾 Live Logs Tail</h2>
      <div class="log-box">
        {% for line in logs %}
          <div class="log-line">{{ line }}</div>
        {% endfor %}
      </div>
      <div class="small" style="margin-top:8px;">If this says no local log found, Railway stdout/stderr logs are still separate from this dashboard process.</div>
    </div>
  </div>

  <div class="footer">
    Polymarket AI Pipeline • DB: {{ db_path }} • Window: {{ window_h }}h
  </div>
</div>

</body>
</html>
"""


@app.route("/")
def home():
    return render_template_string(
        HTML,
        s=_get_summary(),
        strategies=get_strategy_accuracies(),
        signals=get_signal_accuracies(),
        trades=_get_recent_trades(40),
        news=_get_news(20),
        runs=_get_runs(12),
        cfg=_get_engine_config(),
        exp=_get_expectations(),
        diag=_get_diagnostics(),
        logs=_get_logs(80),
        now=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        window_h=_cfg("DEMO_HOURS_WINDOW", 30),
        db_path=str(DB_PATH),
    )


@app.route("/api/summary")
def api_summary():
    return jsonify({
        "summary": _get_summary(),
        "strategies": get_strategy_accuracies(),
        "signals": get_signal_accuracies(),
    })


@app.route("/api/trades")
def api_trades():
    return jsonify(_get_recent_trades(100))


@app.route("/api/news")
def api_news():
    return jsonify(_get_news(50))


@app.route("/api/runs")
def api_runs():
    return jsonify(_get_runs(100))


@app.route("/api/config")
def api_config():
    return jsonify(_get_engine_config())




@app.route("/api/expectations")
def api_expectations():
    return jsonify(_get_expectations())


@app.route("/api/diagnostics")
def api_diagnostics():
    return jsonify(_get_diagnostics())


@app.route("/api/logs")
def api_logs():
    return jsonify({"lines": _get_logs(200)})


@app.route("/healthz")
def health():
    return "ok", 200


@app.route("/debug/duration")
def debug_duration():
    """Debug endpoint to trace duration calculation"""
    rows = _q(
        "SELECT id, created_at, end_date_iso, resolved_at, result "
        "FROM demo_trades "
        "ORDER BY id DESC LIMIT 5"
    )
    results = []
    for r in rows:
        info = dict(r)
        ds = info.get("end_date_iso") or info.get("resolved_at")
        ca = info.get("created_at")
        if ds and ca:
            try:
                cd = datetime.fromisoformat(ds.replace("Z", "+00:00"))
                ct = datetime.fromisoformat(ca.replace("Z", "+00:00"))
                cd = cd.replace(tzinfo=None)
                ct = ct.replace(tzinfo=None)
                info["_secs"] = int((cd - ct).total_seconds())
            except Exception as e:
                info["_error"] = str(e)
        info["_has_ds"] = bool(ds)
        info["_has_ca"] = bool(ca)
        results.append(info)
    return jsonify(results)


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


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8081"))
    print(f"Dashboard running on http://0.0.0.0:{port}")
    print(f"   DB: {DB_PATH}")
    app.run(host="0.0.0.0", port=port, debug=False)

# trigger redeploy
