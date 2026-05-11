# Polymarket Pipeline — Context Handoff

> **Read this file first when starting a new Cline conversation.**
> Just say: "Read CONTEXT_HANDOFF.md and continue where we left off."

---

## Current State (as of 2026-05-11 14:45 IST)

### Pipeline Performance
- **Accuracy**: 82.9% (24W / 5L) — exceeds 80% target ✅
- **Virtual PnL**: $11.43 across 29 resolved trades
- **Mode**: DRY_RUN (virtual trades only)
- **Dashboard**: https://demo-runner-production-3f90.up.railway.app/

### Railway Deployment
- **Service name**: `demo-runner`
- **Deploy command**: `railway up --service demo-runner`
- **Git push**: `git push origin main` (triggers auto-deploy if connected)
- **Procfile**: `web: python3.11 run_both.py` (runs pipeline + dashboard together)
- **Last commit**: Blocklist fix (relaxed vs/moneyline/cricket/tournament blocks)

### MiMo API Config (Cline model)
- **Config file**: `cline-mimo-config.json`
- **Model**: `mimo-v2.5-pro` (Xiaomi's best)
- **API base**: `https://token-plan-sgp.xiaomimimo.com/v1`
- **API key**: `tp-smb26vqnngif8xfg9yumoj1npvc0cr0jjy0csju1rnbc83zz`
- **maxTokens**: 32768 (increased for better experience, only 1% of quota used)
- **Token quota**: 700M total, ~1% used

### Coding Config (Qwen3)
- **Config file**: `cline-coding-config.json`
- **Model**: `qwen/qwen3-coder-480b-a35b-instruct` on NVIDIA
- **maxTokens**: 32768 (increased)

---

## Recent Changes Made

### 1. Blocklist Fix (`demo_runner.py`)
Removed over-aggressive keyword blocking in `HARD_SKIP` list:
- **Removed**: `" vs. "`, `" vs "`, `"moneyline"`, `"1h moneyline"` — AI consensus handles these
- **Removed**: 18 cricket team patterns (`"will cf "`, `"will ca "`, etc.) — caught legitimate cricket markets
- **Removed**: `"win the 2025/2026/2027"`, `"finish in the top"` — over-broad tournament blocks
- **Kept**: Only truly broken/empty question patterns

### 2. Config Changes
- Both `cline-mimo-config.json` and `cline-coding-config.json` updated with `maxTokens: 32768`
- MiMo model upgraded from `mimo-v2-omni` → `mimo-v2.5-pro`

---

## Known Issues

### Dashboard Shows 0 Stats on Railway
The Railway deployment has its own SQLite DB (`polymarket.db`) which is empty. The 82.9% accuracy stats are from the LOCAL database. Railway will populate as the pipeline runs live.

### Cricket API Errors
ESPN (403) and Cricbuzz (404) APIs fail when no IPL matches are live. This is expected — the pipeline falls back to Polymarket's Gamma API for non-cricket markets.

### Blocklist May Still Be Too Aggressive
If trades aren't appearing after deployment, check Railway logs. The remaining `HARD_SKIP` patterns in `demo_runner.py` may need further loosening. Key patterns to watch:
- `"world of "` — blocks too many legitimate markets
- `", the"` — overly broad

---

## Architecture Quick Reference

| File | Purpose |
|------|---------|
| `demo_runner.py` | Main loop — market discovery, AI consensus, trade execution |
| `classifier.py` | LLM-based market categorization (uses MiMo/Groq) |
| `edge.py` | Edge calculation (polymarket vs true probability) |
| `bankroll.py` | Virtual bankroll, position sizing, PnL tracking |
| `resolver.py` | Resolves trades when markets closed, tracks accuracy |
| `web_dashboard.py` | Flask dashboard served on Railway |
| `run_both.py` | Launches pipeline + dashboard together |
| `markets.py` | Fetches markets from Polymarket Gamma API |
| `logger.py` | SQLite DB management (`polymarket.db`) |
| `config.py` | Configuration constants |
| `pipeline.py` | Core trade pipeline orchestration |

---

## Commands Reference

```bash
# Deploy to Railway
railway up --service demo-runner

# Git workflow
git add .; git commit -m "msg"; git push origin main

# Check local stats
python scratch/check_stats.py

# Check Railway logs
railway logs --service demo-runner

# Run locally
python run_both.py