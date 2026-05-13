"""
Configuration settings for Polymarket trading pipeline.
V2: Added multi-signal analysis, consensus, RRF scoring, dynamic weights.
V3: Hardened thresholds for accuracy — materiality ≠ probability.
"""
import os
from pathlib import Path

# ─── API Keys ────────────────────────────────────────────────────────────────
POLY_API_KEY        = os.getenv("POLY_API_KEY", "")
POLY_SECRET         = os.getenv("POLY_SECRET", "")
POLY_PASSPHRASE     = os.getenv("POLY_PASSPHRASE", "")

# Polymarket CLOB client names (executor.py uses these)
POLYMARKET_API_KEY    = os.getenv("POLYMARKET_API_KEY", os.getenv("POLY_API_KEY", ""))
POLYMARKET_PRIVATE_KEY = os.getenv("POLYMARKET_PRIVATE_KEY", os.getenv("POLY_PRIVATE_KEY", ""))
POLYMARKET_API_SECRET = os.getenv("POLYMARKET_API_SECRET", os.getenv("POLY_SECRET", ""))
POLYMARKET_API_PASSPHRASE = os.getenv("POLYMARKET_API_PASSPHRASE", os.getenv("POLY_PASSPHRASE", ""))
GEMINI_API_KEY      = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY        = os.getenv("GROQ_API_KEY", "")
NVIDIA_API_KEY      = os.getenv("NVIDIA_API_KEY", "")
OPENAI_API_KEY      = os.getenv("OPENAI_API_KEY", "")
NEWSAPI_KEY         = os.getenv("NEWSAPI_KEY", "")

# ─── Xiaomi MiMo ────────────────────────────────────────────────────────────
MIMO_API_KEY        = os.getenv("MIMO_API_KEY", "")
MIMO_BASE_URL       = os.getenv("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1")
MIMO_MODEL          = os.getenv("MIMO_MODEL", "MiMo-V2.5-Pro")
MIMO_WEB_SEARCH     = os.getenv("MIMO_WEB_SEARCH", "true").lower() == "true"

# ─── Anthropic (optional) ───────────────────────────────────────────────────
ANTHROPIC_API_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
REDDIT_CLIENT_ID    = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_SECRET       = os.getenv("REDDIT_SECRET", "")
TELEGRAM_API_ID     = os.getenv("TELEGRAM_API_ID", "")
TELEGRAM_API_HASH   = os.getenv("TELEGRAM_API_HASH", "")
APIFY_TOKEN         = os.getenv("APIFY_TOKEN", "")

# ─── Database ────────────────────────────────────────────────────────────────
# On Railway: /data/bot.db (persistent volume)
# Locally: ./bot.db
DB_PATH = os.getenv("DB_PATH", "/data/trades.db" if os.path.exists("/data") else "./trades.db")

# ─── Polymarket API ─────────────────────────────────────────────────────────
POLYMARKET_HOST     = os.getenv("POLYMARKET_HOST", "https://clob.polymarket.com")

# ─── Trading Parameters ─────────────────────────────────────────────────────
DRY_RUN             = os.getenv("DRY_RUN", "true").lower() == "true"
BANKROLL_USD        = float(os.getenv("BANKROLL_USD", "100"))
MAX_BET_USD         = float(os.getenv("MAX_BET_USD", "2.0"))
MIN_BET_USD         = 0.50
TRADES_PER_DAY      = int(os.getenv("TRADES_PER_DAY", "20"))
DAILY_LOSS_LIMIT_USD = float(os.getenv("DAILY_LOSS_LIMIT_USD", "10"))

# ─── Edge / Scoring Thresholds (HARDENED) ────────────────────────────────────
# These are the MINIMUM requirements for a trade to fire
EDGE_THRESHOLD      = float(os.getenv("EDGE_THRESHOLD", "0.08"))
MATERIALITY_THRESHOLD = float(os.getenv("MATERIALITY_THRESHOLD", "0.45"))
MIN_COMPOSITE_SCORE = float(os.getenv("MIN_COMPOSITE_SCORE", "0.40"))

# Price caps — YES ≤ 35¢, NO only when YES ≥ 55¢
MAX_BUY_PRICE       = float(os.getenv("MAX_BUY_PRICE", "0.35"))
MAX_YES_ENTRY_PRICE = float(os.getenv("MAX_YES_ENTRY_PRICE", "0.35"))
MIN_NO_ENTRY_PRICE  = float(os.getenv("MIN_NO_ENTRY_PRICE", "0.55"))
MAX_NO_BUY_PRICE    = float(os.getenv("MAX_NO_BUY_PRICE", "0.45"))

# ─── Volume Filter ───────────────────────────────────────────────────────────
MIN_VOLUME_USD      = float(os.getenv("MIN_VOLUME_USD", "50"))
MAX_VOLUME_USD      = float(os.getenv("MAX_VOLUME_USD", "2000000"))

# ─── LLM Settings ────────────────────────────────────────────────────────────
LLM_PROVIDER        = os.getenv("LLM_PROVIDER", "mimo")
CLASSIFICATION_MODEL = os.getenv("CLASSIFICATION_MODEL", "MiMo-V2.5-Pro")
GEMINI_MODEL        = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GROQ_MODEL          = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
NVIDIA_MODEL        = os.getenv("NVIDIA_MODEL", "nvidia/llama-3.3-nemotron-super-49b-v1")
OPENAI_MODEL        = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# ─── Consensus Settings ─────────────────────────────────────────────────────
CONSENSUS_ENABLED   = os.getenv("CONSENSUS_ENABLED", "true").lower() == "true"
CONSENSUS_PASSES    = int(os.getenv("CONSENSUS_PASSES", "2"))
CONSENSUS_MIN_AGREEMENT = float(os.getenv("CONSENSUS_MIN_AGREEMENT", "1.0"))
STRICT_CONSENSUS    = os.getenv("STRICT_CONSENSUS", "false").lower() == "true"

# ─── Signal Weights (RRF Composite) ─────────────────────────────────────────
SIGNAL_WEIGHTS = {
    "classification": 0.30,   # AI direction confidence
    "materiality":    0.25,   # How relevant the news is
    "price_room":     0.20,   # Room for price to move
    "volume_niche":   0.10,   # Lower volume = less efficient = more edge
    "recency":        0.15,   # News freshness
}

# ─── Dynamic Weight Ranges ───────────────────────────────────────────────────
DYNAMIC_WEIGHT_RANGES = {
    "pf":     (0.03, 0.12),
    "copy":   (0.03, 0.10),
    "whale":  (0.02, 0.08),
    "ai":     (0.08, 0.25),
    "crowd":  (0.01, 0.05),  # crowd signal DISABLED (29% accuracy)
    "consensus": (0.05, 0.15),
}

# ─── Market Filters ──────────────────────────────────────────────────────────
SCAN_INTERVAL_MIN   = int(os.getenv("SCAN_INTERVAL_MIN", "5"))
RESOLVE_INTERVAL_MIN = int(os.getenv("RESOLVE_INTERVAL_MIN", "2"))
MAX_MARKETS_PER_SCAN = int(os.getenv("MAX_MARKETS_PER_SCAN", "400"))
MAX_AI_CALLS_PER_SCAN = int(os.getenv("MAX_AI_CALLS_PER_SCAN", "120"))

# ─── Demo / Go-Live ─────────────────────────────────────────────────────────
ACCURACY_THRESHOLD  = float(os.getenv("ACCURACY_THRESHOLD", "55"))
MIN_RESOLVED        = int(os.getenv("MIN_RESOLVED", "30"))
DEMO_HOURS_WINDOW   = float(os.getenv("DEMO_HOURS_WINDOW", "30"))

# ─── Paths ───────────────────────────────────────────────────────────────────
PROJECT_ROOT        = Path(__file__).parent
LOG_FILE            = PROJECT_ROOT / "polymarket_bot.log"