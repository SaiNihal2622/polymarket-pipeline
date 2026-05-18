"""
Market Maker — HFT Spread Capture with Paired Cost Protocol

Implements the "Bone Reaper" and "Ohanism" strategies from Poly Research Robotics:
1. Paired Cost Protocol: Buy YES + NO for < $1.00 combined = risk-free spread profit
2. Bid-Ask Spread Capture: Place limit orders on both sides simultaneously
3. Retail Slippage Harvesting: Micro-trades targeting mispriced markets
4. Internal Pricing Model: Compare our fair value vs Polymarket price for edge detection

Uses existing Polymarket CLOB API (py_clob_client) for order placement.
Operates in demo mode — logs opportunities and simulated fills.
"""

import os
import json
import time
import sqlite3
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import datetime, timezone

import httpx

from config import DB_FILE, get_clob_client

log = logging.getLogger("market_maker")

# ─── Config ────────────────────────────────────────────────────────────────────
MIN_PAIRED_DISCOUNT = float(os.getenv("MM_MIN_PAIRED_DISCOUNT", "0.02"))
MM_MAX_POSITION_USD = float(os.getenv("MM_MAX_POSITION_USD", "10.0"))
MM_TRADE_SIZE_USD = float(os.getenv("MM_MM_TRADE_SIZE_USD", "5.0"))
MM_SPREAD_THRESHOLD = float(os.getenv("MM_SPREAD_THRESHOLD", "0.03"))
MM_CHECK_INTERVAL = int(os.getenv("MM_CHECK_INTERVAL", "30"))
MM_ENABLED = os.getenv("MM_ENABLED", "true").lower() == "true"
MM_TARGET_MIN_VOLUME = float(os.getenv("MM_TARGET_MIN_VOLUME", "50000"))
MM_TARGET_CATEGORIES = os.getenv("MM_TARGET_CATEGORIES", "crypto,politics,ai,sports").split(",")


@dataclass
class SpreadOpportunity:
    """A detected spread capture opportunity."""
    condition_id: str
    question: str
    yes_bid: float
    yes_ask: float
    no_bid: float
    no_ask: float
    paired_cost: float
    spread: float
    confidence: float
    volume_24h: float
    category: str = ""
    strategy: str = "spread_capture"
    timestamp: float = field(default_factory=time.time)

    @property
    def is_profitable(self) -> bool:
        return self.paired_cost < 1.0 and self.spread >= MM_SPREAD_THRESHOLD

    @property
    def expected_profit_per_pair(self) -> float:
        return max(0, 1.0 - self.paired_cost)


@dataclass
class MakerTrade:
    """A simulated or real market maker trade."""
    condition_id: str
    side: str  # "yes" or "no"
    price: float
    size_usd: float
    order_type: str  # "limit" or "market"
    strategy: str
    paired_cost: Optional[float] = None
    spread: Optional[float] = None
    status: str = "simulated"
    fill_price: Optional[float] = None
    pnl: Optional[float] = None
    timestamp: float = field(default_factory=time.time)


# ─── Database ──────────────────────────────────────────────────────────────────
def _init_maker_table():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mm_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            condition_id TEXT NOT NULL,
            side TEXT NOT NULL,
            price REAL NOT NULL,
            size_usd REAL NOT NULL,
            order_type TEXT NOT NULL,
            strategy TEXT NOT NULL,
            paired_cost REAL,
            spread REAL,
            status TEXT NOT NULL DEFAULT 'simulated',
            fill_price REAL,
            pnl REAL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mm_opportunities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            condition_id TEXT NOT NULL,
            question TEXT,
            yes_bid REAL,
            yes_ask REAL,
            no_bid REAL,
            no_ask REAL,
            paired_cost REAL,
            spread REAL,
            confidence REAL,
            volume_24h REAL,
            category TEXT,
            strategy TEXT,
            captured INTEGER DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


def save_opportunity(opp: SpreadOpportunity):
    _init_maker_table()
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        INSERT INTO mm_opportunities 
        (condition_id, question, yes_bid, yes_ask, no_bid, no_ask, 
         paired_cost, spread, confidence, volume_24h, category, strategy)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (opp.condition_id, opp.question, opp.yes_bid, opp.yes_ask,
          opp.no_bid, opp.no_ask, opp.paired_cost, opp.spread,
          opp.confidence, opp.volume_24h, opp.category, opp.strategy))
    conn.commit()
    conn.close()


def save_trade(trade: MakerTrade):
    _init_maker_table()
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        INSERT INTO mm_trades
        (condition_id, side, price, size_usd, order_type, strategy,
         paired_cost, spread, status, fill_price, pnl)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (trade.condition_id, trade.side, trade.price, trade.size_usd,
          trade.order_type, trade.strategy, trade.paired_cost, trade.spread,
          trade.status, trade.fill_price, trade.pnl))
    conn.commit()
    conn.close()


def get_maker_stats() -> dict:
    _init_maker_table()
    conn = sqlite3.connect(DB_FILE)
    row = conn.execute("""
        SELECT 
            COUNT(*) as total_trades,
            SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses,
            COALESCE(SUM(pnl), 0) as total_pnl,
            COALESCE(AVG(spread), 0) as avg_spread,
            COALESCE(AVG(paired_cost), 0) as avg_paired_cost,
            COUNT(DISTINCT condition_id) as markets_traded
        FROM mm_trades
    """).fetchone()
    opp_count = conn.execute("SELECT COUNT(*) FROM mm_opportunities").fetchone()[0]
    conn.close()
    
    return {
        "total_trades": row[0] or 0,
        "wins": row[1] or 0,
        "losses": row[2] or 0,
        "total_pnl": round(row[3] or 0, 4),
        "avg_spread": round(row[4] or 0, 4),
        "avg_paired_cost": round(row[5] or 0, 4),
        "markets_traded": row[6] or 0,
        "opportunities_found": opp_count,
    }


# ─── Orderbook Fetching ────────────────────────────────────────────────────────
def fetch_orderbook(token_id: str) -> dict:
    """Fetch CLOB orderbook for a token. Returns {bids: [{price, size}], asks: [{price, size}]}."""
    try:
        clob = get_clob_client()
        book = clob.get_order_book(token_id)
        bids = [{"price": float(l.price), "size": float(l.size)} for l in (book.bids or [])]
        asks = [{"price": float(l.price), "size": float(l.size)} for l in (book.asks or [])]
        return {"bids": sorted(bids, key=lambda x: -x["price"]),
                "asks": sorted(asks, key=lambda x: x["price"])}
    except Exception as e:
        log.warning(f"[mm] orderbook fetch failed for {token_id[:12]}…: {e}")
        return {"bids": [], "asks": []}


def fetch_markets_for_making(limit: int = 100) -> list[dict]:
    """Fetch active markets suitable for market making (high volume, 5min/15min/1h crypto)."""
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(
                "https://gamma-api.polymarket.com/markets",
                params={
                    "limit": limit,
                    "active": "true",
                    "closed": "false",
                    "order": "volume",
                    "ascending": "false",
                }
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        log.warning(f"[mm] market fetch failed: {e}")
        return []


# ─── Strategy: Paired Cost (Bone Reaper) ───────────────────────────────────────
def check_paired_cost(market: dict) -> Optional[SpreadOpportunity]:
    """
    Bone Reaper Strategy: Buy YES + NO for < $1.00 combined.
    If the best ask for YES is 0.55 and best ask for NO is 0.40,
    paired cost = 0.95, profit = $0.05 per pair.
    """
    tokens = market.get("clobTokenIds") or market.get("tokens", [])
    if not tokens or len(tokens) < 2:
        return None

    yes_book = fetch_orderbook(tokens[0])
    no_book = fetch_orderbook(tokens[1])

    if not yes_book["asks"] or not no_book["asks"]:
        return None

    yes_best_ask = yes_book["asks"][0]["price"]
    no_best_ask = no_book["asks"][0]["price"]
    yes_best_bid = yes_book["bids"][0]["price"] if yes_book["bids"] else 0
    no_best_bid = no_book["bids"][0]["price"] if no_book["bids"] else 0

    paired_cost = yes_best_ask + no_best_ask
    spread = (yes_best_ask - yes_best_bid + no_best_ask - no_best_bid) / 2
    discount = 1.0 - paired_cost

    if discount >= MIN_PAIRED_DISCOUNT:
        return SpreadOpportunity(
            condition_id=market.get("conditionId", ""),
            question=market.get("question", ""),
            yes_bid=yes_best_bid,
            yes_ask=yes_best_ask,
            no_bid=no_best_bid,
            no_ask=no_best_ask,
            paired_cost=round(paired_cost, 4),
            spread=round(spread, 4),
            confidence=min(1.0, discount / 0.10),
            volume_24h=market.get("volume24hr", 0) or 0,
            strategy="paired_cost",
        )
    return None


# ─── Strategy: Spread Capture (Ohanism-lite) ───────────────────────────────────
def check_spread_capture(market: dict) -> Optional[SpreadOpportunity]:
    """
    Spread Capture: Place limit orders on both sides to capture bid-ask spread.
    Buy below mid-price, sell above mid-price.
    Only targets markets with sufficient spread and volume.
    """
    tokens = market.get("clobTokenIds") or market.get("tokens", [])
    if not tokens:
        return None

    yes_book = fetch_orderbook(tokens[0])

    if not yes_book["bids"] or not yes_book["asks"]:
        return None

    yes_best_bid = yes_book["bids"][0]["price"]
    yes_best_ask = yes_book["asks"][0]["price"]
    spread = yes_best_ask - yes_best_bid

    if spread < MM_SPREAD_THRESHOLD:
        return None

    mid = (yes_best_bid + yes_best_ask) / 2

    no_book = fetch_orderbook(tokens[1]) if len(tokens) > 1 else {"bids": [], "asks": []}
    no_best_bid = no_book["bids"][0]["price"] if no_book["bids"] else 0
    no_best_ask = no_book["asks"][0]["price"] if no_book["asks"] else 0

    paired_cost = yes_best_ask + no_best_ask if no_best_ask > 0 else 1.0

    return SpreadOpportunity(
        condition_id=market.get("conditionId", ""),
        question=market.get("question", ""),
        yes_bid=yes_best_bid,
        yes_ask=yes_best_ask,
        no_bid=no_best_bid,
        no_ask=no_best_ask,
        paired_cost=round(paired_cost, 4),
        spread=round(spread, 4),
        confidence=min(1.0, spread / 0.10),
        volume_24h=market.get("volume24hr", 0) or 0,
        strategy="spread_capture",
    )


# ─── Strategy: Internal Pricing Model (Edge Detection) ─────────────────────────
def check_model_edge(market: dict, our_probability: float) -> Optional[SpreadOpportunity]:
    """
    Compare our internal probability estimate vs Polymarket price.
    If our model says 0.70 YES but Polymarket has YES at 0.55, that's a 15% edge.
    Dynamically scales position size by edge magnitude.
    """
    tokens = market.get("clobTokenIds") or market.get("tokens", [])
    if not tokens:
        return None

    yes_book = fetch_orderbook(tokens[0])
    if not yes_book["asks"]:
        return None

    market_yes = yes_book["asks"][0]["price"]
    edge = abs(our_probability - market_yes)

    if edge < 0.05:
        return None

    no_book = fetch_orderbook(tokens[1]) if len(tokens) > 1 else {"bids": [], "asks": []}
    no_best_ask = no_book["asks"][0]["price"] if no_book["asks"] else 0
    paired_cost = market_yes + no_best_ask if no_best_ask > 0 else 1.0

    return SpreadOpportunity(
        condition_id=market.get("conditionId", ""),
        question=market.get("question", ""),
        yes_bid=yes_book["bids"][0]["price"] if yes_book["bids"] else 0,
        yes_ask=market_yes,
        no_bid=no_book["bids"][0]["price"] if no_book["bids"] else 0,
        no_ask=no_best_ask,
        paired_cost=round(paired_cost, 4),
        spread=round(edge, 4),
        confidence=min(1.0, edge / 0.20),
        volume_24h=market.get("volume24hr", 0) or 0,
        strategy="model_edge",
    )


# ─── Execution (Demo Mode) ────────────────────────────────────────────────────
def simulate_fill(opp: SpreadOpportunity, size_usd: float = None) -> list[MakerTrade]:
    """
    Simulate executing a paired trade. In demo mode, we assume fill at ask price.
    Returns list of trades (YES buy + NO buy for paired_cost, or single spread capture).
    """
    size = size_usd or MM_TRADE_SIZE_USD
    trades = []

    if opp.strategy == "paired_cost":
        # Buy YES and NO simultaneously
        yes_trade = MakerTrade(
            condition_id=opp.condition_id,
            side="yes",
            price=opp.yes_ask,
            size_usd=size / 2,
            order_type="limit",
            strategy=opp.strategy,
            paired_cost=opp.paired_cost,
            spread=opp.spread,
            status="simulated",
            fill_price=opp.yes_ask,
            pnl=round(opp.expected_profit_per_pair * (size / 2), 4),
        )
        no_trade = MakerTrade(
            condition_id=opp.condition_id,
            side="no",
            price=opp.no_ask,
            size_usd=size / 2,
            order_type="limit",
            strategy=opp.strategy,
            paired_cost=opp.paired_cost,
            spread=opp.spread,
            status="simulated",
            fill_price=opp.no_ask,
            pnl=round(opp.expected_profit_per_pair * (size / 2), 4),
        )
        trades = [yes_trade, no_trade]

    elif opp.strategy == "spread_capture":
        # Place limit buy at bid, limit sell at ask
        buy_trade = MakerTrade(
            condition_id=opp.condition_id,
            side="yes",
            price=opp.yes_bid,
            size_usd=size,
            order_type="limit",
            strategy=opp.strategy,
            spread=opp.spread,
            status="simulated",
            fill_price=opp.yes_bid,
            pnl=round(opp.spread * size, 4),
        )
        trades = [buy_trade]

    elif opp.strategy == "model_edge":
        direction = "yes" if opp.confidence > 0.5 else "no"
        buy_price = opp.yes_ask if direction == "yes" else opp.no_ask
        trades = [MakerTrade(
            condition_id=opp.condition_id,
            side=direction,
            price=buy_price,
            size_usd=size,
            order_type="limit",
            strategy=opp.strategy,
            paired_cost=opp.paired_cost,
            spread=opp.spread,
            status="simulated",
            fill_price=buy_price,
            pnl=round(opp.spread * size, 4),
        )]

    for t in trades:
        save_trade(t)

    return trades


# ─── Main Scan Loop ────────────────────────────────────────────────────────────
def scan_for_opportunities(our_probabilities: dict = None) -> list[SpreadOpportunity]:
    """
    Scan all target markets for spread opportunities.
    our_probabilities: {condition_id: float} — internal model estimates (optional).
    Returns list of profitable opportunities.
    """
    if not MM_ENABLED:
        return []

    markets = fetch_markets_for_making()
    opportunities = []

    for m in markets:
        cid = m.get("conditionId", "")

        # Strategy 1: Paired Cost (Bone Reaper)
        opp = check_paired_cost(m)
        if opp and opp.is_profitable:
            save_opportunity(opp)
            opportunities.append(opp)
            log.info(f"[mm] PAIRED COST: {opp.question[:60]}… "
                     f"cost={opp.paired_cost:.3f} profit=${opp.expected_profit_per_pair:.3f}")
            continue

        # Strategy 2: Spread Capture
        opp = check_spread_capture(m)
        if opp and opp.is_profitable:
            save_opportunity(opp)
            opportunities.append(opp)
            log.info(f"[mm] SPREAD: {opp.question[:60]}… spread={opp.spread:.3f}")

        # Strategy 3: Model Edge (if we have internal estimates)
        if our_probabilities and cid in our_probabilities:
            opp = check_model_edge(m, our_probabilities[cid])
            if opp:
                save_opportunity(opp)
                opportunities.append(opp)
                log.info(f"[mm] MODEL EDGE: {opp.question[:60]}… edge={opp.spread:.3f}")

    return opportunities


def run_maker_cycle(our_probabilities: dict = None) -> dict:
    """Run one full market making cycle. Returns summary."""
    log.info("[mm] ═══ MARKET MAKER CYCLE ═══")
    opps = scan_for_opportunities(our_probabilities)

    total_pairs = sum(1 for o in opps if o.strategy == "paired_cost")
    total_spread = sum(1 for o in opps if o.strategy == "spread_capture")
    total_edge = sum(1 for o in opps if o.strategy == "model_edge")

    # Simulate fills for profitable opportunities
    all_trades = []
    for opp in opps:
        if opp.is_profitable:
            trades = simulate_fill(opp)
            all_trades.extend(trades)

    stats = get_maker_stats()

    log.info(f"[mm] Found {len(opps)} opportunities: "
             f"{total_pairs} paired, {total_spread} spread, {total_edge} edge")
    log.info(f"[mm] Stats: {stats['total_trades']} trades, "
             f"PnL=${stats['total_pnl']:.2f}, avg_spread={stats['avg_spread']:.4f}")

    return {
        "opportunities": len(opps),
        "paired_cost": total_pairs,
        "spread_capture": total_spread,
        "model_edge": total_edge,
        "trades_executed": len(all_trades),
        "stats": stats,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
    result = run_maker_cycle()
    print(json.dumps(result, indent=2, default=str))