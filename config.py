import os
from dotenv import load_dotenv

load_dotenv()

# --- LLM Provider ---
# Recommended: "gemini" (Gemini 2.0 Flash) — works locally AND on Railway, cheap, fast
# Options: "gemini" | "groq" | "anthropic" | "ollama" (local only, no Railway)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()

# --- Anthropic ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# --- Groq ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# --- Google Gemini ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")  # fast + cheap

# --- Ollama ---
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# --- Polymarket CLOB ---
POLYMARKET_API_KEY = os.getenv("POLYMARKET_API_KEY", "")
POLYMARKET_API_SECRET = os.getenv("POLYMARKET_API_SECRET", "")
POLYMARKET_API_PASSPHRASE = os.getenv("POLYMARKET_API_PASSPHRASE", "")
POLYMARKET_PRIVATE_KEY = os.getenv("POLYMARKET_PRIVATE_KEY", "")
POLYMARKET_HOST = "https://clob.polymarket.com"
POLYMARKET_WS_HOST = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

# --- Twitter API v2 ---
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN", "")

# --- Telegram ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_IDS = [
    c.strip() for c in os.getenv("TELEGRAM_CHANNEL_IDS", "").split(",") if c.strip()
]

# --- NewsAPI (optional, RSS fallback) ---
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "")

# --- RSS Feeds (fallback — expanded for broader coverage) ---
RSS_FEEDS = [
    # General / AI / Tech
    "https://news.google.com/rss/search?q=AI+artificial+intelligence&hl=en-US&gl=US&ceid=US:en",
    "https://feeds.feedburner.com/TechCrunch",
    "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "https://www.theverge.com/rss/index.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
    # Crypto
    "https://cointelegraph.com/rss",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    # Politics / World
    "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://news.google.com/rss/search?q=tariff+OR+congress+OR+sanctions&hl=en-US&gl=US&ceid=US:en",
    # Sports (IPL, NBA, NFL, Soccer)
    "https://news.google.com/rss/search?q=IPL+cricket+2026&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=NBA+playoffs+2026&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=NFL+2026&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=Champions+League+soccer+2026&hl=en-US&gl=US&ceid=US:en",
    # Entertainment / Pop culture
    "https://news.google.com/rss/search?q=Oscars+OR+Grammy+OR+Emmy+OR+box+office&hl=en-US&gl=US&ceid=US:en",
    # Science / Space
    "https://news.google.com/rss/search?q=SpaceX+OR+NASA+OR+climate+change&hl=en-US&gl=US&ceid=US:en",
    # Finance / Economy
    "https://news.google.com/rss/search?q=Federal+Reserve+OR+interest+rate+OR+inflation&hl=en-US&gl=US&ceid=US:en",
]

# --- Pipeline Settings (tuned for $20 bankroll) ---
BANKROLL_USD = float(os.getenv("BANKROLL_USD", "20"))
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"
MAX_BET_USD = float(os.getenv("MAX_BET_USD", "2"))         # $2 max per trade on $20 bankroll
DAILY_LOSS_LIMIT_USD = float(os.getenv("DAILY_LOSS_LIMIT_USD", "5"))  # Stop after $5 loss/day
EDGE_THRESHOLD = float(os.getenv("EDGE_THRESHOLD", "0.15"))  # Higher threshold = fewer but better trades
NEWS_LOOKBACK_HOURS = 6

# --- Demo Runner Settings ---
DEMO_HOURS_WINDOW = float(os.getenv("DEMO_HOURS_WINDOW", "24"))       # Only trade markets closing in ≤N hours
SCAN_INTERVAL_MIN = int(os.getenv("SCAN_INTERVAL_MIN", "30"))          # Re-scan every N minutes
RESOLVE_INTERVAL_MIN = int(os.getenv("RESOLVE_INTERVAL_MIN", "10"))    # Check resolutions every N minutes
ACCURACY_THRESHOLD = float(os.getenv("ACCURACY_THRESHOLD", "70.0"))   # % accuracy to unlock live trading
MIN_RESOLVED_TRADES = int(os.getenv("MIN_RESOLVED_TRADES", "10"))      # Min resolved trades needed before going live

# --- V2 Settings ---
MAX_RESOLVE_HOURS = float(os.getenv("MAX_RESOLVE_HOURS", "72"))  # 3 days max
MAX_VOLUME_USD = float(os.getenv("MAX_VOLUME_USD", "500000"))
MIN_VOLUME_USD = float(os.getenv("MIN_VOLUME_USD", "500"))   # Lowered to catch more niche markets
MATERIALITY_THRESHOLD = float(os.getenv("MATERIALITY_THRESHOLD", "0.65"))  # Slightly higher for quality
SPEED_TARGET_SECONDS = float(os.getenv("SPEED_TARGET_SECONDS", "5"))
CLASSIFICATION_MODEL = os.getenv("CLASSIFICATION_MODEL", "gemma3:4b")
SCORING_MODEL = os.getenv("SCORING_MODEL", "gemma3:4b")
# Alias for V1 scorer compatibility
CLAUDE_MODEL = SCORING_MODEL

# --- Consensus Settings (multi-agent inspired by MiroFish debate pattern) ---
CONSENSUS_ENABLED = os.getenv("CONSENSUS_ENABLED", "true").lower() == "true"
CONSENSUS_PASSES = int(os.getenv("CONSENSUS_PASSES", "1"))       # 1 pass for speed
CONSENSUS_MIN_AGREEMENT = float(os.getenv("CONSENSUS_MIN_AGREEMENT", "1.0"))  # 1.0 = unanimous

# --- RRF Multi-Signal Settings (inspired by SkillX fusion scoring) ---
RRF_K = 60  # Reciprocal Rank Fusion constant
SIGNAL_WEIGHTS = {
    "classification": 0.35,   # Claude direction classification
    "materiality": 0.25,      # How material is the news
    "price_room": 0.20,       # Room for price to move
    "volume_niche": 0.10,     # Niche market bonus
    "recency": 0.10,          # News freshness bonus
}

# --- Categories to track (expanded for full coverage) ---
MARKET_CATEGORIES = [
    "ai",
    "technology",
    "crypto",
    "politics",
    "science",
    "sports",
    "entertainment",
    "finance",
    "world",
    "other",
]

# --- Twitter filter keywords (expanded for full coverage) ---
TWITTER_KEYWORDS = [
    # AI / Tech
    "OpenAI", "GPT-5", "Anthropic", "Claude", "Google AI", "Gemini",
    "Apple", "NVIDIA", "Microsoft", "Google", "Meta", "Tesla",
    # Crypto
    "Bitcoin", "Ethereum", "Solana", "crypto", "BTC", "ETH",
    # Politics / World
    "Fed rate", "tariff", "Congress", "White House", "sanctions",
    "Trump", "Biden", "election", "Supreme Court",
    # Sports
    "IPL", "NBA", "NFL", "Champions League", "World Cup",
    "Premier League", "cricket", "playoffs",
    # Science / Space
    "SpaceX", "Starship", "NASA", "climate",
    # Entertainment
    "Oscars", "Grammy", "box office", "Netflix", "Disney",
    # Finance
    "inflation", "interest rate", "recession", "S&P 500", "stock market",
]
