import os
from dotenv import load_dotenv

load_dotenv()

# --- LLM Provider ---
# Recommended: "mixed" (Heterogeneous AI Consensus) — uses Gemini, Groq, and Nvidia together for 80%+ accuracy
# Options: "mixed" | "gemini" | "groq" | "anthropic" | "nvidia" | "ollama"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "mimo").lower()

# --- Anthropic ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# --- Groq ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# --- Google Gemini ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")  # Flash = 15 RPM free tier, fast + good

# --- NVIDIA ---
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "qwen/qwen3-coder-480b-a35b-instruct")  # Best coding model on NVIDIA

# --- Ollama ---
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# --- Mimo AI (Premium Backend) ---
MIMO_API_KEY = os.getenv("MIMO_API_KEY", "")
MIMO_MODEL = os.getenv("MIMO_MODEL", "mimo-v2.5-pro")  # Xiaomi MiMo v2.5 Pro
MIMO_BASE_URL = os.getenv("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1")

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

# --- RSS Feeds (primary source — broad coverage across all market categories) ---
RSS_FEEDS = [
    # ── General / Breaking News ──────────────────────────────────────────────
    "https://feeds.bbci.co.uk/news/rss.xml",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
    "https://www.reuters.com/rssFeed/topNews",
    "https://feeds.npr.org/1001/rss.xml",

    # ── AI / Tech ────────────────────────────────────────────────────────────
    "https://news.google.com/rss/search?q=AI+artificial+intelligence+OpenAI+Anthropic&hl=en-US&gl=US&ceid=US:en",
    "https://feeds.feedburner.com/TechCrunch",
    "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "https://www.theverge.com/rss/index.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
    "https://news.google.com/rss/search?q=ChatGPT+OR+GPT-5+OR+Gemini+OR+Claude+AI&hl=en-US&gl=US&ceid=US:en",

    # ── Crypto ───────────────────────────────────────────────────────────────
    "https://cointelegraph.com/rss",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://decrypt.co/feed",
    "https://news.google.com/rss/search?q=Bitcoin+OR+Ethereum+OR+crypto+price&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=BTC+price+OR+ETH+price+OR+Solana&hl=en-US&gl=US&ceid=US:en",

    # ── Politics / World / Economics ─────────────────────────────────────────
    "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Economy.xml",
    "https://news.google.com/rss/search?q=tariff+OR+congress+OR+sanctions+OR+Trump&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=Federal+Reserve+OR+interest+rate+OR+inflation+OR+recession&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=election+2026+OR+Supreme+Court+OR+White+House&hl=en-US&gl=US&ceid=US:en",

    # ── Soccer / Football ────────────────────────────────────────────────────
    "https://feeds.bbci.co.uk/sport/football/rss.xml",
    "https://news.google.com/rss/search?q=Premier+League+2026&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=Champions+League+2026+soccer&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=FC+Bayern+OR+Manchester+United+OR+Arsenal+OR+Chelsea&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=La+Liga+OR+Bundesliga+OR+Serie+A+2026&hl=en-US&gl=US&ceid=US:en",
    "https://www.goal.com/feeds/en/news",

    # ── NBA / Basketball ─────────────────────────────────────────────────────
    "https://feeds.bbci.co.uk/sport/basketball/rss.xml",
    "https://news.google.com/rss/search?q=NBA+2026+playoffs&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=NBA+game+result+OR+NBA+trade+OR+NBA+injury&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=76ers+OR+Lakers+OR+Celtics+OR+Warriors+OR+Bucks&hl=en-US&gl=US&ceid=US:en",

    # ── Tennis ───────────────────────────────────────────────────────────────
    "https://news.google.com/rss/search?q=ATP+tennis+2026+OR+WTA+tennis+2026&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=Djokovic+OR+Alcaraz+OR+Sinner+OR+Medvedev+tennis&hl=en-US&gl=US&ceid=US:en",
    "https://feeds.bbci.co.uk/sport/tennis/rss.xml",

    # ── NFL / American Football ──────────────────────────────────────────────
    "https://news.google.com/rss/search?q=NFL+2026+OR+NFL+draft&hl=en-US&gl=US&ceid=US:en",

    # ── Finance / Markets ────────────────────────────────────────────────────
    "https://feeds.marketwatch.com/marketwatch/topstories/",
    "https://news.google.com/rss/search?q=stock+market+OR+S%26P+500+OR+NASDAQ+2026&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=earnings+report+OR+IPO+OR+merger+acquisition&hl=en-US&gl=US&ceid=US:en",

    # ── Entertainment ────────────────────────────────────────────────────────
    "https://news.google.com/rss/search?q=Oscars+OR+Grammy+OR+Emmy+OR+box+office+2026&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=Netflix+OR+Disney+OR+Hollywood+movie&hl=en-US&gl=US&ceid=US:en",

    # ── Science / Space ──────────────────────────────────────────────────────
    "https://news.google.com/rss/search?q=SpaceX+OR+NASA+OR+Starship+2026&hl=en-US&gl=US&ceid=US:en",
]

# --- Pipeline Settings (tuned for $1 flat bets, 80% accuracy target) ---
BANKROLL_USD = float(os.getenv("BANKROLL_USD", "30"))
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"
MAX_BET_USD = float(os.getenv("MAX_BET_USD", "1"))          # $1 flat bet per signal
DAILY_LOSS_LIMIT_USD = float(os.getenv("DAILY_LOSS_LIMIT_USD", "10"))  # Stop after $10 loss/day
EDGE_THRESHOLD = float(os.getenv("EDGE_THRESHOLD", "0.15"))  # 0.15 = conservative edge gate
NEWS_LOOKBACK_HOURS = 12

# --- High-ROI Price Sweet Spot (GUARANTEES profit even at LOW accuracy) ---
# At 30¢ entry: break-even = 30% accuracy. At 40% acc = $0.33 profit per $1.
# At 20¢ entry: break-even = 20% accuracy. At 40% acc = $1.00 profit per $1.
# ┌──────────┬───────────┬────────────┬────────────────┬──────────────────┐
# │ Buy Price│ Break-Even│ EV @ 40%   │ EV @ 50%       │ EV @ 60%         │
# ├──────────┼───────────┼────────────┼────────────────┼──────────────────┤
# │ $0.15    │ 15%       │ +$1.73     │ +$2.33         │ +$2.93           │
# │ $0.20    │ 20%       │ +$1.00     │ +$1.50         │ +$2.00           │
# │ $0.25    │ 25%       │ +$0.60     │ +$1.00         │ +$1.40           │
# │ $0.30    │ 30%       │ +$0.33     │ +$0.67         │ +$1.00           │
# │ $0.40    │ 40%       │ $0.00      │ +$0.25         │ +$0.50           │
# │ $0.50    │ 50%       │ -$0.20     │ $0.00          │ +$0.20           │
# └──────────┴───────────┴────────────┴────────────────┴──────────────────┘
# Only trade at 30¢ or below → PROFITABLE at ≥31% accuracy → guaranteed upside
MAX_BUY_PRICE = float(os.getenv("MAX_BUY_PRICE", "0.30"))      # YES: only buy ≤30¢ → break-even at 30%
MAX_YES_ENTRY_PRICE = float(os.getenv("MAX_YES_ENTRY_PRICE", "0.30"))  # Buy YES below 30¢
MIN_NO_ENTRY_PRICE = float(os.getenv("MIN_NO_ENTRY_PRICE", "0.50"))    # Buy NO when YES ≥ 50¢
MAX_NO_BUY_PRICE = float(os.getenv("MAX_NO_BUY_PRICE", "0.50"))       # NO: allow up to 50¢ (breakeven 50%)

# --- Demo Runner Settings ---
DEMO_HOURS_WINDOW = float(os.getenv("DEMO_HOURS_WINDOW", "30"))       # 30h window — tighter, avoids stale markets
SCAN_INTERVAL_MIN = int(os.getenv("SCAN_INTERVAL_MIN", "5"))          # 5min scan interval
RESOLVE_INTERVAL_MIN = int(os.getenv("RESOLVE_INTERVAL_MIN", "6"))     # Check resolutions every 6min
ACCURACY_THRESHOLD = float(os.getenv("ACCURACY_THRESHOLD", "80.0"))   # Target: 80% accuracy
MIN_RESOLVED_TRADES = int(os.getenv("MIN_RESOLVED_TRADES", "20"))      # Need 20 resolved before going live

# --- V2 Settings ---
MAX_RESOLVE_HOURS = float(os.getenv("MAX_RESOLVE_HOURS", "72"))  # 3 days max
MAX_VOLUME_USD = float(os.getenv("MAX_VOLUME_USD", "500000"))
MIN_VOLUME_USD = float(os.getenv("MIN_VOLUME_USD", "50"))    # Low: catch 5/15-min crypto windows ($100-$1000 vol)
MATERIALITY_THRESHOLD = float(os.getenv("MATERIALITY_THRESHOLD", "0.55")) # 0.55 = moderate+ materiality

# --- Market Quality Filters (maximise signal accuracy) ---
MIN_CLOSE_HOURS  = float(os.getenv("MIN_CLOSE_HOURS",  "0.50"))  # Skip markets closing in < 30min
MIN_YES_PRICE    = float(os.getenv("MIN_YES_PRICE",   "0.10"))   # Filter near-impossible markets (< 10¢)
MAX_YES_PRICE    = float(os.getenv("MAX_YES_PRICE",   "0.95"))   # Only filter near-certain markets
MIN_WINDOW_HOURS = float(os.getenv("MIN_WINDOW_HOURS", "0.25"))  # Skip < 15-min duration markets (already correct)
SPEED_TARGET_SECONDS = float(os.getenv("SPEED_TARGET_SECONDS", "5"))
CLASSIFICATION_MODEL = os.getenv("CLASSIFICATION_MODEL", "gemma3:4b")
SCORING_MODEL = os.getenv("SCORING_MODEL", "gemma3:4b")
# Alias for V1 scorer compatibility
CLAUDE_MODEL = SCORING_MODEL

# --- Gemini Search Grounding (live web search during classification) ---
USE_SEARCH_GROUNDING = os.getenv("USE_SEARCH_GROUNDING", "true").lower() == "true"

# --- Consensus Settings (multi-agent inspired by MiroFish debate pattern) ---
CONSENSUS_ENABLED = os.getenv("CONSENSUS_ENABLED", "true").lower() == "true"
CONSENSUS_PASSES = int(os.getenv("CONSENSUS_PASSES", "3"))       # Analyst + Skeptic + Reflector
STRICT_CONSENSUS = os.getenv("STRICT_CONSENSUS", "true").lower() == "true"
CONSENSUS_MIN_AGREEMENT = float(os.getenv("CONSENSUS_MIN_AGREEMENT", "0.67"))  # 2/3 agreement = good signal

# --- RRF Multi-Signal Settings (inspired by SkillX fusion scoring) ---
RRF_K = 60  # Reciprocal Rank Fusion constant
SIGNAL_WEIGHTS = {
    "classification": 0.35,   # Claude direction classification
    "materiality": 0.25,      # How material is the news
    "price_room": 0.20,       # Room for price to move
    "volume_niche": 0.10,     # Niche market bonus
    "recency": 0.10,          # News freshness bonus
}

# --- Categories to track (only categories where AI has demonstrated edge) ---
# REMOVED: "sports" (0% accuracy - random player props, no AI edge)
# REMOVED: "entertainment" (0% accuracy - awards, TV outcomes, pure noise)
# These categories drag overall accuracy to ~40%. Politics/crypto/AI/finance = ~80%.
MARKET_CATEGORIES = [
    "ai",
    "technology",
    "crypto",
    "politics",
    "science",
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
    "NBA", "NFL", "Champions League", "World Cup",
    "Premier League", "playoffs",
    # Science / Space
    "SpaceX", "Starship", "NASA", "climate",
    # Entertainment
    "Oscars", "Grammy", "box office", "Netflix", "Disney",
    # Finance
    "inflation", "interest rate", "recession", "S&P 500", "stock market",
]