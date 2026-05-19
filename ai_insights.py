"""
AI Insights — Real-Time Directional Probability Module

Inspired by Poly Sniper AI's "AI Insights Module":
1. Generates directional probability percentages for markets
2. Combines news sentiment, whale signals, order flow, and market price
3. Outputs confidence-adjusted signals: "93% DOWN", "82% BULLISH"
4. Feeds into the main pipeline's scoring system and dashboard

Uses existing classifier/scorer infrastructure for LLM calls.
"""

import os
import json
import time
import sqlite3
import logging
from dataclasses import dataclass, field
from typing import Optional

import httpx

from config import DB_PATH as DB_FILE, MIMO_API_KEY as MIMO_KEY, MIMO_BASE_URL as MIMO_BASE, MIMO_MODEL

USE_MIMO = bool(MIMO_KEY)

log = logging.getLogger("ai_insights")


@dataclass
class MarketInsight:
    """AI-generated directional insight for a market."""
    condition_id: str
    question: str
    # Price data
    current_yes_price: float = 0.0
    current_no_price: float = 0.0
    # AI analysis
    direction: str = ""  # "bullish", "bearish", "neutral"
    ai_probability: float = 0.5  # 0-1, our estimated probability
    confidence: float = 0.0  # 0-1
    # Signal components
    news_sentiment: float = 0.0  # -1 to 1
    whale_signal: float = 0.0  # -1 to 1
    order_flow_signal: float = 0.0  # -1 to 1
    price_momentum: float = 0.0  # -1 to 1
    # Composite
    composite_score: float = 0.0  # -1 to 1
    edge: float = 0.0  # difference between our estimate and market price
    # Meta
    reasoning: str = ""
    timeframe: str = "24h"
    risk_level: str = "medium"  # low, medium, high
    timestamp: float = field(default_factory=time.time)


# ─── Database ──────────────────────────────────────────────────────────────────
def _init_insights_table():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ai_insights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            condition_id TEXT NOT NULL,
            question TEXT DEFAULT '',
            current_yes_price REAL DEFAULT 0,
            current_no_price REAL DEFAULT 0,
            direction TEXT DEFAULT '',
            ai_probability REAL DEFAULT 0.5,
            confidence REAL DEFAULT 0,
            news_sentiment REAL DEFAULT 0,
            whale_signal REAL DEFAULT 0,
            order_flow_signal REAL DEFAULT 0,
            price_momentum REAL DEFAULT 0,
            composite_score REAL DEFAULT 0,
            edge REAL DEFAULT 0,
            reasoning TEXT DEFAULT '',
            timeframe TEXT DEFAULT '24h',
            risk_level TEXT DEFAULT 'medium',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


def save_insight(insight: MarketInsight):
    _init_insights_table()
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        INSERT INTO ai_insights
        (condition_id, question, current_yes_price, current_no_price,
         direction, ai_probability, confidence,
         news_sentiment, whale_signal, order_flow_signal, price_momentum,
         composite_score, edge, reasoning, timeframe, risk_level)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (insight.condition_id, insight.question,
          insight.current_yes_price, insight.current_no_price,
          insight.direction, insight.ai_probability, insight.confidence,
          insight.news_sentiment, insight.whale_signal,
          insight.order_flow_signal, insight.price_momentum,
          insight.composite_score, insight.edge,
          insight.reasoning, insight.timeframe, insight.risk_level))
    conn.commit()
    conn.close()


def get_latest_insights(limit: int = 50) -> list[dict]:
    _init_insights_table()
    conn = sqlite3.connect(DB_FILE)
    rows = conn.execute("""
        SELECT condition_id, question, current_yes_price, current_no_price,
               direction, ai_probability, confidence,
               news_sentiment, whale_signal, order_flow_signal, price_momentum,
               composite_score, edge, reasoning, timeframe, risk_level, created_at
        FROM ai_insights
        ORDER BY id DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()

    # Deduplicate by condition_id — keep latest for each
    seen = {}
    for r in rows:
        cid = r[0]
        if cid not in seen:
            seen[cid] = {
                "condition_id": r[0], "question": r[1],
                "yes_price": r[2], "no_price": r[3],
                "direction": r[4], "ai_probability": r[5],
                "confidence": r[6],
                "news_sentiment": r[7], "whale_signal": r[8],
                "order_flow_signal": r[9], "price_momentum": r[10],
                "composite_score": r[11], "edge": r[12],
                "reasoning": r[13], "timeframe": r[14],
                "risk_level": r[15], "time": r[16],
            }
    return list(seen.values())


def get_high_signal_insights(min_confidence: float = 0.6) -> list[dict]:
    """Get insights with high confidence for actionable signals."""
    all_insights = get_latest_insights(200)
    return [i for i in all_insights if i["confidence"] >= min_confidence]


# ─── LLM Analysis ──────────────────────────────────────────────────────────────
def _call_llm(prompt: str) -> str:
    """Call the configured LLM for analysis."""
    if not USE_MIMO:
        return ""

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{MIMO_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {MIMO_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": MIMO_MODEL,
                    "messages": [
                        {"role": "system", "content": (
                            "You are a prediction market analyst. "
                            "Return ONLY valid JSON. No markdown, no explanation."
                        )},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.2,
                    "max_tokens": 300,
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log.warning(f"[ai_insights] LLM call failed: {e}")
        return ""


def _parse_json(text: str) -> dict:
    """Extract JSON from LLM response."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        import re
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
    return {}


# ─── Signal Generation ─────────────────────────────────────────────────────────
def analyze_market_insight(
    question: str,
    yes_price: float,
    no_price: float,
    news_headlines: list[str] = None,
    whale_signal: float = 0.0,
    order_flow_signal: float = 0.0,
    volume_24h: float = 0.0,
) -> MarketInsight:
    """
    Generate a directional insight for a market.
    Combines LLM analysis with whale/orderflow signals.

    Returns MarketInsight with direction, probability, confidence, and reasoning.
    """
    news_text = ""
    if news_headlines:
        news_text = "\n".join(f"- {h}" for h in news_headlines[:15])

    prompt = f"""Analyze this prediction market and provide a directional assessment.

MARKET: "{question}"
CURRENT YES PRICE: ${yes_price:.2f} ({yes_price*100:.0f}%)
CURRENT NO PRICE: ${no_price:.2f} ({no_price*100:.0f}%)
24H VOLUME: ${volume_24h:,.0f}

RECENT NEWS:
{news_text or "No recent news available."}

WHALE SIGNAL: {"bullish" if whale_signal > 0.2 else "bearish" if whale_signal < -0.2 else "neutral"} ({whale_signal:+.2f})
ORDER FLOW: {"bullish" if order_flow_signal > 0.2 else "bearish" if order_flow_signal < -0.2 else "neutral"} ({order_flow_signal:+.2f})

Respond with JSON only:
{{
    "direction": "bullish" or "bearish" or "neutral",
    "probability": <float 0-1, your estimated probability of YES>,
    "confidence": <float 0-1, how confident you are>,
    "news_sentiment": <float -1 to 1>,
    "reasoning": "<1-2 sentence explanation>",
    "risk_level": "low" or "medium" or "high"
}}"""

    raw = _call_llm(prompt)
    data = _parse_json(raw)

    if not data:
        # Fallback: derive from price + whale signal
        prob = yes_price
        if abs(whale_signal) > 0.3:
            prob = prob + whale_signal * 0.1
        prob = max(0.01, min(0.99, prob))
        direction = "bullish" if prob > 0.55 else "bearish" if prob < 0.45 else "neutral"
        return MarketInsight(
            direction=direction,
            ai_probability=prob,
            confidence=0.3,
            news_sentiment=0,
            whale_signal=whale_signal,
            order_flow_signal=order_flow_signal,
            composite_score=whale_signal * 0.5,
            edge=abs(prob - yes_price),
            reasoning="Fallback analysis (LLM unavailable)",
            risk_level="medium",
        )

    ai_prob = float(data.get("probability", yes_price))
    news_sent = float(data.get("news_sentiment", 0))
    conf = float(data.get("confidence", 0.5))
    direction = data.get("direction", "neutral")
    reasoning = data.get("reasoning", "")
    risk = data.get("risk_level", "medium")

    # Composite: weighted average of all signals
    composite = (
        news_sent * 0.35 +
        whale_signal * 0.25 +
        order_flow_signal * 0.20 +
        (ai_prob - 0.5) * 2 * 0.20  # normalize AI prob to -1..1
    )
    composite = max(-1, min(1, composite))

    edge = ai_prob - yes_price  # positive = YES underpriced

    insight = MarketInsight(
        current_yes_price=yes_price,
        current_no_price=no_price,
        direction=direction,
        ai_probability=round(ai_prob, 3),
        confidence=round(conf, 3),
        news_sentiment=round(news_sent, 3),
        whale_signal=round(whale_signal, 3),
        order_flow_signal=round(order_flow_signal, 3),
        price_momentum=round((ai_prob - 0.5) * 2, 3),
        composite_score=round(composite, 3),
        edge=round(edge, 3),
        reasoning=reasoning,
        risk_level=risk,
    )

    return insight


def generate_batch_insights(
    markets: list[dict],
    news_map: dict = None,
    whale_signals: dict = None,
    flow_signals: dict = None,
) -> list[MarketInsight]:
    """
    Generate insights for a batch of markets.
    markets: list of market dicts from gamma-api
    news_map: {condition_id: [headlines]}
    whale_signals: {condition_id: float}
    flow_signals: {condition_id: float}
    """
    news_map = news_map or {}
    whale_signals = whale_signals or {}
    flow_signals = flow_signals or {}

    insights = []
    for m in markets:
        cid = m.get("conditionId", "")
        question = m.get("question", "")
        tokens = m.get("clobTokenIds") or m.get("tokens", [])
        yes_price = m.get("outcomePrices", [0.5, 0.5])
        if isinstance(yes_price, str):
            try:
                yes_price = json.loads(yes_price)
            except:
                yes_price = [0.5, 0.5]
        yes_p = float(yes_price[0]) if yes_price else 0.5
        no_p = float(yes_price[1]) if len(yes_price) > 1 else 1 - yes_p

        insight = analyze_market_insight(
            question=question,
            yes_price=yes_p,
            no_price=no_p,
            news_headlines=news_map.get(cid, []),
            whale_signal=whale_signals.get(cid, 0),
            order_flow_signal=flow_signals.get(cid, 0),
            volume_24h=m.get("volume24hr", 0) or 0,
        )
        insight.condition_id = cid
        insight.question = question
        save_insight(insight)
        insights.append(insight)

    return insights


# ─── Dashboard Summary ─────────────────────────────────────────────────────────
def get_insights_summary() -> dict:
    """Get summary for dashboard display."""
    insights = get_latest_insights(200)

    if not insights:
        return {"total": 0, "bullish": 0, "bearish": 0, "neutral": 0, "top_signals": []}

    bullish = [i for i in insights if i["direction"] == "bullish"]
    bearish = [i for i in insights if i["direction"] == "bearish"]
    neutral = [i for i in insights if i["direction"] == "neutral"]

    # Top signals by absolute edge
    top_signals = sorted(insights, key=lambda x: abs(x["edge"]), reverse=True)[:10]

    return {
        "total": len(insights),
        "bullish": len(bullish),
        "bearish": len(bearish),
        "neutral": len(neutral),
        "avg_confidence": round(sum(i["confidence"] for i in insights) / max(1, len(insights)), 3),
        "avg_edge": round(sum(abs(i["edge"]) for i in insights) / max(1, len(insights)), 3),
        "top_signals": [
            {
                "question": s["question"][:80],
                "direction": s["direction"],
                "ai_probability": s["ai_probability"],
                "yes_price": s["yes_price"],
                "edge": s["edge"],
                "confidence": s["confidence"],
                "composite_score": s["composite_score"],
                "risk_level": s["risk_level"],
                "reasoning": s["reasoning"][:120],
            }
            for s in top_signals
        ],
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
    # Test with a sample market
    insight = analyze_market_insight(
        question="Will Bitcoin be above $100K by end of May 2026?",
        yes_price=0.45,
        no_price=0.55,
        news_headlines=["Bitcoin surges to $98K amid ETF inflows", "Crypto market cap hits $3.5T"],
        whale_signal=0.3,
        order_flow_signal=0.2,
    )
    print(json.dumps({
        "direction": insight.direction,
        "probability": insight.ai_probability,
        "confidence": insight.confidence,
        "edge": insight.edge,
        "composite": insight.composite_score,
        "reasoning": insight.reasoning,
    }, indent=2))