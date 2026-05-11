# Context Handoff — Polymarket Pipeline

## Current State (2026-05-12 ~14:30 IST)
- **Status**: Running on Railway (Production deployment, ID: `3f90`)
- **Mode**: DRY_RUN=True (trial/demo mode)
- **Railway Services**: 
  - Pipeline: `polymarket-pipeline-production-3f90`
  - Cron: `polymarket-cron-production-3f90`

## CRON JOBS (AUTO-SCHEDULER)
The cron service runs two jobs automatically:
1. **demo_runner** — every 5 min (`*/5 * * * *`)
   - Scans markets → generates signals → places DRY_RUN trades → resolves
   - Command: `python demo_runner.py scan`
2. **resolve_trades** — every 6 min (`*/6 * * * *`)
   - Only resolves pending trades
   - Command: `python resolve_trades.py`

**DO NOT start long-running processes** — use one-shot commands only.

## Latest Fixes (Just Deployed)

### Dashboard Gate Logic Fix
- **Problem**: Gate Status showed "OPEN" (green) even at 44.8% accuracy because it only checked `can_trade_today()` (daily loss limit), not accuracy
- **Fix**: Added `can_go_live` field that checks BOTH accuracy >= 80% AND resolved >= 20 trades
- Gate now shows "ACCUMULATING" (yellow) when not yet ready, with tooltip showing what's needed

### Position Sizing Fix
- **Problem**: Kelly sizing allowed $3.76-$4.05 bets despite `MAX_BET_USD=1` config
- **Root cause**: `kelly_bet_size()` in bankroll.py only used `MAX_BET_FRAC` (7% of bankroll), not the `MAX_BET_USD` config value
- **Fix**: Added `MAX_BET_USD` hard cap that caps Kelly output at $1 (or whatever config says)
- On $95 bankroll: Kelly would bet $6.65 (7%), now capped at $1

### Strategy Leaderboard Fix
- **Problem**: Showed "•  trades" with blank number
- **Root cause**: Template used `st.total` but dict returns `st.trades`
- **Fix**: Changed to `st.trades` in template

## Key Rules
- Use `timeout 120` for ALL Railway commands
- Always `--no-input -y` on Railway CLI
- One-shot commands only (never long-running processes)
- Read-only DB queries on Railway (no writes)

## Database Schema
Tables: trades, outcomes, news_events, pipeline_runs
- `outcomes`: trade_id, result, pnl, resolved_at, closing_price, source, reason

## What Was Done This Session
1. Full accuracy analysis: 28W/34L = 44.8% win rate, $1.49 net profit
2. Fixed dashboard gate to check accuracy threshold (80%) not just daily loss limit
3. Fixed Kelly bet sizing to respect MAX_BET_USD hard cap ($1)
4. Fixed strategy leaderboard trade count display

## Next Steps
- Monitor next trades to verify $1 max bet is enforced
- Track accuracy improvement as more trades resolve
- Consider relaxing `MAX_NO_ENTRY_PRICE` (0.50) to widen entry zone
- Consider relaxing `MATERIALITY_THRESHOLD` (0.55) to allow more trades
- Dashboard: https://demo-runner-production-3f90.up.railway.app