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
MIMO_MODEL          = os.getenv("MIMO_MODEL", "mimo-v2.5-pro")
MIMO_WEB_SEARCH     = os.getenv("MIMO_WEB_SEARCH", "true").lower() == "true"

# ─── Anthropic (optional) ───────────────────────────────────────────────────
ANTHROPIC_API_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
REDDIT_CLIENT_ID    = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_SECRET       = os.getenv("REDDIT_SECRET", "")
TELEGRAM_API_ID     = os.getenv("TELEGRAM_API_ID", "")
TELEGRAM_API_HASH   = os.getenv("TELEGRAM_API_HASH", "")
APIFY_TOKEN         = os.getenv("APIFY_TOKEN", "")

# ─── Twitter ────────────────────────────────────────────────────────────────
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN", "")
TWITTER_KEYWORDS    = [
    "polymarket", "prediction market", "betting odds",
    "crypto regulation", "SEC", "bitcoin ETF", "election",
    "Fed rate", "inflation", "GDP", "war", "tariff",
    "AI regulation", "OpenAI", "FDA approval", "IPO",
]

# ─── Telegram ───────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_IDS = os.getenv("TELEGRAM_CHANNEL_IDS", "").split(",") if os.getenv("TELEGRAM_CHANNEL_IDS") else []

# ─── RSS Feeds ──────────────────────────────────────────────────────────────
RSS_FEEDS = [
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "https://feeds.reuters.com/reuters/topNews",
    "https://feeds.bbci.co.uk/news/business/rss.xml",
    "https://feeds.bbci.co.uk/news/technology/rss.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
    "https://feeds.reuters.com/reuters/businessNews",
    "https://feeds.reuters.com/reuters/technologyNews",
    "https://cointelegraph.com/rss",
    "https://decrypt.co/feed",
    "https://www.theblock.co/rss.xml",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://feeds.nbcnews.com/nbcnews/public/news",
]

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
EDGE_THRESHOLD      = float(os.getenv("EDGE_THRESHOLD", "0.12"))
MATERIALITY_THRESHOLD = float(os.getenv("MATERIALITY_THRESHOLD", "0.45"))
MIN_COMPOSITE_SCORE = float(os.getenv("MIN_COMPOSITE_SCORE", "0.25"))

# Price caps — EXTREME ROI focus: 4x-20x payout only
# YES trades: entry 0.03–0.25 (buy cheap YES, win $1 = 300-3200% ROI)
# NO trades:  entry when YES ≥ 0.75 (NO share ≤ 0.25, win $1 = 300-3200% ROI)
# SKIP: YES price 0.26–0.74 (low ROI either direction — waste of capital)
# At 4x payout, breakeven accuracy = 20%. At 70% accuracy = 3.5x profit.
MAX_BUY_PRICE       = float(os.getenv("MAX_BUY_PRICE", "0.25"))
MAX_YES_ENTRY_PRICE = float(os.getenv("MAX_YES_ENTRY_PRICE", "0.40"))
MIN_YES_ENTRY_PRICE = float(os.getenv("MIN_YES_ENTRY_PRICE", "0.05"))
MIN_NO_ENTRY_PRICE  = float(os.getenv("MIN_NO_ENTRY_PRICE", "0.65"))
MAX_NO_ENTRY_PRICE  = float(os.getenv("MAX_NO_ENTRY_PRICE", "0.97"))
MAX_NO_BUY_PRICE    = float(os.getenv("MAX_NO_BUY_PRICE", "0.25"))

# Dead-zone: skip markets where YES price is between these values (low ROI)
# NARROWED: 0.42-0.58 to let more markets through
DEAD_ZONE_LOW       = float(os.getenv("DEAD_ZONE_LOW", "0.42"))
DEAD_ZONE_HIGH      = float(os.getenv("DEAD_ZONE_HIGH", "0.58"))

# Fast-resolution filter: only take markets resolving within this window
# WIDENED to 168h (7 days) — was 72h which filtered 196 markets!
MAX_HOURS_TO_CLOSE  = float(os.getenv("MAX_HOURS_TO_CLOSE", "168"))

# ─── Volume Filter ───────────────────────────────────────────────────────────
MIN_VOLUME_USD      = float(os.getenv("MIN_VOLUME_USD", "100"))
MAX_VOLUME_USD      = float(os.getenv("MAX_VOLUME_USD", "1000000"))

# ─── LLM Settings ────────────────────────────────────────────────────────────
LLM_PROVIDER        = os.getenv("LLM_PROVIDER", "mimo")
CLASSIFICATION_MODEL = os.getenv("CLASSIFICATION_MODEL", "mimo-v2.5-pro")
GEMINI_MODEL        = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GROQ_MODEL          = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
NVIDIA_MODEL        = os.getenv("NVIDIA_MODEL", "nvidia/llama-3.3-nemotron-super-49b-v1")
OPENAI_MODEL        = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# ─── Consensus Settings ─────────────────────────────────────────────────────
CONSENSUS_ENABLED   = os.getenv("CONSENSUS_ENABLED", "false").lower() == "true"
CONSENSUS_PASSES    = int(os.getenv("CONSENSUS_PASSES", "1"))
CONSENSUS_MIN_AGREEMENT = float(os.getenv("CONSENSUS_MIN_AGREEMENT", "1.0"))
STRICT_CONSENSUS    = os.getenv("STRICT_CONSENSUS", "true").lower() == "true"

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
SCAN_INTERVAL_MIN   = int(os.getenv("SCAN_INTERVAL_MIN", "3"))
RESOLVE_INTERVAL_MIN = int(os.getenv("RESOLVE_INTERVAL_MIN", "2"))
MAX_MARKETS_PER_SCAN = int(os.getenv("MAX_MARKETS_PER_SCAN", "500"))
MAX_AI_CALLS_PER_SCAN = int(os.getenv("MAX_AI_CALLS_PER_SCAN", "300"))

# ─── Demo / Go-Live ─────────────────────────────────────────────────────────
ACCURACY_THRESHOLD  = float(os.getenv("ACCURACY_THRESHOLD", "65"))
MIN_RESOLVED        = int(os.getenv("MIN_RESOLVED", "30"))
DEMO_HOURS_WINDOW   = float(os.getenv("DEMO_HOURS_WINDOW", "168"))

# ─── Speed Target ───────────────────────────────────────────────────────────
SPEED_TARGET_SECONDS = float(os.getenv("SPEED_TARGET_SECONDS", "5"))

# ─── News Settings ───────────────────────────────────────────────────────
NEWS_LOOKBACK_HOURS = int(os.getenv("NEWS_LOOKBACK_HOURS", "72"))

# ─── Paths ───────────────────────────────────────────────────────────────────
PROJECT_ROOT        = Path(__file__).parent
LOG_FILE            = PROJECT_ROOT / "polymarket_bot.log"
