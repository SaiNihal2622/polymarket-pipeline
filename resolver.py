#!/usr/bin/env python3
"""
resolver.py — Resolves demo trades via multiple strategies:

Strategy 1 (PRIMARY): Gamma REST endpoint per trade.
  GET gamma-api.polymarket.com/markets?slug=<conditionId>
  Parse outcomePrices to get final result.

Strategy 2 (SECONDARY): CLOB API per-trade.
  fetch_book(token_id) → if best_bid > 0.95 → YES resolved
                       → if best_ask < 0.05 → NO resolved

Strategy 3 (TERTIARY): Bulk Gamma closed-market scan + question text match.
  Scans 500 closed markets, matches by question text (fuzzy).

Strategy 4 (FALLBACK): MiMo AI search-based resolution.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import time as _time
from datetime import datetime, timezone
from pathlib import Path

from difflib import SequenceMatcher

import httpx
try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:
    urllib3 = None

log = logging.getLogger(__name__)

# MCP client for enhanced market resolution
try:
    import poly_mcp_client as mcp
except ImportError:
    mcp = None

_db_env = os.getenv("DB_PATH", "")
if _db_env:
    DB_PATH = Path(_db_env)
else:
    # Use same path as logger.py: /data/trades.db on Railway, ./trades.db locally
    _railway_volume = Path("/data")
    if _railway_volume.exists():
        DB_PATH = _railway_volume / "trades.db"
    else:
        DB_PATH = Path(__file__).parent / "trades.db"
GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API  = "https://clob.polymarket.com"
DATA_API  = "https://data-api.polymarket.com"


# ── DB helpers ──────────────────────────────────────────────────────────────

def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def get_pending_demo_trades() -> list[dict]:
    conn = _conn()
    rows = conn.execute("""
        SELECT t.id, t.market_id, t.market_question, t.side, t.amount_usd,
               t.claude_score, t.market_price, t.edge, t.created_at, t.token_id
        FROM trades t
        LEFT JOIN outcomes o ON t.id = o.trade_id
        WHERE t.status IN ('demo', 'dry_run')
          AND o.id IS NULL
          AND t.market_id != ''
        ORDER BY t.created_at ASC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _get_token_id_for_trade(market_id: str) -> str | None:
    try:
        conn = _conn()
        cols = {r[1] for r in conn.execute("PRAGMA table_info(trades)").fetchall()}
        if "token_id" not in cols:
            conn.close()
            return None
        row = conn.execute(
            "SELECT token_id FROM trades WHERE market_id=? AND token_id IS NOT NULL LIMIT 1",
            (market_id,)
        ).fetchone()
        conn.close()
        return row["token_id"] if row else None
    except Exception:
        return None


# ── Parse outcome from Gamma market dict ────────────────────────────────────

def _parse_outcome(m: dict) -> float | None:
    """Extract result from Gamma market dict. Returns 1.0 (YES) / 0.0 (NO) / None."""
    # Check outcomePrices first (most reliable)
    outcome_prices_raw = m.get("outcomePrices", "")
    if outcome_prices_raw:
        try:
            prices = json.loads(outcome_prices_raw) if isinstance(outcome_prices_raw, str) else outcome_prices_raw
            if len(prices) >= 2:
                yes_price = float(prices[0])
                no_price  = float(prices[1])
                if yes_price >= 0.85:   return 1.0
                if no_price  >= 0.85:   return 0.0
        except (json.JSONDecodeError, ValueError):
            pass

    # Check resolutionPrice
    res_price = m.get("resolutionPrice")
    if res_price is not None:
        try:
            rp = float(res_price)
            if rp >= 0.90: return 1.0
            if rp <= 0.10: return 0.0
        except (ValueError, TypeError):
            pass

    # Check resolvedOutcome field (some Gamma markets have this)
    resolved_outcome = m.get("resolvedOutcome")
    if resolved_outcome:
        ro = str(resolved_outcome).strip().lower()
        if ro in ("yes", "true", "1"): return 1.0
        if ro in ("no", "false", "0"): return 0.0

    # Check if market is closed and has clear winner via outcomes array
    outcomes = m.get("outcomes", "")
    if outcomes:
        try:
            outs = json.loads(outcomes) if isinstance(outcomes, str) else outcomes
            if isinstance(outs, list) and len(outs) >= 2:
                # Sometimes outcomes contain the resolution directly
                pass
        except Exception:
            pass

    return None


# ── Strategy 1: Gamma REST per-trade (MOST RELIABLE) ───────────────────────

def _resolve_via_gamma_slug(trade: dict) -> float | None:
    """
    Look up market on Gamma by slug (conditionId) or question text.
    This is the MOST reliable method.
    """
    question = trade.get("market_question", "")
    market_id = trade.get("market_id", "")
    token_id = trade.get("token_id", "")
    # End-date guard: only skip if market end is MORE than 24h away.
    # Many markets resolve early, so we check Gamma regardless unless
    # the end date is far in the future.
    end_str = trade.get("end_date_iso") or trade.get("market_end_date") or ""
    if end_str:
        try:
            from datetime import datetime as _dt2, timezone as _tz2
            end_dt = _dt2.fromisoformat(end_str.replace("Z", "+00:00"))
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=_tz2.utc)
            now = _dt2.now(_tz2.utc)
            remaining_hours = (end_dt - now).total_seconds() / 3600
            if remaining_hours > 24:
                log.info(f"[resolver] Skipping trade — market ends in {remaining_hours:.1f}h: {question[:50]}")
                return None
        except Exception:
            pass

    if not market_id and not question:
        return None
    
    # Try 1: Direct slug lookup (conditionId as slug)
    if market_id:
        try:
            r = httpx.get(f"{GAMMA_API}/markets",
                params={"slug": market_id, "limit": 1},
                timeout=10, verify=False)
            if r.status_code == 200:
                data = r.json()
                items = data if isinstance(data, list) else data.get("data", [])
                for m in items:
                    result = _parse_outcome(m)
                    if result is not None:
                        return result
        except Exception:
            pass

    # Try 2: conditionId filter
    if market_id:
        for param_name in ["conditionId", "condition_id"]:
            try:
                r = httpx.get(f"{GAMMA_API}/markets",
                    params={param_name: market_id, "limit": 1},
                    timeout=10, verify=False)
                if r.status_code == 200:
                    data = r.json()
                    items = data if isinstance(data, list) else data.get("data", [])
                    for m in items:
                        m_cid = m.get("conditionId") or m.get("id") or ""
                        if m_cid == market_id:
                            result = _parse_outcome(m)
                            if result is not None:
                                return result
            except Exception:
                pass

    # Try 2.5: Look up by clob_token_ids (our stored token_id)
    if token_id and len(str(token_id)) > 50:
        try:
            r = httpx.get(f"{GAMMA_API}/markets",
                params={"clob_token_ids": f'["{token_id}"]', "limit": 5},
                timeout=10, verify=False)
            if r.status_code == 200:
                data = r.json()
                items = data if isinstance(data, list) else data.get("data", [])
                for m in items:
                    result = _parse_outcome(m)
                    if result is not None:
                        return result
        except Exception:
            pass

    # Try 3: Search by question text (closed=true) — lower threshold to 0.60
    if question:
        try:
            r = httpx.get(f"{GAMMA_API}/markets",
                params={"question": question[:100], "limit": 5, "closed": "true"},
                timeout=10, verify=False)
            if r.status_code == 200:
                data = r.json()
                items = data if isinstance(data, list) else data.get("data", [])
                for m in items:
                    mq = (m.get("question") or "").strip()
                    if _fuzzy_match(mq, question, threshold=0.60):
                        result = _parse_outcome(m)
                        if result is not None:
                            return result
        except Exception:
            pass

    # Try 4: Search by question text (all markets) — lower threshold
    if question:
        try:
            r = httpx.get(f"{GAMMA_API}/markets",
                params={"question": question[:100], "limit": 5},
                timeout=10, verify=False)
            if r.status_code == 200:
                data = r.json()
                items = data if isinstance(data, list) else data.get("data", [])
                for m in items:
                    mq = (m.get("question") or "").strip()
                    if _fuzzy_match(mq, question, threshold=0.60):
                        result = _parse_outcome(m)
                        if result is not None:
                            return result
        except Exception:
            pass

    # Try 5: Keyword search — extract key terms and search Gamma broadly
    if question:
        try:
            # Extract keywords: remove common words, keep nouns/proper nouns
            stopwords = {"will", "the", "a", "an", "is", "be", "on", "in", "at", "or", "vs", "vs.", "hit", "low", "high", "week", "of", "for", "inc", "global"}
            words = re.findall(r'[a-zA-Z$]+', question)
            keywords = [w for w in words if w.lower() not in stopwords and len(w) > 2]
            
            # Try searching with top 3 keywords
            if len(keywords) >= 2:
                search_q = " ".join(keywords[:4])
                for closed_val in ["true", None]:
                    params = {"question": search_q, "limit": 10}
                    if closed_val:
                        params["closed"] = closed_val
                    r = httpx.get(f"{GAMMA_API}/markets", params=params, timeout=10, verify=False)
                    if r.status_code == 200:
                        data = r.json()
                        items = data if isinstance(data, list) else data.get("data", [])
                        best_match = None
                        best_sim = 0.0
                        for m in items:
                            mq = (m.get("question") or "").strip()
                            sim = SequenceMatcher(None, _normalize_q(question, 120), _normalize_q(mq, 120)).ratio()
                            if sim > best_sim:
                                best_sim = sim
                                best_match = m
                        if best_match and best_sim >= 0.45:
                            log.info(f"[resolver] Gamma keyword match sim={best_sim:.2f}: {best_match.get('question','')[:60]}")
                            result = _parse_outcome(best_match)
                            if result is not None:
                                return result
        except Exception:
            pass

    # Try 6: Search by individual key words from question
    if question:
        try:
            words = re.findall(r'[A-Z][a-zA-Z]+', question)  # proper nouns / capitalized
            if len(words) >= 2:
                search_q = " ".join(words[:3])
                r = httpx.get(f"{GAMMA_API}/markets",
                    params={"question": search_q, "limit": 10, "closed": "true"},
                    timeout=10, verify=False)
                if r.status_code == 200:
                    data = r.json()
                    items = data if isinstance(data, list) else data.get("data", [])
                    best_match = None
                    best_sim = 0.0
                    for m in items:
                        mq = (m.get("question") or "").strip()
                        sim = SequenceMatcher(None, _normalize_q(question, 120), _normalize_q(mq, 120)).ratio()
                        if sim > best_sim:
                            best_sim = sim
                            best_match = m
                    if best_match and best_sim >= 0.40:
                        log.info(f"[resolver] Gamma proper-noun match sim={best_sim:.2f}: {best_match.get('question','')[:60]}")
                        result = _parse_outcome(best_match)
                        if result is not None:
                            return result
        except Exception:
            pass

    # Log why we couldn't resolve
    log.info(f"[resolver] Gamma: no resolution found for '{question[:50]}' — market may not be resolved yet")
    return None


# ── Strategy 2: CLOB book prices ────────────────────────────────────────────

def _resolve_via_clob(token_id: str, timeout: int = 8) -> float | None:
    """Check CLOB book for a YES token."""
    if not token_id:
        return None
    try:
        r = httpx.get(f"{CLOB_API}/book-snapshot", params={"token_id": token_id}, timeout=timeout, verify=False)
        if r.status_code == 200:
            data = r.json()
            bids = data.get("bids", []) or []
            asks = data.get("asks", []) or []

            if not bids and not asks:
                lp = data.get("last_trade_price") or data.get("midpoint")
                if lp is not None:
                    lp = float(lp)
                    if lp >= 0.98:  return 1.0
                    if lp <= 0.02:  return 0.0
                return None

            prices: list[float] = []
            for side in (bids, asks):
                for entry in side[:5]:
                    try:
                        prices.append(float(entry.get("price", 0)))
                    except (ValueError, TypeError):
                        pass

            if not prices:
                return None

            avg_price = sum(prices) / len(prices)
            if avg_price >= 0.95:  return 1.0
            if avg_price <= 0.05:  return 0.0
            return None

        # 404 = market resolved and delisted from CLOB
        if r.status_code == 404:
            # Try CLOB /prices endpoint
            try:
                pr = httpx.get(f"{CLOB_API}/prices", params={"token_ids": token_id}, timeout=timeout, verify=False)
                if pr.status_code == 200:
                    pdata = pr.json()
                    if isinstance(pdata, dict):
                        price_str = pdata.get(token_id) or pdata.get("price")
                        if price_str is not None:
                            p = float(price_str)
                            if p >= 0.95: return 1.0
                            if p <= 0.05: return 0.0
                    elif isinstance(pdata, list) and pdata:
                        p = float(pdata[0]) if not isinstance(pdata[0], dict) else float(pdata[0].get("price", 0.5))
                        if p >= 0.95: return 1.0
                        if p <= 0.05: return 0.0
            except Exception:
                pass

            # Try Gamma lookup by clobTokenIds
            try:
                gr = httpx.get(f"{GAMMA_API}/markets",
                    params={"clob_token_ids": f'["{token_id}"]', "limit": 1},
                    timeout=timeout, verify=False)
                if gr.status_code == 200:
                    gdata = gr.json()
                    items = gdata if isinstance(gdata, list) else gdata.get("data", [])
                    for m in items:
                        result = _parse_outcome(m)
                        if result is not None:
                            return result
            except Exception:
                pass

        return None
    except Exception as e:
        log.debug(f"[resolver:clob] {token_id[:12]}: {e}")
        return None


# ── Strategy 3: Bulk Gamma closed-market scan ───────────────────────────────

_resolution_cache: dict[str, float] = {}
_cache_fetched_at: float = 0.0
_CACHE_TTL = 300


def _normalize_q(s: str, length: int = 80) -> str:
    s = s.lower().strip()
    s = re.sub(r'\s+', ' ', s)
    s = s.replace('\u2019', "'").replace('\u2018', "'")
    s = s.replace('\u2013', '-').replace('\u2014', '-')
    for suffix in ['?', '.', '!', ' - polymarket', ' | polymarket']:
        if s.endswith(suffix):
            s = s[:-len(suffix)]
    return s[:length]


def _fuzzy_match(q1: str, q2: str, threshold: float = 0.80) -> bool:
    from difflib import SequenceMatcher
    n1 = _normalize_q(q1, 120)
    n2 = _normalize_q(q2, 120)
    if n1 == n2:
        return True
    ratio = SequenceMatcher(None, n1, n2).ratio()
    return ratio >= threshold


def _refresh_bulk_cache(pending_trades: list[dict]) -> None:
    global _resolution_cache, _cache_fetched_at
    now = _time.time()
    if now - _cache_fetched_at < _CACHE_TTL:
        return

    pending_by_q: dict[str, str] = {}
    for t in pending_trades:
        raw = t.get("market_question", "")
        mid = t["market_id"]
        for ln in (80, 60, 40):
            k = _normalize_q(raw, ln)
            if k and k not in pending_by_q:
                pending_by_q[k] = mid

    matched = 0
    fetched_total = 0

    for offset in range(0, 2000, 100):
        try:
            r = httpx.get(f"{GAMMA_API}/markets",
                params={"closed": "true", "limit": 100, "offset": offset,
                        "order": "updatedAt", "ascending": "false"}, timeout=15, verify=False)
            r.raise_for_status()
            data = r.json()
            items = data if isinstance(data, list) else data.get("data", [])
            if not items:
                break
            fetched_total += len(items)
            for m in items:
                gq_full = (m.get("question") or "").lower().strip()
                result = _parse_outcome(m)
                matched_cid = None
                for ln in (80, 60, 40):
                    gq = _normalize_q(gq_full, ln)
                    if gq in pending_by_q:
                        matched_cid = pending_by_q[gq]
                        break
                if not matched_cid:
                    for t in pending_trades:
                        pq = t.get("market_question", "")
                        if _fuzzy_match(gq_full, pq, threshold=0.55):
                            matched_cid = t["market_id"]
                            break
                if matched_cid and result is not None:
                    _resolution_cache[matched_cid] = result
                    matched += 1
                for id_field in ("conditionId", "id"):
                    cid2 = m.get(id_field, "")
                    if cid2 and result is not None:
                        _resolution_cache[cid2] = result
        except Exception as e:
            log.warning(f"[resolver:bulk] offset={offset}: {e}")
            break

    _cache_fetched_at = now
    print(f"[resolver] bulk: {fetched_total} closed markets scanned, {matched} text-matched")

    # Try Gamma search by clob_token_ids for each pending trade
    for t in pending_trades[:30]:
        mid = t["market_id"]
        if mid in _resolution_cache:
            continue
        tid = t.get("token_id") or _get_token_id_for_trade(mid)
        if tid and len(str(tid)) > 50:
            try:
                r = httpx.get(f"{GAMMA_API}/markets",
                    params={"clob_token_ids": f'["{tid}"]', "limit": 3},
                    timeout=8, verify=False)
                if r.status_code == 200:
                    data = r.json()
                    items = data if isinstance(data, list) else data.get("data", [])
                    for m in items:
                        result = _parse_outcome(m)
                        if result is not None:
                            _resolution_cache[mid] = result
                            print(f"[resolver:token_bulk] #{t['id']} matched via token_id → {result}")
                            matched += 1
                            break
            except Exception:
                pass

    # Direct question-text search for each pending trade
    for t in pending_trades[:30]:
        q = t.get("market_question", "")
        mid = t["market_id"]
        if mid in _resolution_cache:
            continue
        try:
            r = httpx.get(f"{GAMMA_API}/markets",
                params={"question": q[:100], "limit": 3, "closed": "true"}, timeout=8, verify=False)
            if r.status_code == 200:
                data = r.json()
                items = data if isinstance(data, list) else data.get("data", [])
                for m in items:
                    mq = (m.get("question") or "").strip()
                    sim = SequenceMatcher(None, _normalize_q(q, 120), _normalize_q(mq, 120)).ratio()
                    if sim >= 0.55:
                        result = _parse_outcome(m)
                        if result is not None:
                            _resolution_cache[mid] = result
                            print(f"[resolver:qsearch] #{t['id']} sim={sim:.2f} matched! → {result}")
                            matched += 1
                            break
        except Exception:
            pass


# ── Strategy 4: MiMo AI search-based resolution ─────────────────────────────

def _resolve_via_search(question: str) -> float | None:
    """Search-based resolution fallback using MiMo API."""
    try:
        import config as _cfg
        prompt = f"""Determine the outcome of this prediction market: "{question}"
Is the outcome YES or NO? If it happened, answer YES. If not, answer NO. If still ongoing or unclear, answer UNCLEAR.
Return ONLY one word: YES, NO, or UNCLEAR."""

        if _cfg.MIMO_API_KEY:
            try:
                r = httpx.post(f"{_cfg.MIMO_BASE_URL}/chat/completions",
                    headers={"Authorization": f"Bearer {_cfg.MIMO_API_KEY}", "Content-Type": "application/json"},
                    json={"model": _cfg.MIMO_MODEL,
                          "messages": [{"role": "user", "content": prompt}],
                          "temperature": 0.0, "max_tokens": 10},
                    timeout=15)
                if r.status_code == 200:
                    result_text = r.json()["choices"][0]["message"]["content"].strip()
                    result_text = result_text.upper().strip()
                    if "YES" in result_text: return 1.0
                    if "NO" in result_text: return 0.0
            except Exception as e:
                log.debug(f"[resolver:search] MiMo failed: {e}")
        return None
    except Exception as e:
        log.warning(f"[resolver:search] error: {e}")
        return None


# ── Main resolution logic ────────────────────────────────────────────────────

def _resolve_via_price_expiry(trade: dict) -> float | None:
    """
    Strategy 0: If market is past its end_date and current price is extreme,
    resolve based on price. This catches markets that Polymarket closed but
    our other strategies missed.
    """
    try:
        end_str = trade.get("end_date_iso") or trade.get("market_end_date")
        if not end_str:
            return None
        from datetime import datetime as _dt, timezone as _tz
        end_dt = _dt.fromisoformat(end_str.replace("Z", "+00:00"))
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=_tz.utc)
        now = _dt.now(_tz.utc)
        # Only apply if market ended at least 2 hours ago
        if (now - end_dt).total_seconds() < 7200:
            return None

        # Fetch current market price from Gamma (use query params, NOT /markets/{id} which 422s)
        market_id = trade.get("market_id", "")
        token_id = trade.get("token_id", "")
        try:
            r = httpx.get(f"{GAMMA_API}/markets",
                params={"conditionId": market_id, "limit": 1},
                timeout=8, verify=False)
            if r.status_code == 200:
                data = r.json()
                items = data if isinstance(data, list) else data.get("data", [])
                if not items and token_id and len(str(token_id)) > 50:
                    r = httpx.get(f"{GAMMA_API}/markets",
                        params={"clob_token_ids": f'["{token_id}"]', "limit": 1},
                        timeout=8, verify=False)
                    if r.status_code == 200:
                        data = r.json()
                        items = data if isinstance(data, list) else data.get("data", [])
                for m in items:
                    outcome_prices = m.get("outcomePrices")
                    if outcome_prices:
                        prices = json.loads(outcome_prices) if isinstance(outcome_prices, str) else outcome_prices
                        yes_price = float(prices[0]) if prices else 0.5
                    else:
                        yes_price = float(m.get("bestAsk", 0.5) or 0.5)
                    # If price is extreme, market is effectively resolved
                    if yes_price >= 0.96:
                        print(f"[resolver:price_expiry] #{trade['id']} YES (price={yes_price}, past end_date)")
                        return 1.0
                    elif yes_price <= 0.04:
                        print(f"[resolver:price_expiry] #{trade['id']} NO (price={yes_price}, past end_date)")
                        return 0.0
        except Exception:
            pass
    except Exception:
        pass
    return None


def check_market_resolution(trade: dict) -> float | None:
    """
    Try all resolution strategies for a trade.
    Order: Price-expiry → Bulk cache → Gamma slug → CLOB → AI search.
    Returns 1.0/0.0 or None if still unresolved.
    """
    market_id = trade.get("market_id", "")
    tid       = trade.get("token_id")

    if not tid:
        tid = _get_token_id_for_trade(market_id)

    # Strategy 0: Price-based expiry resolution (fastest for expired markets)
    result = _resolve_via_price_expiry(trade)
    if result is not None:
        return result

    # Strategy 1: Bulk cache hit
    cached = _resolution_cache.get(market_id)
    if cached is not None:
        print(f"[resolver:cache] #{trade['id']} → {cached}")
        return cached

    # Strategy 1.5: MCP client
    if mcp:
        try:
            mcp_result = mcp.check_resolution_sync(market_id)
            if mcp_result and mcp_result.get("outcome"):
                outcome = mcp_result["outcome"]
                result = 1.0 if outcome == "Yes" else 0.0
                print(f"[resolver:MCP] #{trade['id']} → {result}")
                return result
        except Exception as e:
            log.debug(f"[resolver:MCP] #{trade['id']} error: {e}")

    # Strategy 2: Gamma slug-based lookup (MOST RELIABLE)
    result = _resolve_via_gamma_slug(trade)
    if result is not None:
        print(f"[resolver:gamma_slug] #{trade['id']} → {result}")
        return result

    # Strategy 3: CLOB book prices
    if tid and len(str(tid)) > 50:
        result = _resolve_via_clob(tid)
        if result is not None:
            print(f"[resolver:CLOB] #{trade['id']} token={tid[:12]}… → {result}")
            return result

    # Strategy 4: AI search fallback
    search_res = _resolve_via_search(trade.get("market_question", ""))
    if search_res is not None:
        print(f"[resolver:search] #{trade['id']} → {search_res}")
    return search_res


def resolve_trade(trade_id: int, market_result: float, side: str, amount_usd: float,
                  market_price: float = 0.5):
    won = (side == "YES" and market_result == 1.0) or (side == "NO" and market_result == 0.0)
    if won:
        bet_price = market_price if side == "YES" else (1.0 - market_price)
        bet_price = max(0.01, min(0.99, bet_price))
        payout_ratio = (1.0 - bet_price) / bet_price
        pnl = round(amount_usd * payout_ratio, 4)
        result_str = "win"
    else:
        pnl = round(-amount_usd, 4); result_str = "loss"

    now = datetime.now(timezone.utc).isoformat()
    conn = _conn()
    conn.execute("""
        INSERT OR IGNORE INTO outcomes (trade_id, resolved_at, result, pnl)
        VALUES (?, ?, ?, ?)
    """, (trade_id, now, result_str, pnl))
    conn.execute("""
        INSERT OR REPLACE INTO calibration
          (trade_id, classification, materiality, entry_price, exit_price,
           actual_direction, correct, resolved_at)
        SELECT id, side, edge, market_price, ?,
               CASE WHEN ? = 1.0 THEN 'YES' ELSE 'NO' END,
               CASE WHEN ? THEN 1 ELSE 0 END, ?
        FROM trades WHERE id = ?
    """, (market_result, market_result, 1 if won else 0, now, trade_id))
    conn.commit()
    conn.close()
    return result_str, pnl


def _void_stuck_trades(pending: list[dict], max_pending_hours: float = 720.0) -> int:
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_pending_hours)
    void_ids = []
    for t in pending:
        try:
            created = datetime.fromisoformat(t["created_at"].replace("Z", "+00:00"))
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if created < cutoff:
                void_ids.append(t["id"])
        except Exception:
            pass
    if void_ids:
        conn = _conn()
        conn.execute(
            f"UPDATE trades SET status='voided' WHERE id IN ({','.join('?'*len(void_ids))})",
            void_ids
        )
        conn.commit()
        conn.close()
        print(f"[resolver] Voided {len(void_ids)} stuck trades")
    return len(void_ids)


def run_resolution_check(verbose: bool = True) -> dict:
    pending = get_pending_demo_trades()
    if not pending:
        if verbose: print("[resolver] No pending trades.")
        return {"checked": 0, "resolved": 0, "wins": 0, "losses": 0, "pushes": 0}

    if verbose: print(f"[resolver] Checking {len(pending)} pending demo trades...")

    voided = _void_stuck_trades(pending, max_pending_hours=168.0)
    if voided > 0:
        pending = get_pending_demo_trades()

    _refresh_bulk_cache(pending)

    resolved = wins = losses = pushes = 0
    for trade in pending:
        market_result = check_market_resolution(trade)
        if verbose:
            print(f"[resolver] #{trade['id']} result={market_result} "
                  f"q=\"{trade['market_question'][:45]}\"")
        if market_result is None:
            continue

        result_str, pnl = resolve_trade(
            trade_id=trade["id"], market_result=market_result,
            side=trade["side"], amount_usd=trade["amount_usd"],
            market_price=float(trade.get("market_price") or 0.5),
        )
        resolved += 1
        if result_str == "win":    wins   += 1; sym = "✅"
        elif result_str == "loss": losses += 1; sym = "❌"
        else:                      pushes += 1; sym = "↩️"
        if verbose:
            print(f"  {sym} #{trade['id']} {result_str.upper()} | "
                  f"{trade['side']} on \"{trade['market_question'][:45]}\" | "
                  f"PnL:${pnl:+.2f}")

    if verbose and resolved > 0:
        print(f"[resolver] Done: {resolved} resolved ({wins}W {losses}L {pushes}P)")

    return {"checked": len(pending), "resolved": resolved,
            "wins": wins, "losses": losses, "pushes": pushes}


def get_accuracy_stats() -> dict:
    conn = _conn()
    logged_row = conn.execute(
        "SELECT COUNT(*) as total FROM trades WHERE status IN ('demo','dry_run')"
    ).fetchone()
    # Exclude voided trades from accuracy — they were never resolved fairly
    row = conn.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN o.result = 'win'  THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN o.result = 'loss' THEN 1 ELSE 0 END) as losses,
            SUM(CASE WHEN o.result = 'push' THEN 1 ELSE 0 END) as pushes,
            SUM(o.pnl) as total_pnl
        FROM trades t
        JOIN outcomes o ON t.id = o.trade_id
        WHERE t.status IN ('demo', 'dry_run')
          AND t.status != 'voided'
    """).fetchone()

    ttr_row = conn.execute("""
        SELECT AVG(
            (julianday(o.resolved_at) - julianday(t.created_at)) * 24
        ) as avg_ttr_hours
        FROM trades t
        JOIN outcomes o ON t.id = o.trade_id
        WHERE t.status IN ('demo', 'dry_run')
          AND o.resolved_at IS NOT NULL
          AND t.created_at IS NOT NULL
    """).fetchone()
    conn.close()

    total = int(row["total"] or 0)
    wins  = int(row["wins"]  or 0)
    losses= int(row["losses"]or 0)
    pushes= int(row["pushes"]or 0)
    pnl   = float(row["total_pnl"] or 0)
    decisive = total - pushes
    acc = (wins / decisive * 100) if decisive > 0 else 0.0
    avg_ttr = float(ttr_row["avg_ttr_hours"] or 0) if ttr_row and ttr_row["avg_ttr_hours"] else 0.0
    return {
        "total_logged":   int(logged_row["total"] or 0),
        "total_resolved": total,
        "wins": wins, "losses": losses, "pushes": pushes,
        "accuracy_pct": round(acc, 1),
        "total_pnl": round(pnl, 2),
        "ready_for_live": decisive >= 10 and acc >= 70.0,
        "avg_ttr_hours": round(avg_ttr, 1),
    }


def get_pipeline_comparison(new_pipeline_start_id: int = 192) -> dict:
    conn = _conn()

    def _stats(where_clause: str, params: tuple = ()) -> dict:
        row = conn.execute(f"""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN o.result = 'win'  THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN o.result = 'loss' THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN o.result = 'push' THEN 1 ELSE 0 END) as pushes,
                COALESCE(SUM(o.pnl), 0) as total_pnl
            FROM trades t
            JOIN outcomes o ON t.id = o.trade_id
            WHERE t.status IN ('demo', 'dry_run') AND {where_clause}
        """, params).fetchone()
        total   = int(row["total"]  or 0)
        wins    = int(row["wins"]   or 0)
        losses  = int(row["losses"] or 0)
        pushes  = int(row["pushes"] or 0)
        pnl     = float(row["total_pnl"] or 0)
        decisive = total - pushes
        acc = (wins / decisive * 100) if decisive > 0 else 0.0
        return {"resolved": total, "wins": wins, "losses": losses,
                "pushes": pushes, "accuracy_pct": round(acc, 1),
                "total_pnl": round(pnl, 2)}

    old = _stats("t.id < ?", (new_pipeline_start_id,))
    new = _stats("t.id >= ?", (new_pipeline_start_id,))

    cat_rows = conn.execute("""
        SELECT
            CASE
                WHEN LOWER(t.market_question) LIKE '%bitcoin%'
                  OR LOWER(t.market_question) LIKE '%btc%'
                  OR LOWER(t.market_question) LIKE '%ethereum%'
                  OR LOWER(t.market_question) LIKE '%eth %'
                  OR LOWER(t.market_question) LIKE '%solana%'
                  OR LOWER(t.market_question) LIKE '%xrp%'
                  OR LOWER(t.market_question) LIKE '%crypto%'
                  OR LOWER(t.market_question) LIKE '%up or down%'
                  THEN 'crypto'
                WHEN LOWER(t.market_question) LIKE '%trump%'
                  OR LOWER(t.market_question) LIKE '%federal reserve%'
                  OR LOWER(t.market_question) LIKE '%fed rate%'
                  OR LOWER(t.market_question) LIKE '%tariff%'
                  OR LOWER(t.market_question) LIKE '%ceasefire%'
                  OR LOWER(t.market_question) LIKE '%congress%'
                  OR LOWER(t.market_question) LIKE '%election%'
                  THEN 'politics'
                WHEN LOWER(t.market_question) LIKE '%amazon%'
                  OR LOWER(t.market_question) LIKE '%tesla%'
                  OR LOWER(t.market_question) LIKE '%s&p 500%'
                  OR LOWER(t.market_question) LIKE '%nasdaq%'
                  OR LOWER(t.market_question) LIKE '%stock%'
                  THEN 'finance'
                WHEN LOWER(t.market_question) LIKE '%ipl%'
                  OR LOWER(t.market_question) LIKE '%cricket%'
                  THEN 'cricket'
                ELSE 'other'
            END as category,
            COUNT(*) as total,
            SUM(CASE WHEN o.result = 'win'  THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN o.result = 'loss' THEN 1 ELSE 0 END) as losses,
            COALESCE(SUM(o.pnl), 0) as pnl
        FROM trades t
        JOIN outcomes o ON t.id = o.trade_id
        WHERE t.status IN ('demo', 'dry_run') AND t.id >= ?
        GROUP BY category
    """, (new_pipeline_start_id,)).fetchall()

    categories = {}
    for r in cat_rows:
        wins = int(r["wins"] or 0)
        losses = int(r["losses"] or 0)
        decisive = wins + losses
        acc = (wins / decisive * 100) if decisive > 0 else 0.0
        categories[r["category"]] = {
            "resolved": int(r["total"] or 0),
            "wins": wins, "losses": losses,
            "accuracy_pct": round(acc, 1),
            "pnl": round(float(r["pnl"] or 0), 2),
        }

    conn.close()
    return {"old": old, "new": new, "new_categories": categories,
            "split_trade_id": new_pipeline_start_id}


def get_resolved_trade_list() -> list[dict]:
    conn = _conn()
    rows = conn.execute("""
        SELECT t.id, t.market_question, t.side, t.amount_usd,
               t.market_price, t.edge, o.result, o.pnl, o.resolved_at
        FROM trades t
        JOIN outcomes o ON t.id = o.trade_id
        WHERE t.status IN ('demo', 'dry_run')
        ORDER BY o.result, o.resolved_at DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_signal_accuracies() -> dict[str, dict]:
    import json as _json
    conn = _conn()
    rows = conn.execute("""
        SELECT t.signals, t.side, o.result
        FROM trades t
        JOIN outcomes o ON t.id = o.trade_id
        WHERE t.status IN ('demo','dry_run')
          AND t.signals IS NOT NULL
          AND o.result IN ('win','loss')
    """).fetchall()
    conn.close()

    stats: dict[str, dict] = {}
    for row in rows:
        try:
            sigs = _json.loads(row["signals"])
        except Exception:
            continue
        trade_side = row["side"]
        outcome    = row["result"]
        for sig_name, val in sigs.items():
            if not val or val == "neutral":
                continue
            parts = val.split(":")
            if len(parts) != 2:
                continue
            sig_dir, sig_conf_str = parts[0], parts[1]
            try:
                sig_conf = float(sig_conf_str)
            except ValueError:
                continue
            trade_dir = "bullish" if trade_side == "YES" else "bearish"
            if sig_dir != trade_dir:
                continue
            s = stats.setdefault(sig_name, {"wins": 0, "losses": 0, "total_conf": 0.0, "count": 0})
            s["count"]      += 1
            s["total_conf"] += sig_conf
            if outcome == "win":
                s["wins"]   += 1
            else:
                s["losses"] += 1

    result = {}
    SIG_LABELS = {"pf": "Price Feed", "ai": "AI Research", "copy": "Copy-Trade",
                  "whale": "Whale", "crowd": "Crowd CLOB"}
    for sig, s in stats.items():
        decisive = s["wins"] + s["losses"]
        acc = (s["wins"] / decisive * 100) if decisive > 0 else 0.0
        result[sig] = {
            "label":        SIG_LABELS.get(sig, sig),
            "trades":       decisive,
            "wins":         s["wins"],
            "losses":       s["losses"],
            "accuracy_pct": round(acc, 1),
            "avg_conf":     round(s["total_conf"] / s["count"], 2) if s["count"] else 0.0,
        }
    return dict(sorted(result.items(), key=lambda x: -x[1]["accuracy_pct"]))


_MIN_SIGNAL_TRADES = 8
_DEFAULT_WEIGHTS = {"pf": 0.40, "ai": 0.30, "copy": 0.20, "whale": 0.07, "crowd": 0.03}


def get_dynamic_weights() -> dict[str, float]:
    accs = get_signal_accuracies()
    raw: dict[str, float] = {}
    for sig, s in accs.items():
        if s["trades"] >= _MIN_SIGNAL_TRADES:
            edge = max(0.0, (s["accuracy_pct"] / 100.0) - 0.50)
            raw[sig] = edge * s["trades"]
    if not raw or sum(raw.values()) < 0.001:
        return _DEFAULT_WEIGHTS.copy()
    total = sum(raw.values())
    weights = {sig: round(v / total, 3) for sig, v in raw.items()}
    for sig in _DEFAULT_WEIGHTS:
        if sig not in weights:
            weights[sig] = 0.02
    total2 = sum(weights.values())
    return {sig: round(w / total2, 3) for sig, w in weights.items()}


def get_strategy_accuracies() -> list[dict]:
    conn = _conn()
    rows = conn.execute("""
        SELECT
            COALESCE(t.strategy, 'baseline') as strategy,
            COUNT(*) as total,
            SUM(CASE WHEN o.result='win'  THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN o.result='loss' THEN 1 ELSE 0 END) as losses,
            ROUND(SUM(o.pnl), 2) as pnl
        FROM trades t
        JOIN outcomes o ON t.id = o.trade_id
        WHERE t.status IN ('demo','dry_run')
          AND o.result IN ('win','loss')
        GROUP BY COALESCE(t.strategy, 'baseline')
        ORDER BY wins*1.0/MAX(1, wins+losses) DESC, total DESC
    """).fetchall()
    conn.close()

    result = []
    for r in rows:
        w = r["wins"] or 0
        l = r["losses"] or 0
        decisive = w + l
        acc = (w / decisive * 100) if decisive > 0 else 0.0
        result.append({
            "strategy":     r["strategy"],
            "trades":       decisive,
            "wins":         w,
            "losses":       l,
            "accuracy_pct": round(acc, 1),
            "pnl":          float(r["pnl"] or 0),
        })
    return result


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    run_resolution_check(verbose=True)
    stats = get_accuracy_stats()
    print(f"\nAccuracy: {stats['accuracy_pct']}% | {stats['wins']}W/{stats['losses']}L | PnL: ${stats['total_pnl']:+.2f}")

    print("\n-- Per-signal accuracy --")
    for sig, s in get_signal_accuracies().items():
        print(f"  {s['label']:15s}: {s['accuracy_pct']:5.1f}% ({s['wins']}W/{s['losses']}L, avg_conf={s['avg_conf']:.2f})")

    print("\n-- Dynamic weights --")
    for sig, w in get_dynamic_weights().items():
        print(f"  {sig:8s}: {w:.3f}")