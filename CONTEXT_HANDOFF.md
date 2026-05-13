# Context Handoff — Polymarket Pipeline

## Current State (2026-05-12 03:30 IST)

### ✅ What's Working
- **Pipeline is LIVE** on Railway `industrious-blessing` project
- **Dashboard** at https://demo-runner-production-3f90.up.railway.app — serving correctly, LLM provider info shows "Mimo / nebula-ai-3"
- **Scanning** every 5 min, finding ~20 candidates per cycle, making 6 AI calls
- **News scraper** active (1400+ headlines)
- **Price feeds** active (CoinGecko 27 prices)
- **API keys** all working (Gemini 2.5 Flash, MIMO nebula-ai-3)
- **BANKROLL_USD** set to $30 via Railway env

### 🔄 Current Issue — Zero Trades
Pipeline scans but places **zero trades**. This is **expected behavior** for a fresh deployment:
- Fresh DB = 0 historical trades, 0 resolved
- Accuracy gate: "need 20 more to go-live"
- Of ~20 candidates per scan, 12 blocked by `hard_blocklist` (O/U, spreads, player props)
- 2 skipped by `dead_zone_31_49` (31-49% probability range)
- Remaining ~6 get AI calls but don't pass consensus gate (no strong signal)
- **This is correct selectivity** — the system won't trade garbage

The old 3f90 project had 62 trades accumulated over time. This new project needs time to accumulate trades.

### 📊 What Needs to Happen
1. **Wait for trades** — Pipeline needs to find high-confidence setups (≥70% AI confidence + consensus agreement)
2. **Trades will accumulate slowly** — the system is deliberately selective
3. **After 20 resolved trades** — accuracy gate unlocks for full go-live
4. **Monitor via dashboard** — trades will appear in the Trades tab when placed

### 🏗️ Architecture
- **Deploy**: Railway (Dockerfile + railway.toml)
- **Runner**: `python demo_runner.py` (per Procfile)
- **Dashboard**: `web_dashboard.py` (Flask, port 5000)
- **DB**: SQLite at `data/demo_runner.db` (Railway volume `/data`)
- **Scanner interval**: 5 min
- **Resolve interval**: 5 min
- **Window**: ≤30h
- **Max AI calls/scan**: 60
- **Min bet**: $3.00
- **Max bet**: $4.50

### 🔑 Environment Variables (Railway)
- `GEMINI_API_KEY` — ✅ working
- `MIMO_API_KEY` — ✅ working (via NeuraLabs)
- `PGPASSWORD_SECRET` — ✅
- `TG_PHONE`, `TG_API_ID`, `TG_API_HASH` — ✅
- `APIFY_TOKEN` — ✅
- `BANKROLL_USD` — Set to 30
- `POLY_ADDRESS`, `POLY_SECRET` — need to verify they're set for real trading

### 📝 Recent Git Commits
- `bede4ca` — Mimo / NeuraLabs provider support + BANKROLL_USD=30
- `11b0cb8` — Bankroll optimization
- `70ae20a` — Cleanup & deploy fixes

### ⚠️ Known Issues (Non-blocking)
- `asyncio: Event loop is closed` errors every scan cycle (httpx client cleanup, cosmetic)
- Old `3f90` project may still be running (check for duplicate scans)
- `polymarket_bot.log` warnings about Pyrogram session (expected)