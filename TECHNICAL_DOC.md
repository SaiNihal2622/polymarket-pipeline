# Polymarket Auto-Trader — Complete Technical Documentation

> Last updated: April 2026  
> System version: V3 (Multi-signal consensus, Gemini + Groq backend, Railway deployment)

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture](#2-architecture)
3. [File-by-File Reference](#3-file-by-file-reference)
4. [Full Trading Pipeline (Step by Step)](#4-full-trading-pipeline-step-by-step)
5. [LLM Backend & Rate Limiting](#5-llm-backend--rate-limiting)
6. [Classification Engine (MiroFish Debate)](#6-classification-engine-mirofish-debate)
7. [Edge Detection & RRF Composite Scoring (SkillX Fusion)](#7-edge-detection--rrf-composite-scoring-skillx-fusion)
8. [Market Quality Filters](#8-market-quality-filters)
9. [Category Guard (Cross-Domain Protection)](#9-category-guard-cross-domain-protection)
10. [Demo Mode & Accuracy Tracking](#10-demo-mode--accuracy-tracking)
11. [Resolution Engine](#11-resolution-engine)
12. [Database Schema](#12-database-schema)
13. [Railway Deployment](#13-railway-deployment)
14. [Configuration Reference](#14-configuration-reference)
15. [Expected Performance](#15-expected-performance)
16. [Go-Live Criteria](#16-go-live-criteria)

---

## 1. System Overview

This is an automated prediction market trading pipeline for Polymarket. It:

1. **Ingests live news** from 17 RSS feeds, Twitter API v2, and Telegram channels
2. **Fetches live Polymarket markets** from the Gamma API (200 at a time)
3. **Matches news headlines to relevant markets** using keyword scoring
4. **Classifies each match** using two LLM passes (Analyst + Skeptic) — both must agree
5. **Scores each signal** using a 5-signal composite score (RRF fusion)
6. **Logs demo trades** (no real money) to SQLite for accuracy tracking
7. **Resolves completed markets** every 10 minutes — checks win/loss
8. **Unlocks live trading** when accuracy ≥ 70% over 10+ resolved trades

**Current mode:** Demo (paper trading). No real money is spent. All trades are logged with `status='demo'` in the database.

**Bankroll:** $20 configured. Max bet per trade: $2. Daily loss limit: $5.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Railway.app Container                     │
│                                                                  │
│  demo_runner.py (main loop — runs continuously)                  │
│       │                                                          │
│       ├── scraper.py          → 17 RSS feeds + NewsAPI           │
│       │    + scraper.py          + Twitter API v2                │
│       │    + scraper.py          + Telegram (if configured)      │
│       │                                                          │
│       ├── markets.py          → Polymarket Gamma API             │
│       │                         (200 markets, category-filtered) │
│       │                                                          │
│       ├── matcher.py          → keyword match: news ↔ markets    │
│       │                                                          │
│       ├── classifier.py       → LLM backend (Gemini/Groq/Claude) │
│       │    ├── Pass 1: Analyst (bullish/bearish/neutral)         │
│       │    └── Pass 2: Skeptic (devil's advocate)                │
│       │         → Consensus: both must agree or SKIP             │
│       │                                                          │
│       ├── edge.py             → 5-signal RRF composite score     │
│       │                         → position sizing (Quarter-Kelly) │
│       │                                                          │
│       ├── logger.py           → SQLite (trades.db on /data vol)  │
│       │                                                          │
│       └── resolver.py         → Gamma API resolution check       │
│                                  → win/loss/push determination    │
│                                                                  │
│  /data/trades.db  (Railway persistent volume — survives deploys) │
└─────────────────────────────────────────────────────────────────┘

External APIs:
  Gemini 2.0 Flash  →  primary LLM (fast + cheap, ~$0.01/1K tokens)
  Groq llama-3.1-8b →  instant fallback when Gemini returns 429
  Polymarket Gamma  →  market data + resolution (no auth needed)
  Polymarket CLOB   →  order execution (auth needed, unused in demo mode)
```

**Timing:**
- Scan every **30 minutes** (`SCAN_INTERVAL_MIN=30`)
- Resolution check every **10 minutes** (`RESOLVE_INTERVAL_MIN=10`)
- Markets window: closing within **168 hours** (7 days)

---

## 3. File-by-File Reference

| File | Role | Key Functions |
|------|------|---------------|
| `demo_runner.py` | Main loop, orchestration | `scan_and_trade()`, `run_loop()`, `filter_quality_markets()`, `_cat()` |
| `classifier.py` | LLM classification engine | `classify()`, `_call_gemini()`, `_call_groq()`, `_parse_json_response()` |
| `edge.py` | Edge detection + position sizing | `detect_edge_v2()`, `compute_composite_score()`, `size_position()` |
| `markets.py` | Polymarket market fetching | `fetch_active_markets()`, `filter_by_categories()` |
| `scraper.py` | News ingestion | `scrape_all()`, `scrape_rss()`, `scrape_twitter()`, `scrape_telegram()` |
| `matcher.py` | Keyword matching | `match_news_to_markets()`, `extract_keywords()` |
| `resolver.py` | Trade resolution | `run_resolution_check()`, `check_market_resolution()`, `get_accuracy_stats()` |
| `logger.py` | SQLite database | `log_trade()`, `get_pending_market_ids()`, `get_accuracy_stats()` |
| `config.py` | All configuration | env var loading, thresholds, API keys |
| `executor.py` | Live order placement | `place_order()` (unused in demo mode) |
| `news_stream.py` | NewsEvent dataclass | timestamp, age, latency tracking |
| `pipeline.py` | V1 pipeline (legacy) | Single-pass scoring (replaced by V2/V3) |
| `start.py` | CLI entry point | mode switching (v1/v2/demo) |
| `dashboard.py` | V3 live dashboard | Rich terminal UI with auto-refresh |

---

## 4. Full Trading Pipeline (Step by Step)

### Step 1: News Ingestion (`scraper.py`)

```python
news_items = scrape_all(config.NEWS_LOOKBACK_HOURS)  # lookback = 6 hours
```

Sources scraped in parallel:
- **17 RSS feeds** — Google News (AI, crypto, politics, sports, IPL, NBA, NFL, Champions League, Oscars, SpaceX, Fed), TechCrunch, Ars Technica, The Verge, NYT Tech, NYT Politics, BBC World, CoinTelegraph, CoinDesk
- **Twitter API v2** — keyword stream on 50+ terms (OpenAI, Bitcoin, IPL, NBA, tariff, SpaceX, etc.) if `TWITTER_BEARER_TOKEN` is set
- **Telegram** — channel scraping if `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHANNEL_IDS` are set

Output: ~100–200 `NewsItem` objects with headline, source, URL, published timestamp.

### Step 2: Market Fetching (`markets.py`)

```python
all_markets = fetch_active_markets(limit=200)
category_filtered = filter_by_categories(all_markets)
window_markets = filter_closing_soon(category_filtered, DEMO_HOURS_WINDOW)
```

- Calls `https://gamma-api.polymarket.com/markets` with `active=true`
- Filters to 10 tracked categories: ai, technology, crypto, politics, science, sports, entertainment, finance, world, other
- Filters to markets closing within `DEMO_HOURS_WINDOW=168` hours (7 days)

### Step 3: Quality Filtering (`demo_runner.py`)

```python
day_markets, skipped = filter_quality_markets(window_markets, now)
```

Four quality gates (see [Section 8](#8-market-quality-filters) for details):
1. Closes in < `MIN_CLOSE_HOURS=1.5h` → skip (already priced in)
2. YES price < `MIN_YES_PRICE=0.05` or > `MAX_YES_PRICE=0.95` → skip (near-certain)
3. Volume < `MIN_VOLUME_USD=500` → skip (micro/illiquid markets)
4. Window duration < `MIN_WINDOW_HOURS=0.5h` → skip (30-minute markets)

Typical result: 200 markets → ~12–30 quality markets.

### Step 4: News-Market Matching (`demo_runner.py` inline + `matcher.py`)

```python
# Category guard first
if mkt_cat != "general" and mkt_cat != news_cat:
    if news_cat != "general" or mkt_cat in _STRICT_CATS:
        continue  # cross-domain skip

# Keyword hit scoring
kws = extract_keywords(market.question)
hits = sum(1 for kw in kws if kw in headline_lower)
score = hits / len(kws)
```

- Each news headline is tested against every quality market
- Category guard prevents crypto news matching weather markets, etc.
- Keyword overlap score ranks matches; best-scoring news per market is kept
- Capped at `MAX_PAIRS_PER_SCAN=15` unique market×news pairs per scan

### Step 5: LLM Classification (`classifier.py`)

```python
classification = classify(headline, market, source)
```

Two passes run sequentially (MiroFish debate pattern):

**Pass 1 — Analyst** (temperature=0.1):
> "Does this news make the market question MORE likely YES, MORE likely NO, or is it NOT RELEVANT? Rate materiality 0.0–1.0."

**Pass 2 — Skeptic** (temperature=0.2):
> "Challenge the initial reaction. Is this already priced in? Does this actually change the odds from the current {yes_price:.0%}?"

Both return JSON: `{"direction": "bullish"|"bearish"|"neutral", "materiality": 0.0–1.0, "reasoning": "..."}`

**Consensus gate:** If the two passes disagree on direction → `consensus_agreed=False` → trade skipped.

### Step 6: Edge Detection + RRF Scoring (`edge.py`)

```python
signal = detect_edge_v2(market, classification, news_event)
```

Prerequisites for a signal:
1. Direction is not neutral
2. Consensus agreed (both passes agree)
3. Materiality ≥ `MATERIALITY_THRESHOLD=0.30`
4. Raw edge ≥ `EDGE_THRESHOLD=0.15`
5. Composite score ≥ 0.4

5-signal composite score (see [Section 7](#7-edge-detection--rrf-composite-scoring-skillx-fusion)):
```
composite = 0.35 × materiality
          + 0.25 × normalized_materiality
          + 0.20 × price_room_signal
          + 0.10 × niche_market_signal
          + 0.10 × recency_signal
```

### Step 7: Demo Trade Logging (`logger.py`)

```python
trade_id = logger.log_trade(..., status="demo")
```

All trade parameters stored: market ID, question, direction, materiality, composite score, edge, side (YES/NO), bet amount, news headline, source, LLM reasoning, latency breakdown.

### Step 8: Resolution Check (`resolver.py`, runs every 10 min)

```python
run_resolution_check(verbose=True)
```

- Queries `https://gamma-api.polymarket.com/markets?conditionIds=<id>` for each pending demo trade
- Checks `closed` + `active` flags + `outcomePrices`
- Determines win (prediction correct), loss (prediction wrong), or push (market invalid/cancelled)
- Updates `outcomes` table with `result` and `pnl`
- Tracks accuracy in `calibration` table

---

## 5. LLM Backend & Rate Limiting

### Provider Priority

```
LLM_PROVIDER = "gemini"  →  Gemini 2.0 Flash (primary)
                          →  Groq llama-3.1-8b (instant fallback on 429)
```

Auto-detect order (if `LLM_PROVIDER` not set): Gemini → Groq → Ollama → Anthropic

### Gemini Rate Control (`classifier.py`)

```python
_GEMINI_MIN_INTERVAL = 3.0  # seconds between calls = ~20 RPM (limit: 2000 RPM)
```

- Random jitter: 0.1–0.5s added per call
- On **429** (`RESOURCE_EXHAUSTED`): **instant Groq fallback** — no waiting, no stalling
- On **503** (`UNAVAILABLE`): one retry after 5s, then Groq fallback
- On any other error: propagates up

**Why 429s happen:** Google's pay-as-you-go capacity is not guaranteed even when under quota. The burst can spike. Solution: instant Groq fallback — the scan never stalls.

### Groq Rate Control

```python
max_retries = 4
backoff = 15  # seconds, doubles each retry (15s → 30s → 60s → 120s)
```

- Model: `llama-3.1-8b-instant` (overrides any Claude/Gemma model names automatically)
- On 429: exponential backoff up to 4 retries

### Token Budget

Each classification call: 2 prompts × ~400 token prompt + 200 token response = ~1,200 tokens per market×news pair.  
At 15 pairs per scan, 30-min interval: ~24 calls/hour × 1,200 tokens = ~29K TPM (well under 4M TPM limit).

---

## 6. Classification Engine (MiroFish Debate)

Inspired by the MiroFish multi-agent debate pattern: run the same question from two opposing perspectives and only act when both agree.

### Pass 1 — Analyst Prompt

Key framing:
```
"Does this news make the market question MORE likely YES, MORE likely NO, or NOT RELEVANT?
Rate MATERIALITY: 0.0=irrelevant, 0.3=minor, 0.6=meaningful, 1.0=definitive"
```

Provides: current YES price as context so LLM knows the starting point.

### Pass 2 — Skeptic Prompt

Key framing:
```
"Challenge the initial reaction:
- Is this ALREADY priced in? The current YES is {yes_price:.0%}.
- Does this DIRECTLY affect the outcome?
- Could the opposite still easily happen?
Only rate above 0.4 materiality if news genuinely changes odds from current price."
```

The skeptic is designed to suppress overconfident signals — it should return neutral on weak evidence.

### Consensus Logic

```python
non_neutral = [d for d in directions if d != "neutral"]
agreed = len(set(non_neutral)) == 1
dominant_direction = non_neutral[0] if agreed else "neutral"
```

- If both say bullish → `consensus_agreed=True`, direction=bullish
- If one says bullish, one bearish → `consensus_agreed=False` → no trade
- If one says bullish, one neutral → `consensus_agreed=True` (non-neutral set = {bullish})
- If both neutral → direction=neutral → no trade

Materiality is averaged over non-neutral passes only (so a neutral skeptic doesn't zero out a strong analyst signal, but does reduce confidence).

---

## 7. Edge Detection & RRF Composite Scoring (SkillX Fusion)

Inspired by Reciprocal Rank Fusion — multiple independent signals combined into one confidence metric.

### Raw Edge Calculation

```python
if direction == "bullish":
    raw_edge = materiality × (1.0 - yes_price)  # how much YES can move up
else:
    raw_edge = materiality × yes_price           # how much NO can move up
```

Minimum: `EDGE_THRESHOLD=0.15`

### 5-Signal Composite Score

| Signal | Weight | Normalization |
|--------|--------|---------------|
| Classification strength | 35% | = materiality (0–1) |
| Materiality bonus | 25% | materiality / 0.8, capped at 1.0 |
| Price room | 20% | price_room / 0.5, capped at 1.0 |
| Niche market bonus | 10% | 1.0 if vol ≤ $50K, 0.7 if ≤ $200K, 0.4 if ≤ $500K, 0.1 otherwise |
| News recency | 10% | 1.0 if < 30min, 0.8 if < 1.5h, 0.5 if < 3h, 0.3 if < 6h, 0.1 otherwise |

Minimum composite for trade: **0.4** (rejects about 50% of signals that pass other gates).

### Position Sizing (Quarter-Kelly)

```python
fraction = edge × 0.25                      # quarter-Kelly fraction
confidence_multiplier = 0.5 + composite     # 0.9× to 1.5× based on confidence
raw_size = bankroll × fraction × confidence_multiplier
bet = clamp(raw_size, min=$0.50, max=MAX_BET_USD=$2.00)
```

On $20 bankroll: typical bet $0.50–$2.00.

---

## 8. Market Quality Filters

Applied after category filtering and window filtering, before any LLM calls.

| Filter | Default | Purpose |
|--------|---------|---------|
| `MIN_CLOSE_HOURS=1.5` | Markets closing in < 1.5h are skipped | Already priced in — no edge left |
| `MIN_YES_PRICE=0.05` | Skip if YES < 5% | Near-impossible — market knows NO |
| `MAX_YES_PRICE=0.95` | Skip if YES > 95% | Near-certain — market knows YES |
| `MIN_VOLUME_USD=500` | Skip if volume < $500 | Micro/illiquid/5-minute markets |
| `MIN_WINDOW_HOURS=0.5` | Skip markets with < 30min window | e.g. "8:00am–8:30am" events |

**Why these values:** The original conservative defaults (MIN_VOLUME=5000, MIN_YES=0.20, MAX_YES=0.80) filtered out 95% of markets, leaving only 2–4 per scan. Relaxed to allow more signals while still blocking junk. Most crypto markets are at extreme prices (BTC above $X = YES 0.98) and get filtered by price-extreme.

---

## 9. Category Guard (Cross-Domain Protection)

Prevents news about Bitcoin from triggering a trade on a weather market, or NBA news from triggering on cricket markets. Runs before LLM calls (saves tokens and prevents nonsense signals).

### Category Classifier (`_cat()` in `demo_runner.py`)

```python
def _cat(text: str) -> str:
    t = text.lower()
    if any(k in t for k in _CRYPTO_KW):      return "crypto"
    if any(k in t for k in _WEATHER_KW):     return "weather"
    if any(k in t for k in _SOCCER_KW):      return "soccer"
    if any(k in t for k in _BASKETBALL_KW):  return "basketball"
    if any(k in t for k in _CRICKET_KW):     return "cricket"
    if any(k in t for k in _ESPORTS_KW):     return "esports"
    if any(k in t for k in _FINANCE_KW):     return "finance"
    return "general"
```

Applied to both the news headline and the market question.

### Guard Logic

```python
if mkt_cat != "general" and mkt_cat != news_cat:
    if news_cat != "general" or mkt_cat in _STRICT_CATS:
        skip  # cross-domain
```

Rules:
- **Specific market + specific news of different type** → always skip (e.g. crypto market + soccer news)
- **Specific market + general news** → allow, UNLESS market is in `_STRICT_CATS`
- **`_STRICT_CATS = {"weather"}`** → weather markets ONLY match weather news, never general news
- **General market + any news** → always allow (general markets = politics, AI, world events)

Typical result: 1,000–2,000 cross-category skips per scan (from 158 news × 12 markets = 1,896 pairs tested).

### Keyword Sets

- **Crypto:** bitcoin, btc, ethereum, eth, solana, sol, xrp, bnb, crypto, blockchain, defi, nft, coinbase, binance, polymarket, web3, on-chain
- **Weather:** temperature, celsius, fahrenheit, weather, rain, snow, wind, humidity, forecast, degrees, hottest, coldest
- **Soccer:** fc [space], football club, premier league, champions league, bundesliga, la liga, atletico, barcelona, bayern, liverpool, arsenal, chelsea, manchester, real madrid, juventus, psg
- **Basketball:** nba, 76ers, lakers, celtics, warriors, bucks, heat, knicks, nets, suns, nuggets, magic, bulls, pistons, raptors, spurs, grizzlies, cavaliers, thunder
- **Cricket:** ipl, cricket, wicket, t20, odi, test match, bcci, iplt20, rajasthan royals, mumbai indians, chennai, kolkata, punjab, sunrisers, rcb, delhi capitals
- **Esports:** valorant, counter-strike, cs:go, dota, league of legends, esports, gaming
- **Finance:** stock, nasdaq, s&p, dow jones, fed, federal reserve, interest rate, inflation, recession, earnings, ipo, bond, yield

---

## 10. Demo Mode & Accuracy Tracking

### Demo Trade Flow

```
Signal detected
   → logger.log_trade(..., status="demo")
   → trade stored in trades.db with virtual bet amount
   → NOT sent to Polymarket CLOB (executor.py not called)
```

### Deduplication

Two levels:
1. **Within scan:** `best_per_market` dict keeps only the best-scoring news for each market
2. **Across scans:** `get_pending_market_ids()` returns all market IDs already logged as demo/dry_run — skipped in subsequent scans

This prevents logging the same market 48 times over 24 hours (one entry per scan interval).

### Running Tally

Printed after every scan:
```
Running tally: 7 trades logged | 3 resolved | Accuracy: 66.7% (2W/1L) | Need: 7 more resolutions
```

### Go-Live Criteria

```python
ACCURACY_THRESHOLD = 70.0   # must reach 70%+
MIN_RESOLVED_TRADES = 10    # over at least 10 resolved trades
```

When both are met, the system prints a green banner with instructions to set `DRY_RUN=false`.

---

## 11. Resolution Engine

`resolver.py` runs every `RESOLVE_INTERVAL_MIN=10` minutes.

### Resolution Check Flow

```python
pending = get_pending_demo_trades()  # all demo trades without outcomes
for trade in pending:
    result = check_market_resolution(trade["market_id"])
    # None = still open (skip)
    # 1.0  = YES resolved
    # 0.0  = NO resolved
    # 0.5  = push/invalid
    if result is not None:
        update_outcome(trade, result)
        log_calibration(trade, result)
```

### Win/Loss Determination

| Trade side | Resolution | Outcome |
|------------|-----------|---------|
| YES | Market resolves YES (price=1.0) | WIN |
| YES | Market resolves NO (price=0.0) | LOSS |
| NO | Market resolves YES (price=1.0) | LOSS |
| NO | Market resolves NO (price=0.0) | WIN |
| Either | Push (price=0.5) | PUSH (excluded from accuracy) |

### PnL Calculation (Virtual)

```python
if win:
    pnl = amount_usd * (1.0 / market_price - 1.0)  # Polymarket payout
else:
    pnl = -amount_usd
```

### Gamma API Query

```
GET https://gamma-api.polymarket.com/markets?conditionIds=<id>&limit=1
```

Checks: `closed=true` AND `active=false` → market resolved.
Parses `outcomePrices` (JSON array) where `[1.0, 0.0]` = YES resolved, `[0.0, 1.0]` = NO resolved.

---

## 12. Database Schema

**File:** `/data/trades.db` (Railway persistent volume) or `trades.db` (local)

### `trades` table

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment trade ID |
| market_id | TEXT | Polymarket conditionId |
| market_question | TEXT | Full question text |
| claude_score | REAL | Materiality score (0–1) |
| market_price | REAL | YES price at signal time |
| edge | REAL | Raw edge = materiality × price_room |
| side | TEXT | "YES" or "NO" |
| amount_usd | REAL | Virtual bet size |
| order_id | TEXT | Polymarket order ID (live only) |
| status | TEXT | "demo" / "dry_run" / "filled" / "executed" |
| reasoning | TEXT | LLM reasoning (both passes) |
| headlines | TEXT | News headline that triggered signal |
| created_at | TEXT | ISO timestamp UTC |
| news_source | TEXT | RSS feed name or "twitter" |
| classification | TEXT | "bullish" / "bearish" |
| materiality | REAL | LLM materiality score |
| news_latency_ms | INTEGER | News age in ms |
| classification_latency_ms | INTEGER | LLM inference time |
| total_latency_ms | INTEGER | news_latency + classification_latency |

### `outcomes` table

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| trade_id | INTEGER FK | References trades.id |
| resolved_at | TEXT | ISO timestamp of resolution |
| result | TEXT | "win" / "loss" / "push" |
| pnl | REAL | Virtual profit/loss in USD |

### `calibration` table

Tracks LLM accuracy per classification type, direction, news source.

| Column | Type | Description |
|--------|------|-------------|
| trade_id | INTEGER FK | References trades.id |
| classification | TEXT | "bullish" / "bearish" |
| materiality | REAL | Score at time of prediction |
| entry_price | REAL | YES price at entry |
| exit_price | REAL | YES price at resolution |
| actual_direction | TEXT | "bullish" / "bearish" based on resolution |
| correct | INTEGER | 1=correct, 0=wrong |
| resolved_at | TEXT | Timestamp |

### `pipeline_runs` table

One row per scan cycle: start time, end time, markets scanned, signals found, trades placed.

### `news_events` table

One row per processed headline: headline, source, matched markets count, triggered trades count.

---

## 13. Railway Deployment

### Infrastructure

- **Platform:** Railway.app (Docker container)
- **Build:** `Dockerfile` → Python 3.11 + requirements-railway.txt
- **Process:** `Procfile` → `web: python demo_runner.py`
- **Persistent storage:** Railway volume mounted at `/data` (500MB) — `trades.db` stored here
- **DB path:** `DB_PATH=/data/trades.db` environment variable

### Deploy Commands

```bash
# Push code changes (new Docker image):
railway up --detach

# Restart with new env vars only (no code changes):
# Use Railway GraphQL API: serviceInstanceRedeploy mutation
```

**Critical distinction:**
- `railway up` = uploads code + builds new Docker image + deploys
- `serviceInstanceRedeploy` = restarts existing container only (same image, new env vars)

### Environment Variables

```bash
# LLM
LLM_PROVIDER=gemini
GEMINI_API_KEY=<your-key>
GEMINI_MODEL=gemini-2.0-flash
GROQ_API_KEY=<your-key>          # fallback for 429s

# Trading
BANKROLL_USD=20
MAX_BET_USD=2
DRY_RUN=true                     # change to false for live trading

# Quality filters
MIN_YES_PRICE=0.05
MAX_YES_PRICE=0.95
MIN_VOLUME_USD=500
MIN_CLOSE_HOURS=1.5

# Pipeline
DEMO_HOURS_WINDOW=168            # 7-day market window
SCAN_INTERVAL_MIN=30
RESOLVE_INTERVAL_MIN=10
MAX_PAIRS_PER_SCAN=15
CONSENSUS_PASSES=2               # 2 = Analyst + Skeptic
USE_SEARCH_GROUNDING=false       # Gemini live search (disabled — causes 429s)

# Database
DB_PATH=/data/trades.db          # Railway volume path
```

### Volume Creation (GraphQL API)

The Railway persistent volume was created via GraphQL mutation:
```graphql
mutation {
  volumeCreate(input: {
    environmentId: "<env-id>",
    serviceId: "<service-id>",
    mountPath: "/data",
    sizeMB: 512000
  }) { id name }
}
```

This ensures `trades.db` survives container restarts and code redeployments.

---

## 14. Configuration Reference

All settings are in `config.py` and can be overridden via environment variables.

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `gemini` | Primary LLM backend |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Gemini model ID |
| `BANKROLL_USD` | `20` | Trading bankroll |
| `MAX_BET_USD` | `2` | Max bet per trade |
| `DAILY_LOSS_LIMIT_USD` | `5` | Stop after this much loss/day |
| `DRY_RUN` | `true` | Paper trade only |
| `EDGE_THRESHOLD` | `0.15` | Minimum raw edge to trade |
| `MATERIALITY_THRESHOLD` | `0.30` | Min materiality from LLM |
| `MIN_CLOSE_HOURS` | `1.5` | Skip markets closing in < N hours |
| `MIN_YES_PRICE` | `0.05` | Skip YES < 5% |
| `MAX_YES_PRICE` | `0.95` | Skip YES > 95% |
| `MIN_VOLUME_USD` | `500` | Skip volume < $500 |
| `MIN_WINDOW_HOURS` | `0.5` | Skip < 30min duration markets |
| `DEMO_HOURS_WINDOW` | `168` | Trade markets closing in ≤ 7 days |
| `SCAN_INTERVAL_MIN` | `30` | Re-scan every 30 minutes |
| `RESOLVE_INTERVAL_MIN` | `10` | Check resolutions every 10 minutes |
| `ACCURACY_THRESHOLD` | `70.0` | % accuracy to unlock live trading |
| `MIN_RESOLVED_TRADES` | `10` | Min resolved trades before go-live check |
| `CONSENSUS_ENABLED` | `true` | Enable Analyst + Skeptic debate |
| `CONSENSUS_PASSES` | `2` | Number of LLM passes (1=analyst only, 2=+skeptic) |
| `MAX_PAIRS_PER_SCAN` | `15` | Cap market×news pairs per scan |
| `USE_SEARCH_GROUNDING` | `false` | Gemini live web search (currently disabled) |
| `NEWS_LOOKBACK_HOURS` | `6` | Ignore news older than 6 hours |

---

## 15. Expected Performance

### Trade Volume

| Scenario | Trades/day | Trades/7 days |
|----------|-----------|---------------|
| Low activity (few relevant markets) | 0–2 | 0–14 |
| Normal | 2–8 | 14–56 |
| High activity (major events) | 5–15 | 35–105 |

Conservative estimate: **3–5 trades/day** under normal conditions.

### Time to First Resolution

Most demo trades are logged on markets closing within 24–72 hours:
- First resolutions: ~6–12 hours after first trade logged
- 10 resolved trades needed for go-live: ~3–7 days

### API Cost Estimate (7 days)

Gemini 2.0 Flash pricing (as of 2025):
- Input: $0.075/1M tokens, Output: $0.30/1M tokens

Per scan: 15 pairs × 2 passes × ~600 tokens = 18,000 tokens  
Per day: 48 scans × 18,000 = 864,000 tokens  
Per week: ~6M tokens → **~$0.50–$1.00 total**

Groq (fallback): Free tier is generous (14,400 tokens/minute). Rarely used.

### Expected Accuracy

With consensus (2-pass) + composite ≥ 0.4 + materiality ≥ 0.30:
- Expected win rate: **60–75%** (MiroFish consensus typically adds ~8–12% vs single-pass)
- Required for go-live: **70%** over 10+ trades

---

## 16. Go-Live Criteria

When all conditions below are met, the system prints a green "🚀 READY FOR LIVE TRADING" banner:

1. **≥ 10 trades resolved** (enough sample for statistical confidence)
2. **≥ 70% accuracy** (predictions correct over resolved trades)

To switch to live trading:
1. Set `DRY_RUN=false` in Railway environment variables
2. Ensure `POLYMARKET_PRIVATE_KEY`, `POLYMARKET_API_KEY`, `POLYMARKET_API_SECRET`, `POLYMARKET_API_PASSPHRASE` are set
3. Redeploy via `serviceInstanceRedeploy` (env var change only — no code change needed)

Live trading uses `executor.py` → Polymarket CLOB API → places real limit orders at current market price.

---

*Document covers all changes through V3: multi-signal consensus, Gemini 2.0 Flash + Groq fallback, Railway persistent volume, granular category guard, market quality filters, and deduplication.*
