#!/usr/bin/env python3
"""
resolver.py — Resolves demo trades via three strategies:

Strategy 1 (PRIMARY): CLOB API per-trade — confirmed working from Railway.
  fetch_book(token_id) → if best_bid > 0.95 → YES resolved
                       → if best_ask < 0.05 → NO resolved
  Clean, no bulk fetch, no text matching needed.

Strategy 2 (SECONDARY): Gamma REST endpoint per trade.
  GET gamma-api.polymarket.com/markets?id=<id>&limit=1
  Parse outcomePrices to get final result.

Strategy 3 (TERTIARY): Bulk Gamma closed-market scan + question text match.
  Scans 3000 closed markets, matches by question text (fuzzy).
  Kept as fallback for markets where token_id is missing.
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

import httpx

log = logging.getLogger(__name__)

_db_env = os.getenv("DB_PATH", "")
DB_PATH = Path(_db_env) if _db_env else Path(__file__).parent / "trades.db"
GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API  = "https://clob.polymarket.com"


# ── DB helpers ──────────────────────────────────────────────────────────────

def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def get_pending_demo_trades() -> list[dict]:
    conn = _conn()
    # Include token_id so CLOB resolution works directly without extra DB lookup
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
    """
    Look up YES-token id from DB only.
    NOTE: Gamma's conditionId filter is fundamentally broken — it always returns
    the same default market regardless of the conditionId queried. We do NOT
    attempt Gamma lookup here. token_id is only available for trades logged
    after the token_id fix (trades #187+).
    """
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


# ── Strategy 1: CLOB book prices ────────────────────────────────────────────

def _resolve_via_clob(token_id: str, timeout: int = 8) -> float | None:
    """
    Check CLOB book for a YES token.
    Resolved YES  → bids near 1.0 / asks near 1.0  → return 1.0
    Resolved NO   → bids near 0.0 / asks near 0.0  → return 0.0
    Still open    → mixed prices                    → return None
    """
    if not token_id:
        return None
    try:
        r = httpx.get(f"{CLOB_API}/book", params={"token_id": token_id}, timeout=timeout)
        if r.status_code != 200:
            return None
        data = r.json()
        bids = data.get("bids", []) or []
        asks = data.get("asks", []) or []

        # If no book at all, market may be resolved (no liquidity post-resolution)
        print(f"[resolver:CLOB_book] token={token_id[:12]} bids={len(bids)} asks={len(asks)} raw={str(data)[:120]}")
        if not bids and not asks:
            # Try midpoint from last_trade_price or hash field
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
        if avg_price >= 0.95:  return 1.0   # resolved YES
        if avg_price <= 0.05:  return 0.0   # resolved NO
        return None  # still trading
    except Exception as e:
        log.debug(f"[resolver:clob] {token_id[:12]}: {e}")
        return None


# ── Strategy 2: Gamma REST per-trade ────────────────────────────────────────

def _resolve_via_gamma_direct(market_id: str, timeout: int = 10) -> float | None:
    """
    Directly fetch a single market from Gamma by conditionId.
    Tries multiple param formats since the API is inconsistent.
    """
    if not market_id:
        return None
    attempts = [
        {"conditionId": market_id, "limit": 1},
        {"condition_id": market_id, "limit": 1},
        {"clob_token_ids": market_id, "limit": 1},
    ]
    for params in attempts:
        try:
            r = httpx.get(f"{GAMMA_API}/markets", params=params, timeout=timeout)
            if r.status_code != 200:
                continue
            data = r.json()
            items = data if isinstance(data, list) else data.get("data", [])
            for m in items:
                # Only accept this market if its conditionId/id matches ours
                m_id = m.get("conditionId") or m.get("id") or ""
                if m_id and m_id != market_id:
                    continue  # wrong market — skip (Gamma filter is broken, must verify)
                result = _parse_outcome(m)
                if result is not None:
                    log.debug(f"[resolver:gamma] {market_id[:16]} → {result}")
                    return result
        except Exception as e:
            log.debug(f"[resolver:gamma] {market_id[:16]} attempt failed: {e}")
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
    return s[:length]


def _parse_outcome(m: dict) -> float | None:
    """Extract result from Gamma market dict. Returns 1.0 (YES) / 0.0 (NO) / None.
    
    CRITICAL: Never return 0.5 (push). A market either resolved YES, NO, or is
    still pending. The old code returned 0.5 for any closed+inactive market,
    which caused ALL trades to resolve as 'push' with $0 PnL.
    """
    outcome_prices_raw = m.get("outcomePrices", "")
    if outcome_prices_raw:
        try:
            prices = json.loads(outcome_prices_raw) if isinstance(outcome_prices_raw, str) else outcome_prices_raw
            if len(prices) >= 2:
                yes_price = float(prices[0])
                no_price  = float(prices[1])
                if yes_price >= 0.85:   return 1.0   # YES resolved
                if no_price  >= 0.85:   return 0.0   # NO resolved
        except (json.JSONDecodeError, ValueError):
            pass

    res_price = m.get("resolutionPrice")
    if res_price is not None:
        try:
            rp = float(res_price)
            if rp >= 0.90: return 1.0
            if rp <= 0.10: return 0.0
        except (ValueError, TypeError):
            pass

    # If market is resolved (closed=true) but we can't determine the outcome,
    # return None — do NOT mark as push. Let it stay pending until we get
    # clear resolution data.
    return None


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
    first5_questions: list[str] = []  # debug: show what Gamma returns

    for offset in range(0, 3000, 100):
        try:
            r = httpx.get(f"{GAMMA_API}/markets",
                params={"closed": "true", "limit": 100, "offset": offset,
                        "order": "updatedAt", "ascending": "false"}, timeout=15)
            r.raise_for_status()
            data = r.json()
            items = data if isinstance(data, list) else data.get("data", [])
            if not items:
                break
            fetched_total += len(items)
            for m in items:
                gq_full = (m.get("question") or "").lower().strip()
                if offset == 0 and len(first5_questions) < 5:
                    first5_questions.append(gq_full[:70])

                # Index ALL closed markets — even without clear outcome prices yet
                # We check outcome separately below
                result = _parse_outcome(m)
                # Match by question text
                matched_cid = None
                for ln in (80, 60, 40):
                    gq = _normalize_q(gq_full, ln)
                    if gq in pending_by_q:
                        matched_cid = pending_by_q[gq]
                        break
                if matched_cid and result is not None:
                    _resolution_cache[matched_cid] = result
                    matched += 1
                    print(f"[resolver:bulk] MATCH '{gq_full[:50]}' → {result}")
                # Index by IDs for CLOB strategy
                for id_field in ("conditionId", "id"):
                    cid2 = m.get(id_field, "")
                    if cid2 and result is not None:
                        _resolution_cache[cid2] = result
        except Exception as e:
            log.warning(f"[resolver:bulk] offset={offset}: {e}")
            break

    _cache_fetched_at = now
    if first5_questions:
        print(f"[resolver] bulk sample questions: {first5_questions}")
    print(f"[resolver] bulk: {fetched_total} closed markets scanned, {matched} text-matched")

    # Bonus: direct question-text search for each pending trade
    for t in pending_trades[:20]:  # cap to avoid rate limits
        q = t.get("market_question", "")
        mid = t["market_id"]
        if mid in _resolution_cache:
            continue  # already resolved
        try:
            r = httpx.get(f"{GAMMA_API}/markets",
                params={"question": q[:100], "limit": 3, "closed": "true"}, timeout=8)
            if r.status_code == 200:
                data = r.json()
                items = data if isinstance(data, list) else data.get("data", [])
                for m in items:
                    mq = (m.get("question") or "").strip()
                    # Check if questions are close enough
                    if _normalize_q(mq, 60) == _normalize_q(q, 60):
                        result = _parse_outcome(m)
                        if result is not None:
                            _resolution_cache[mid] = result
                            print(f"[resolver:qsearch] #{t['id']} matched! → {result}")
                            matched += 1
                            break
        except Exception:
            pass


# ── Main resolution logic ────────────────────────────────────────────────────

def check_market_resolution(trade: dict) -> float | None:
    """
    Try all three resolution strategies for a trade.
    Returns 1.0/0.0/0.5 or None if still unresolved.
    """
    market_id = trade.get("market_id", "")
    tid       = trade.get("token_id")

    # Fetch token_id if not stored with this trade
    if not tid:
        tid = _get_token_id_for_trade(market_id)

    # Strategy 1: CLOB book prices (most reliable — confirmed working from Railway)
    if tid:
        result = _resolve_via_clob(tid)
        if result is not None:
            print(f"[resolver:CLOB] #{trade['id']} token={tid[:12]}… → {result}")
            return result
    else:
        print(f"[resolver:CLOB] #{trade['id']} no token_id — skipping CLOB")

    # Strategy 2: Gamma direct REST lookup
    result = _resolve_via_gamma_direct(market_id)
    if result is not None:
        print(f"[resolver:Gamma] #{trade['id']} → {result}")
        return result

    # Strategy 3: Bulk cache hit
    cached = _resolution_cache.get(market_id)
    if cached is not None:
        print(f"[resolver:cache] #{trade['id']} → {cached}")
    return cached


def resolve_trade(trade_id: int, market_result: float, side: str, amount_usd: float,
                  market_price: float = 0.5):
    won = (side == "YES" and market_result == 1.0) or (side == "NO" and market_result == 0.0)
    if won:
        # Actual payout depends on the price we bought at
        # YES at price p → win pays (1-p)/p per dollar
        # NO at price p  → win pays p/(1-p) per dollar
        bet_price = market_price if side == "YES" else (1.0 - market_price)
        bet_price = max(0.01, min(0.99, bet_price))  # clamp to avoid div-by-zero
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


def _void_stuck_trades(pending: list[dict], max_pending_hours: float = 36.0) -> int:
    """
    Void trades that have been pending too long — market probably resolved but
    Gamma hasn't indexed it. Marks as 'voided' so they don't clog the pipeline.
    """
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
        print(f"[resolver] Voided {len(void_ids)} stuck trades (pending >{max_pending_hours:.0f}h): {void_ids}")
    return len(void_ids)


def run_resolution_check(verbose: bool = True) -> dict:
    pending = get_pending_demo_trades()
    if not pending:
        if verbose: print("[resolver] No pending trades.")
        return {"checked": 0, "resolved": 0, "wins": 0, "losses": 0, "pushes": 0}

    if verbose: print(f"[resolver] Checking {len(pending)} pending demo trades...")

    # Void trades stuck >36h (Polymarket likely resolved but Gamma not indexed)
    voided = _void_stuck_trades(pending, max_pending_hours=36.0)
    if voided > 0:
        pending = get_pending_demo_trades()  # refresh

    # Kick off bulk scan (populates _resolution_cache for text-match fallback)
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
    """).fetchone()
    conn.close()

    total = int(row["total"] or 0)
    wins  = int(row["wins"]  or 0)
    losses= int(row["losses"]or 0)
    pushes= int(row["pushes"]or 0)
    pnl   = float(row["total_pnl"] or 0)
    decisive = total - pushes
    acc = (wins / decisive * 100) if decisive > 0 else 0.0
    return {
        "total_logged":   int(logged_row["total"] or 0),
        "total_resolved": total,
        "wins": wins, "losses": losses, "pushes": pushes,
        "accuracy_pct": round(acc, 1),
        "total_pnl": round(pnl, 2),
        "ready_for_live": decisive >= 10 and acc >= 70.0,
    }


def get_pipeline_comparison(new_pipeline_start_id: int = 192) -> dict:
    """
    Side-by-side accuracy: OLD pipeline (id < new_pipeline_start_id) vs
    NEW pipeline (id >= new_pipeline_start_id, verifiable-market era).
    Returns dict with 'old' and 'new' sub-dicts each containing
    wins/losses/accuracy_pct/total_pnl, plus a category breakdown for new.
    """
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

    # Category breakdown for new pipeline
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


# ── Per-signal accuracy tracking ─────────────────────────────────────────────

def get_signal_accuracies() -> dict[str, dict]:
    """
    Return accuracy stats for each individual signal type.
    Parses the JSON 'signals' column stored per trade.

    Returns dict: {signal_name: {trades, wins, losses, accuracy_pct, avg_conf}}

    Signal names: "pf" (price feed), "ai" (research), "copy" (copy-trade),
                  "whale" (whale holders), "crowd" (CLOB crowd)
    """
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

    # {signal: {wins, losses, total_conf, count}}
    stats: dict[str, dict] = {}

    for row in rows:
        try:
            sigs = _json.loads(row["signals"])
        except Exception:
            continue

        trade_side = row["side"]   # "YES" or "NO"
        outcome    = row["result"] # "win" or "loss"

        for sig_name, val in sigs.items():
            if not val or val == "neutral":
                continue
            # val format: "direction:confidence" e.g. "bearish:0.82"
            parts = val.split(":")
            if len(parts) != 2:
                continue
            sig_dir, sig_conf_str = parts[0], parts[1]
            try:
                sig_conf = float(sig_conf_str)
            except ValueError:
                continue

            # Did this signal agree with the trade direction?
            trade_dir = "bullish" if trade_side == "YES" else "bearish"
            if sig_dir != trade_dir:
                continue  # signal wasn't the reason for this trade direction

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

    # Sort by accuracy desc
    return dict(sorted(result.items(), key=lambda x: -x[1]["accuracy_pct"]))


# Min resolved trades per signal before we trust the empirical accuracy
_MIN_SIGNAL_TRADES = 8

# Default weights when we don't have enough data yet
_DEFAULT_WEIGHTS = {"pf": 0.40, "ai": 0.30, "copy": 0.20, "whale": 0.07, "crowd": 0.03}


def get_dynamic_weights() -> dict[str, float]:
    """
    Compute signal weights from empirical per-signal accuracy.
    Formula: weight ∝ (accuracy - 0.50) × trades  (only counts edge above 50%)
    Falls back to default weights if insufficient data per signal.

    Returns dict: {signal_name: weight}  (sums to 1.0)
    """
    accs = get_signal_accuracies()

    raw: dict[str, float] = {}
    for sig, s in accs.items():
        if s["trades"] >= _MIN_SIGNAL_TRADES:
            # Edge above 50% × number of trades = confidence-weighted edge
            edge = max(0.0, (s["accuracy_pct"] / 100.0) - 0.50)
            raw[sig] = edge * s["trades"]

    if not raw or sum(raw.values()) < 0.001:
        return _DEFAULT_WEIGHTS.copy()

    total = sum(raw.values())
    weights = {sig: round(v / total, 3) for sig, v in raw.items()}

    # Ensure all 5 signals have a weight (minimum 0.02 floor for less-proven signals)
    for sig in _DEFAULT_WEIGHTS:
        if sig not in weights:
            weights[sig] = 0.02

    # Re-normalise after adding floors
    total2 = sum(weights.values())
    return {sig: round(w / total2, 3) for sig, w in weights.items()}


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    run_resolution_check(verbose=True)
    stats = get_accuracy_stats()
    print(f"\nAccuracy: {stats['accuracy_pct']}% | {stats['wins']}W/{stats['losses']}L | PnL: ${stats['total_pnl']:+.2f}")

    print("\n── Per-signal accuracy ──")
    for sig, s in get_signal_accuracies().items():
        print(f"  {s['label']:15s}: {s['accuracy_pct']:5.1f}% ({s['wins']}W/{s['losses']}L, avg_conf={s['avg_conf']:.2f})")

    print("\n── Dynamic weights ──")
    for sig, w in get_dynamic_weights().items():
        print(f"  {sig:8s}: {w:.3f}")
