"""
sniper.py — Ultra-Fast Sniper Execution Engine

Implements the "Poly Sniper AI" paradigm from Video 1:
1. Timing Edge Capture: When insider/whale alerts fire, instantly place orders
   before the market adjusts odds
2. Order-Flow Anomaly Triggers: Scan blockchain for sudden wallet inflows
   into specific contract positions
3. Auto-Bet System: Configurable stop-loss, safety cut, max bet, credit limit
4. Neural Network Ensemble Signals: Aggregates multiple AI signals for direction

The sniper is event-driven — it listens for alerts from onchain_scanner.py
and executes trades with minimal latency.
"""

import os
import json
import time
import sqlite3
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import datetime, timezone

from config import DB_PATH as DB_FILE

log = logging.getLogger("sniper")

# ─── Config ────────────────────────────────────────────────────────────────────
SNIPER_ENABLED = os.getenv("SNIPER_ENABLED", "true").lower() == "true"
SNIPER_MAX_BET_USD = float(os.getenv("SNIPER_MAX_BET_USD", "10.0"))
SNIPER_MIN_CONFIDENCE = float(os.getenv("SNIPER_MIN_CONFIDENCE", "0.7"))
SNIPER_STOP_LOSS_PCT = float(os.getenv("SNIPER_STOP_LOSS_PCT", "0.15"))  # 15% stop-loss
SNIPER_SAFETY_CUT_PCT = float(os.getenv("SNIPER_SAFETY_CUT_PCT", "0.25"))  # 25% safety cut
SNIPER_MAX_DAILY_TRADES = int(os.getenv("SNIPER_MAX_DAILY_TRADES", "20"))
SNIPER_COOLDOWN_SECS = int(os.getenv("SNIPER_COOLDOWN_SECS", "60"))
SNIPER_CREDIT_LIMIT_USD = float(os.getenv("SNIPER_CREDIT_LIMIT_USD", "50.0"))
SNIPER_VELOCITY_WINDOW = int(os.getenv("SNIPER_VELOCITY_WINDOW", "300"))  # 5 min window


@dataclass
class SniperSignal:
    """A sniper execution signal from aggregated sources."""
    condition_id: str
    question: str
    direction: str  # "yes" or "no"
    confidence: float  # 0.0 - 1.0
    trigger_source: str  # "whale_alert", "order_flow_anomaly", "ai_signal", "volume_spike"
    market_price: float
    target_price: float
    edge: float  # confidence - market_price
    urgency: str  # "low", "medium", "high", "critical"
    metadata: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    @property
    def is_actionable(self) -> bool:
        return (
            self.confidence >= SNIPER_MIN_CONFIDENCE
            and abs(self.edge) >= 0.05
            and self.urgency in ("medium", "high", "critical")
        )


@dataclass
class SniperTrade:
    """A sniper execution trade record."""
    signal_id: str
    condition_id: str
    side: str
    entry_price: float
    size_usd: float
    confidence: float
    trigger_source: str
    stop_loss: float
    safety_cut: float
    status: str = "pending"  # pending, filled, cancelled, stopped_out, safety_exited
    exit_price: Optional[float] = None
    pnl: Optional[float] = None
    exit_reason: Optional[str] = None
    latency_ms: Optional[float] = None
    timestamp: float = field(default_factory=time.time)


# ─── Database ──────────────────────────────────────────────────────────────────
def _init_sniper_tables():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sniper_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            condition_id TEXT NOT NULL,
            question TEXT,
            direction TEXT NOT NULL,
            confidence REAL NOT NULL,
            trigger_source TEXT NOT NULL,
            market_price REAL,
            target_price REAL,
            edge REAL,
            urgency TEXT,
            metadata TEXT,
            acted INTEGER DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sniper_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id TEXT NOT NULL,
            condition_id TEXT NOT NULL,
            side TEXT NOT NULL,
            entry_price REAL NOT NULL,
            size_usd REAL NOT NULL,
            confidence REAL NOT NULL,
            trigger_source TEXT NOT NULL,
            stop_loss REAL NOT NULL,
            safety_cut REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            exit_price REAL,
            pnl REAL,
            exit_reason TEXT,
            latency_ms REAL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sniper_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            condition_id TEXT NOT NULL UNIQUE,
            side TEXT NOT NULL,
            entry_price REAL NOT NULL,
            current_price REAL,
            size_usd REAL NOT NULL,
            stop_loss_price REAL NOT NULL,
            safety_cut_price REAL NOT NULL,
            unrealized_pnl REAL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'open',
            opened_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


def save_signal(signal: SniperSignal):
    _init_sniper_tables()
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        INSERT INTO sniper_signals
        (condition_id, question, direction, confidence, trigger_source,
         market_price, target_price, edge, urgency, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (signal.condition_id, signal.question, signal.direction,
          signal.confidence, signal.trigger_source, signal.market_price,
          signal.target_price, signal.edge, signal.urgency,
          json.dumps(signal.metadata)))
    conn.commit()
    conn.close()


def save_sniper_trade(trade: SniperTrade):
    _init_sniper_tables()
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        INSERT INTO sniper_trades
        (signal_id, condition_id, side, entry_price, size_usd, confidence,
         trigger_source, stop_loss, safety_cut, status, exit_price,
         pnl, exit_reason, latency_ms)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (trade.signal_id, trade.condition_id, trade.side, trade.entry_price,
          trade.size_usd, trade.confidence, trade.trigger_source,
          trade.stop_loss, trade.safety_cut, trade.status, trade.exit_price,
          trade.pnl, trade.exit_reason, trade.latency_ms))
    conn.commit()
    conn.close()


def get_sniper_stats() -> dict:
    _init_sniper_tables()
    conn = sqlite3.connect(DB_FILE)
    trades = conn.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses,
            COALESCE(SUM(pnl), 0) as total_pnl,
            COALESCE(AVG(confidence), 0) as avg_confidence,
            COALESCE(AVG(latency_ms), 0) as avg_latency_ms,
            COUNT(DISTINCT trigger_source) as sources_used,
            COALESCE(AVG(size_usd), 0) as avg_size,
            SUM(CASE WHEN exit_reason = 'stop_loss' THEN 1 ELSE 0 END) as stop_losses,
            SUM(CASE WHEN exit_reason = 'safety_cut' THEN 1 ELSE 0 END) as safety_cuts
        FROM sniper_trades
    """).fetchone()
    signals = conn.execute("SELECT COUNT(*) FROM sniper_signals").fetchone()[0]
    acted = conn.execute("SELECT COUNT(*) FROM sniper_signals WHERE acted = 1").fetchone()[0]
    open_pos = conn.execute("SELECT COUNT(*) FROM sniper_positions WHERE status = 'open'").fetchone()[0]
    conn.close()

    return {
        "total_trades": trades[0] or 0,
        "wins": trades[1] or 0,
        "losses": trades[2] or 0,
        "total_pnl": round(trades[3] or 0, 4),
        "avg_confidence": round(trades[4] or 0, 3),
        "avg_latency_ms": round(trades[5] or 0, 1),
        "sources_used": trades[6] or 0,
        "avg_size_usd": round(trades[7] or 0, 2),
        "stop_losses": trades[8] or 0,
        "safety_cuts": trades[9] or 0,
        "total_signals": signals,
        "signals_acted": acted,
        "open_positions": open_pos,
    }


def get_open_positions() -> list[dict]:
    """Get all open sniper positions for monitoring."""
    _init_sniper_tables()
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT * FROM sniper_positions WHERE status = 'open'
        ORDER BY opened_at DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── Signal Generation ─────────────────────────────────────────────────────────
def generate_signal_from_whale_alert(alert: dict) -> Optional[SniperSignal]:
    """
    Convert a whale alert from onchain_scanner into a sniper signal.
    Whale buying → signal to buy (front-run the insider).
    """
    if not SNIPER_ENABLED:
        return None

    severity = alert.get("severity", "low")
    amount = alert.get("amount_usd", 0)
    alert_type = alert.get("alert_type", "")
    side = alert.get("side", "")

    # Calculate confidence based on severity and amount
    severity_scores = {"low": 0.3, "medium": 0.5, "high": 0.7, "critical": 0.9}
    base_confidence = severity_scores.get(severity, 0.3)

    # Boost confidence for larger amounts
    amount_boost = min(0.2, amount / 50000)
    confidence = min(1.0, base_confidence + amount_boost)

    # Urgency mapping
    urgency_map = {"low": "low", "medium": "medium", "high": "high", "critical": "critical"}
    urgency = urgency_map.get(severity, "low")

    direction = side if side in ("yes", "no") else "yes"

    return SniperSignal(
        condition_id=alert.get("condition_id", ""),
        question=alert.get("market", alert.get("question", "")),
        direction=direction,
        confidence=confidence,
        trigger_source="whale_alert",
        market_price=alert.get("price", 0.5),
        target_price=alert.get("price", 0.5) + (0.05 if direction == "yes" else -0.05),
        edge=confidence - alert.get("price", 0.5),
        urgency=urgency,
        metadata={
            "alert_type": alert_type,
            "amount_usd": amount,
            "wallet": alert.get("wallet", ""),
            "severity": severity,
        },
    )


def generate_signal_from_anomaly(flow: dict) -> Optional[SniperSignal]:
    """
    Convert an order-flow anomaly into a sniper signal.
    High anomaly score + volume spike = potential insider activity.
    """
    if not SNIPER_ENABLED:
        return None

    anomaly_score = flow.get("anomaly_score", 0)
    if anomaly_score < 0.5:
        return None

    volume = flow.get("total_volume", 0)
    large_trades = flow.get("large_trade_count", 0)
    buy_pressure = flow.get("buy_pressure", 0.5)

    direction = "yes" if buy_pressure > 0.6 else ("no" if buy_pressure < 0.4 else "yes")
    confidence = min(1.0, anomaly_score * 0.8 + (large_trades / 10) * 0.2)

    urgency = "low"
    if anomaly_score > 0.8:
        urgency = "critical"
    elif anomaly_score > 0.6:
        urgency = "high"
    elif anomaly_score > 0.4:
        urgency = "medium"

    market_price = buy_pressure  # proxy

    return SniperSignal(
        condition_id=flow.get("condition_id", ""),
        question=flow.get("question", ""),
        direction=direction,
        confidence=confidence,
        trigger_source="order_flow_anomaly",
        market_price=market_price,
        target_price=market_price + (0.03 if direction == "yes" else -0.03),
        edge=abs(confidence - market_price),
        urgency=urgency,
        metadata={
            "anomaly_score": anomaly_score,
            "volume": volume,
            "large_trades": large_trades,
            "buy_pressure": buy_pressure,
        },
    )


def generate_signal_from_ai(ai_result: dict) -> Optional[SniperSignal]:
    """
    Convert AI insights into a sniper signal.
    Aggregates multi-model consensus into a single high-confidence signal.
    """
    if not SNIPER_ENABLED:
        return None

    probability = ai_result.get("probability", 0.5)
    consensus = ai_result.get("consensus_score", 0)
    source = ai_result.get("source", "ai")

    # Only act on strong AI signals
    if consensus < 0.6:
        return None

    direction = "yes" if probability > 0.55 else ("no" if probability < 0.45 else "yes")
    confidence = consensus
    market_price = ai_result.get("market_price", 0.5)
    edge = abs(probability - market_price)

    if edge < 0.05:
        return None

    urgency = "low"
    if edge > 0.20 and consensus > 0.8:
        urgency = "critical"
    elif edge > 0.15 and consensus > 0.7:
        urgency = "high"
    elif edge > 0.10:
        urgency = "medium"

    return SniperSignal(
        condition_id=ai_result.get("condition_id", ""),
        question=ai_result.get("question", ""),
        direction=direction,
        confidence=confidence,
        trigger_source="ai_signal",
        market_price=market_price,
        target_price=probability,
        edge=edge,
        urgency=urgency,
        metadata={
            "probability": probability,
            "consensus": consensus,
            "source": source,
            "models_agreed": ai_result.get("models_agreed", 1),
        },
    )


# ─── Auto-Bet Engine ───────────────────────────────────────────────────────────
def check_daily_limits() -> dict:
    """Check if we're within daily trading limits."""
    _init_sniper_tables()
    conn = sqlite3.connect(DB_FILE)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    trades_today = conn.execute("""
        SELECT COUNT(*), COALESCE(SUM(size_usd), 0)
        FROM sniper_trades
        WHERE date(created_at) = ?
    """, (today,)).fetchone()

    pnl_today = conn.execute("""
        SELECT COALESCE(SUM(pnl), 0)
        FROM sniper_trades
        WHERE date(created_at) = ? AND pnl IS NOT NULL
    """, (today,)).fetchone()

    conn.close()

    trade_count = trades_today[0] or 0
    total_spent = trades_today[1] or 0
    daily_pnl = pnl_today[0] or 0

    return {
        "trades_today": trade_count,
        "total_spent_usd": round(total_spent, 2),
        "daily_pnl": round(daily_pnl, 4),
        "can_trade": (
            trade_count < SNIPER_MAX_DAILY_TRADES
            and total_spent < SNIPER_CREDIT_LIMIT_USD
        ),
        "max_trades": SNIPER_MAX_DAILY_TRADES,
        "credit_remaining": round(SNIPER_CREDIT_LIMIT_USD - total_spent, 2),
    }


def compute_stop_loss_safety_cut(entry_price: float, direction: str) -> tuple[float, float]:
    """
    Compute stop-loss and safety-cut prices.
    Stop-loss: exit if price moves against us by SNIPER_STOP_LOSS_PCT
    Safety-cut: exit if price moves against us by SNIPER_SAFETY_CUT_PCT
    """
    if direction == "yes":
        stop_loss = round(entry_price * (1 - SNIPER_STOP_LOSS_PCT), 4)
        safety_cut = round(entry_price * (1 - SNIPER_SAFETY_CUT_PCT), 4)
    else:
        stop_loss = round(entry_price * (1 + SNIPER_STOP_LOSS_PCT), 4)
        safety_cut = round(entry_price * (1 + SNIPER_SAFETY_CUT_PCT), 4)
    return stop_loss, safety_cut


def auto_execute_signal(signal: SniperSignal) -> Optional[SniperTrade]:
    """
    Auto-execute a sniper signal if all conditions are met.
    Implements the full auto-bet system with stop-loss and safety cut.
    """
    if not signal.is_actionable:
        log.debug(f"[sniper] Signal not actionable: {signal.question[:40]}… "
                  f"conf={signal.confidence:.2f} edge={signal.edge:.3f}")
        return None

    # Check daily limits
    limits = check_daily_limits()
    if not limits["can_trade"]:
        log.warning(f"[sniper] Daily limit hit: {limits['trades_today']}/{limits['max_trades']} trades, "
                    f"${limits['credit_remaining']:.2f} credit remaining")
        return None

    # Compute position size based on confidence and urgency
    urgency_multiplier = {"low": 0.3, "medium": 0.5, "high": 0.8, "critical": 1.0}
    base_size = SNIPER_MAX_BET_USD * signal.confidence
    size = base_size * urgency_multiplier.get(signal.urgency, 0.5)
    size = min(size, limits["credit_remaining"], SNIPER_MAX_BET_USD)
    size = max(0.50, size)  # minimum bet

    # Compute stop-loss and safety cut
    stop_loss, safety_cut = compute_stop_loss_safety_cut(signal.market_price, signal.direction)

    # Record latency (simulated in demo mode)
    start_time = time.time()
    latency_ms = round((time.time() - start_time) * 1000, 1)

    trade = SniperTrade(
        signal_id=f"sig_{int(signal.timestamp)}",
        condition_id=signal.condition_id,
        side=signal.direction,
        entry_price=signal.market_price,
        size_usd=round(size, 2),
        confidence=signal.confidence,
        trigger_source=signal.trigger_source,
        stop_loss=stop_loss,
        safety_cut=safety_cut,
        status="simulated",
        latency_ms=latency_ms,
    )

    save_sniper_trade(trade)

    # Mark signal as acted
    _init_sniper_tables()
    conn = sqlite3.connect(DB_FILE)
    conn.execute("UPDATE sniper_signals SET acted = 1 WHERE condition_id = ? ORDER BY id DESC LIMIT 1",
                 (signal.condition_id,))
    conn.commit()
    conn.close()

    log.info(f"[sniper] ⚡ SNIPED: {signal.question[:50]}… "
             f"dir={signal.direction} size=${size:.2f} "
             f"conf={signal.confidence:.2f} trigger={signal.trigger_source} "
             f"SL={stop_loss:.3f} SC={safety_cut:.3f}")

    return trade


def check_stop_losses(current_prices: dict) -> list[dict]:
    """
    Check open positions against stop-loss and safety-cut levels.
    current_prices: {condition_id: current_price}
    Returns list of triggered exits.
    """
    positions = get_open_positions()
    triggered = []

    for pos in positions:
        cid = pos["condition_id"]
        if cid not in current_prices:
            continue

        current = current_prices[cid]
        side = pos["side"]

        # Check stop-loss
        if side == "yes" and current <= pos["stop_loss_price"]:
            triggered.append({**pos, "exit_reason": "stop_loss", "exit_price": current})
        elif side == "no" and current >= pos["stop_loss_price"]:
            triggered.append({**pos, "exit_reason": "stop_loss", "exit_price": current})

        # Check safety cut
        elif side == "yes" and current <= pos["safety_cut_price"]:
            triggered.append({**pos, "exit_reason": "safety_cut", "exit_price": current})
        elif side == "no" and current >= pos["safety_cut_price"]:
            triggered.append({**pos, "exit_reason": "safety_cut", "exit_price": current})

    return triggered


# ─── Main Sniper Loop ──────────────────────────────────────────────────────────
def run_sniper_cycle(whale_alerts: list = None, order_flow: list = None,
                     ai_results: list = None) -> dict:
    """
    Run one full sniper cycle.
    Aggregates signals from all sources, filters, and auto-executes.
    """
    if not SNIPER_ENABLED:
        return {"enabled": False}

    log.info("[sniper] ═══ SNIPER CYCLE ═══")
    signals = []

    # Generate signals from whale alerts
    if whale_alerts:
        for alert in whale_alerts:
            sig = generate_signal_from_whale_alert(alert)
            if sig:
                save_signal(sig)
                signals.append(sig)
        log.info(f"[sniper] {len(whale_alerts)} whale alerts → "
                 f"{sum(1 for s in signals if s.trigger_source == 'whale_alert')} signals")

    # Generate signals from order-flow anomalies
    if order_flow:
        for flow in order_flow:
            sig = generate_signal_from_anomaly(flow)
            if sig:
                save_signal(sig)
                signals.append(sig)
        log.info(f"[sniper] {len(order_flow)} flow analyses → "
                 f"{sum(1 for s in signals if s.trigger_source == 'order_flow_anomaly')} signals")

    # Generate signals from AI insights
    if ai_results:
        for ai in ai_results:
            sig = generate_signal_from_ai(ai)
            if sig:
                save_signal(sig)
                signals.append(sig)
        log.info(f"[sniper] {len(ai_results)} AI results → "
                 f"{sum(1 for s in signals if s.trigger_source == 'ai_signal')} signals")

    # Filter to actionable signals
    actionable = [s for s in signals if s.is_actionable]
    log.info(f"[sniper] {len(signals)} total signals, {len(actionable)} actionable")

    # Auto-execute
    trades = []
    for sig in sorted(actionable, key=lambda s: s.confidence * (1 if s.urgency == "critical" else 0.7),
                      reverse=True):
        trade = auto_execute_signal(sig)
        if trade:
            trades.append(trade)

    stats = get_sniper_stats()

    log.info(f"[sniper] Executed {len(trades)} trades | "
             f"Total: {stats['total_trades']} | PnL: ${stats['total_pnl']:.2f} | "
             f"Win rate: {stats['wins']}/{stats['wins'] + stats['losses']}")

    return {
        "enabled": True,
        "signals_total": len(signals),
        "signals_actionable": len(actionable),
        "trades_executed": len(trades),
        "stats": stats,
    }


# ─── Position Monitor ──────────────────────────────────────────────────────────
def monitor_positions(current_prices: dict) -> list[dict]:
    """
    Monitor open positions for stop-loss and safety-cut triggers.
    Called periodically with current market prices.
    """
    triggered = check_stop_losses(current_prices)

    for pos in triggered:
        _init_sniper_tables()
        conn = sqlite3.connect(DB_FILE)
        conn.execute("""
            UPDATE sniper_positions
            SET status = 'closed', current_price = ?, updated_at = datetime('now')
            WHERE condition_id = ? AND status = 'open'
        """, (pos["exit_price"], pos["condition_id"]))
        conn.commit()
        conn.close()

        log.warning(f"[sniper] 🛑 {pos['exit_reason'].upper()}: {pos['condition_id'][:12]}… "
                    f"exit={pos['exit_price']:.3f}")

    return triggered


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

    # Demo: test with sample data
    sample_alert = {
        "condition_id": "0x1234",
        "market": "Will BTC hit 100k by end of 2025?",
        "alert_type": "whale_buy",
        "side": "yes",
        "amount_usd": 15000,
        "price": 0.65,
        "severity": "high",
        "wallet": "0xabcd...1234",
    }

    sample_flow = {
        "condition_id": "0x5678",
        "question": "Will ETH be above 5000 by March?",
        "anomaly_score": 0.75,
        "total_volume": 50000,
        "large_trade_count": 5,
        "buy_pressure": 0.7,
    }

    result = run_sniper_cycle(whale_alerts=[sample_alert], order_flow=[sample_flow])
    print(json.dumps(result, indent=2, default=str))