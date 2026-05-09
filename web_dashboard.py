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

# Resilient imports — dashboard must start even if heavy modules fail
try:
    import logger as _logger  # ensures init_db ran
    from logger import DB_PATH
except Exception:
    DB_PATH = "polymarket.db"

try:
    from resolver import (
        get_accuracy_stats,
        get_signal_accuracies,
        get_strategy_accuracies,
    )
except Exception:
    def get_accuracy_stats(): return {"accuracy_pct": 0, "wins": 0, "losses": 0}
    def get_signal_accuracies(): return []
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
    acc = get_accuracy_stats()
    bk = get_current_bankroll()
    pnl = todays_pnl()
    allowed, reason = can_trade_today()

    pending = _q(
        "SELECT COUNT(*) as c FROM trades WHERE status IN ('demo','dry_run') "
        "AND id NOT IN (SELECT trade_id FROM outcomes)"
    )[0]["c"]

    total_trades = _q("SELECT COUNT(*) as c FROM trades")[0]["c"]
    total_resolved = _q("SELECT COUNT(*) as c FROM outcomes")[0]["c"]
    total_pnl = _q("SELECT COALESCE(SUM(pnl),0) as p FROM outcomes")[0]["p"]

    return {
        "bankroll": round(bk, 2),
        "todays_pnl": round(pnl, 2),
        "total_pnl": round(total_pnl, 2),
        "trades_today_allowed": allowed,
        "trade_block_reason": reason,
        "accuracy_pct": acc.get("accuracy_pct", 0),
        "wins": acc.get("wins", 0),
        "losses": acc.get("losses", 0),
        "resolved": total_resolved,
        "pending": pending,
        "total_trades": total_trades,
        "go_live_remaining": max(0, 30 - total_resolved),
    }


def _get_recent_trades(limit: int = 30) -> list[dict]:
    rows = _q(
        """SELECT t.id, t.created_at, t.market_question, t.side,
                  t.market_price, t.claude_score, t.edge, t.amount_usd,
                  t.status, t.strategy, t.signals, t.classification,
                  t.materiality, t.news_source, t.end_date_iso,
                  o.result, o.pnl, o.resolved_at
           FROM trades t
           LEFT JOIN outcomes o ON o.trade_id = t.id
           ORDER BY t.id DESC LIMIT ?""",
        (limit,),
    )
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
        # Priority: end_date_iso > resolved_at (from outcomes) > time_to_resolve fallback
        r["resolution_duration"] = ""
        end_iso = r.get("end_date_iso")
        resolved_at = r.get("resolved_at")
        created_at = r.get("created_at")
        duration_source = end_iso or resolved_at  # use whichever is available
        if duration_source and created_at:
            try:
                close_dt = datetime.fromisoformat(duration_source.replace("Z", "+00:00"))
                create_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                # Strip tzinfo from both to avoid naive/aware mismatch
                close_dt = close_dt.replace(tzinfo=None)
                create_dt = create_dt.replace(tzinfo=None)
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
        amount = r.get("amount_usd", 1.0)
        side = r.get("side", "YES")
        edge = r.get("edge", 0.0) or 0.0
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
          <span class="stat-value {{ 'win' if s.accuracy_pct >= 80 and s.resolved >= 30 else 'warn' }}">
            {{ 'PRODUCTION' if s.accuracy_pct >= 80 and s.resolved >= 30 else 'DRY-RUN / TRIAL' }}
          </span>
        </div>
        <div class="stat-row">
          <span class="stat-label">Trial Progress</span>
          <span class="stat-value">{{ s.resolved }} / 30</span>
        </div>
        <div class="progress-bg"><div class="progress-fill" style="width: {{ (s.resolved/30)*100 }}%"></div></div>
        <div class="stat-row" style="margin-top: 4px; border-bottom:0;">
          <span class="stat-label">Gate Status</span>
          <span class="stat-value {{ 'win' if s.trades_today_allowed else 'loss' }}">
             {{ 'OPEN' if s.trades_today_allowed else 'BLOCKED' }}
          </span>
        </div>
      </div>
    </div>
  </div>

  <!-- STRATEGIES & SIGNALS -->
  <div class="grid grid-2" style="margin-bottom: 32px;">
    <div class="panel">
      <h2>🏆 Strategy Leaderboard</h2>
      {% for st in strategies %}
        {% set acc = (st.wins / (st.wins + st.losses) * 100) if (st.wins + st.losses) > 0 else 0 %}
        <div class="strategy-item">
          <div class="strategy-header">
            <span style="font-weight: 500;">{{ st.strategy }}</span>
            <span><span class="{{ 'win' if acc >= 75 else 'warn' }}">{{ acc|round(1) }}%</span> <span class="muted">acc</span></span>
          </div>
          <div class="progress-bg"><div class="progress-fill" style="width: {{ acc }}%"></div></div>
          <div style="font-size: 11px; color: var(--muted); margin-top: 4px;">
            {{ st.wins }}W - {{ st.losses }}L • {{ st.total }} trades • ${{ st.pnl }} PnL
          </div>
        </div>
      {% endfor %}
    </div>

    <div class="panel">
      <h2>📡 Signal Intelligence</h2>
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
                <span class="win" style="font-weight: 700;">WIN <span style="font-size: 11px; font-weight: 400; color: var(--muted);">${{ "%.2f"|format(t.pnl) }}</span></span>
              {% elif t.result == 'loss' %}
                <span class="loss" style="font-weight: 700;">LOSS <span style="font-size: 11px; font-weight: 400; color: var(--muted);">${{ "%.2f"|format(t.pnl) }}</span></span>
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
        now=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        window_h=os.getenv("DEMO_HOURS_WINDOW", "30"),
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


@app.route("/healthz")
def health():
    return "ok", 200


@app.route("/debug/duration")
def debug_duration():
    """Debug endpoint to trace duration calculation"""
    rows = _q(
        "SELECT t.id, t.created_at, t.end_date_iso, o.resolved_at, o.result "
        "FROM trades t LEFT JOIN outcomes o ON o.trade_id = t.id "
        "ORDER BY t.id DESC LIMIT 5"
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


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8081"))
    print(f"Dashboard running on http://0.0.0.0:{port}")
    print(f"   DB: {DB_PATH}")
    app.run(host="0.0.0.0", port=port, debug=False)
