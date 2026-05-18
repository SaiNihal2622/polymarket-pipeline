"""
On-Chain Scanner — Blockchain Order Flow & Whale Anomaly Detection

Inspired by Poly Sniper AI's "Insider Alerts Tracker":
1. Monitors Polymarket CTF Exchange contract for large trades
2. Tracks whale wallet activity via Polymarket data-api
3. Detects order flow anomalies (sudden volume spikes, concentrated positions)
4. Alerts on potential insider-pattern activity

Uses Polymarket data-api (no auth, Railway-friendly) + Polygonscan API (free tier).
"""

import os
import time
import json
import sqlite3
import logging
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone, timedelta

import httpx

from config import DB_FILE

log = logging.getLogger("onchain")

# ─── Config ────────────────────────────────────────────────────────────────────
POLYGONSCAN_API_KEY = os.getenv("POLYGONSCAN_API_KEY", "")
CTF_EXCHANGE = os.getenv("CTF_EXCHANGE", "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E").lower()
NEG_RISK_EXCHANGE = os.getenv("NEG_RISK_EXCHANGE", "0xC5d563A36AE78145C45a50134d48A1215220f80a").lower()
USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174".lower()
WALLET_ALERT_THRESHOLD_USD = float(os.getenv("WALLET_ALERT_THRESHOLD", "5000"))
VOLUME_SPIKE_MULTIPLIER = float(os.getenv("VOLUME_SPIKE_MULT", "3.0"))
SCAN_INTERVAL_SECONDS = int(os.getenv("ONCHAIN_SCAN_INTERVAL", "120"))


@dataclass
class WhaleAlert:
    """A detected whale/anomaly event."""
    alert_type: str  # "whale_buy", "whale_sell", "volume_spike", "concentration"
    market_id: str
    market_question: str = ""
    wallet: str = ""
    side: str = ""  # "yes" or "no"
    amount_usd: float = 0.0
    price: float = 0.0
    detail: str = ""
    severity: str = "medium"  # low, medium, high, critical
    timestamp: float = field(default_factory=time.time)


@dataclass
class OrderFlowSummary:
    """Aggregated order flow for a market."""
    condition_id: str
    question: str
    total_volume: float = 0.0
    large_trades: int = 0
    unique_wallets: int = 0
    yes_pressure: float = 0.0  # 0-1, >0.5 = bullish
    no_pressure: float = 0.0
    whale_count: int = 0
    whale_total_usd: float = 0.0
    anomaly_score: float = 0.0  # 0-1


# ─── Database ──────────────────────────────────────────────────────────────────
def _init_onchain_tables():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS whale_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_type TEXT NOT NULL,
            market_id TEXT NOT NULL,
            market_question TEXT DEFAULT '',
            wallet TEXT DEFAULT '',
            side TEXT DEFAULT '',
            amount_usd REAL DEFAULT 0,
            price REAL DEFAULT 0,
            detail TEXT DEFAULT '',
            severity TEXT DEFAULT 'medium',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS order_flow (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            condition_id TEXT NOT NULL,
            question TEXT DEFAULT '',
            total_volume REAL DEFAULT 0,
            large_trades INTEGER DEFAULT 0,
            unique_wallets INTEGER DEFAULT 0,
            yes_pressure REAL DEFAULT 0,
            no_pressure REAL DEFAULT 0,
            whale_count INTEGER DEFAULT 0,
            whale_total_usd REAL DEFAULT 0,
            anomaly_score REAL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


def save_alert(alert: WhaleAlert):
    _init_onchain_tables()
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        INSERT INTO whale_alerts
        (alert_type, market_id, market_question, wallet, side, amount_usd, price, detail, severity)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (alert.alert_type, alert.market_id, alert.market_question,
          alert.wallet, alert.side, alert.amount_usd, alert.price,
          alert.detail, alert.severity))
    conn.commit()
    conn.close()


def save_flow(flow: OrderFlowSummary):
    _init_onchain_tables()
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        INSERT INTO order_flow
        (condition_id, question, total_volume, large_trades, unique_wallets,
         yes_pressure, no_pressure, whale_count, whale_total_usd, anomaly_score)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (flow.condition_id, flow.question, flow.total_volume, flow.large_trades,
          flow.unique_wallets, flow.yes_pressure, flow.no_pressure,
          flow.whale_count, flow.whale_total_usd, flow.anomaly_score))
    conn.commit()
    conn.close()


def get_recent_alerts(limit: int = 50) -> list[dict]:
    _init_onchain_tables()
    conn = sqlite3.connect(DB_FILE)
    rows = conn.execute("""
        SELECT alert_type, market_id, market_question, wallet, side,
               amount_usd, price, detail, severity, created_at
        FROM whale_alerts ORDER BY id DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [
        {
            "type": r[0], "market_id": r[1], "question": r[2],
            "wallet": r[3][:10] + "…" if r[3] and len(r[3]) > 10 else r[3],
            "side": r[4], "amount_usd": r[5], "price": r[6],
            "detail": r[7], "severity": r[8], "time": r[9],
        }
        for r in rows
    ]


# ─── Polymarket Data API (whale positions) ─────────────────────────────────────
def fetch_top_holders(condition_id: str, limit: int = 20) -> list[dict]:
    """Fetch top position holders for a market from Polymarket data-api."""
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                "https://data-api.polymarket.com/holders",
                params={"conditionId": condition_id, "limit": limit}
            )
            resp.raise_for_status()
            return resp.json() or []
    except Exception as e:
        log.debug(f"[onchain] holders fetch failed: {e}")
        return []


def fetch_market_trades(condition_id: str, limit: int = 100) -> list[dict]:
    """Fetch recent trades for a market."""
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                "https://data-api.polymarket.com/trades",
                params={"market": condition_id, "limit": limit}
            )
            resp.raise_for_status()
            return resp.json() or []
    except Exception as e:
        log.debug(f"[onchain] trades fetch failed: {e}")
        return []


# ─── Polygonscan (on-chain transactions) ───────────────────────────────────────
def fetch_contract_transactions(contract: str, start_block: int = 0) -> list[dict]:
    """Fetch recent transactions to a contract via Polygonscan API."""
    if not POLYGONSCAN_API_KEY:
        return []

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                "https://api.polygonscan.com/api",
                params={
                    "module": "account",
                    "action": "txlist",
                    "address": contract,
                    "startblock": start_block,
                    "endblock": 99999999,
                    "sort": "desc",
                    "apikey": POLYGONSCAN_API_KEY,
                    "page": 1,
                    "offset": 50,
                }
            )
            data = resp.json()
            if data.get("status") == "1":
                return data.get("result", [])
            return []
    except Exception as e:
        log.debug(f"[onchain] polygonscan fetch failed: {e}")
        return []


# ─── Anomaly Detection ────────────────────────────────────────────────────────
def detect_whale_activity(condition_id: str, question: str = "") -> list[WhaleAlert]:
    """Detect whale buys/sells in a market."""
    alerts = []

    # Fetch top holders
    holders = fetch_top_holders(condition_id)
    for h in holders:
        value = float(h.get("value", 0) or h.get("amount", 0) or 0)
        if value >= WALLET_ALERT_THRESHOLD_USD:
            wallet = h.get("address", h.get("wallet", ""))
            side = h.get("side", h.get("outcome", ""))
            alert = WhaleAlert(
                alert_type="whale_position",
                market_id=condition_id,
                market_question=question,
                wallet=wallet,
                side=str(side).lower(),
                amount_usd=round(value, 2),
                price=float(h.get("price", 0) or 0),
                detail=f"Whale holds ${value:,.0f} on {side}",
                severity="high" if value >= WALLET_ALERT_THRESHOLD_USD * 5 else "medium",
            )
            alerts.append(alert)
            save_alert(alert)

    return alerts


def detect_volume_spike(condition_id: str, question: str = "",
                        current_volume: float = 0, avg_volume: float = 0) -> Optional[WhaleAlert]:
    """Detect unusual volume spikes (potential insider activity)."""
    if avg_volume <= 0 or current_volume <= 0:
        return None

    ratio = current_volume / avg_volume

    if ratio >= VOLUME_SPIKE_MULTIPLIER:
        severity = "critical" if ratio >= 5.0 else "high" if ratio >= 4.0 else "medium"
        alert = WhaleAlert(
            alert_type="volume_spike",
            market_id=condition_id,
            market_question=question,
            amount_usd=round(current_volume, 2),
            detail=f"Volume {ratio:.1f}x above average (${current_volume:,.0f} vs ${avg_volume:,.0f} avg)",
            severity=severity,
        )
        save_alert(alert)
        return alert
    return None


def analyze_order_flow(condition_id: str, question: str = "") -> OrderFlowSummary:
    """Analyze order flow for a market — trades, whale activity, pressure."""
    trades = fetch_market_trades(condition_id)

    total_volume = 0.0
    large_trades = 0
    wallets = set()
    yes_vol = 0.0
    no_vol = 0.0

    for t in trades:
        amount = float(t.get("amount", 0) or t.get("usdcSize", 0) or 0)
        total_volume += amount
        side = str(t.get("side", t.get("outcome", ""))).lower()
        if side in ("yes", "buy"):
            yes_vol += amount
        else:
            no_vol += amount

        if amount >= 1000:
            large_trades += 1

        wallet = t.get("maker", t.get("taker", t.get("wallet", "")))
        if wallet:
            wallets.add(wallet.lower())

    # Whale analysis
    holders = fetch_top_holders(condition_id)
    whale_count = sum(1 for h in holders
                      if float(h.get("value", 0) or h.get("amount", 0) or 0) >= WALLET_ALERT_THRESHOLD_USD)
    whale_total = sum(float(h.get("value", 0) or h.get("amount", 0) or 0)
                      for h in holders
                      if float(h.get("value", 0) or h.get("amount", 0) or 0) >= WALLET_ALERT_THRESHOLD_USD)

    total = yes_vol + no_vol if (yes_vol + no_vol) > 0 else 1
    yes_pressure = yes_vol / total
    no_pressure = no_vol / total

    # Anomaly score: combines volume spike + whale concentration + large trade ratio
    trade_count = len(trades) if trades else 1
    anomaly_score = min(1.0, (
        (large_trades / trade_count) * 0.3 +
        (whale_count / max(1, len(holders))) * 0.4 +
        (1 if total_volume > WALLET_ALERT_THRESHOLD_USD * 10 else 0.5) * 0.3
    ))

    flow = OrderFlowSummary(
        condition_id=condition_id,
        question=question,
        total_volume=round(total_volume, 2),
        large_trades=large_trades,
        unique_wallets=len(wallets),
        yes_pressure=round(yes_pressure, 3),
        no_pressure=round(no_pressure, 3),
        whale_count=whale_count,
        whale_total_usd=round(whale_total, 2),
        anomaly_score=round(anomaly_score, 3),
    )
    save_flow(flow)
    return flow


# ─── Full Scan ─────────────────────────────────────────────────────────────────
def scan_onchain(markets: list[dict] = None) -> dict:
    """
    Full on-chain scan: analyze order flow + whale activity for active markets.
    markets: list of market dicts from gamma-api (optional, fetches if not provided).
    Returns summary dict for dashboard.
    """
    if not markets:
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.get(
                    "https://gamma-api.polymarket.com/markets",
                    params={
                        "limit": 50,
                        "active": "true",
                        "closed": "false",
                        "order": "volume",
                        "ascending": "false",
                    }
                )
                resp.raise_for_status()
                markets = resp.json()
        except Exception as e:
            log.warning(f"[onchain] market fetch failed: {e}")
            return {"error": str(e)}

    all_alerts = []
    all_flows = []
    high_anomaly_markets = []

    for m in markets:
        cid = m.get("conditionId", "")
        question = m.get("question", "")
        if not cid:
            continue

        # Whale detection
        alerts = detect_whale_activity(cid, question)
        all_alerts.extend(alerts)

        # Order flow analysis (only for top volume markets to limit API calls)
        vol = m.get("volume24hr", 0) or 0
        if vol > 10000:
            flow = analyze_order_flow(cid, question)
            all_flows.append(flow)
            if flow.anomaly_score >= 0.6:
                high_anomaly_markets.append({
                    "question": question,
                    "condition_id": cid,
                    "anomaly_score": flow.anomaly_score,
                    "whale_count": flow.whale_count,
                    "whale_total": flow.whale_total_usd,
                    "yes_pressure": flow.yes_pressure,
                    "volume": flow.total_volume,
                })

        time.sleep(0.3)  # rate limit

    summary = {
        "markets_scanned": len(markets),
        "alerts_generated": len(all_alerts),
        "flows_analyzed": len(all_flows),
        "high_anomaly_markets": len(high_anomaly_markets),
        "top_anomalies": sorted(high_anomaly_markets,
                                key=lambda x: x["anomaly_score"], reverse=True)[:10],
        "recent_alerts": get_recent_alerts(20),
    }

    log.info(f"[onchain] Scanned {len(markets)} markets: "
             f"{len(all_alerts)} alerts, {len(high_anomaly_markets)} high-anomaly")

    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
    result = scan_onchain()
    print(json.dumps(result, indent=2, default=str))