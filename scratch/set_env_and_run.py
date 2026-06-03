"""Set required env vars and run demo_runner once."""
import os

# Required env vars for live trading
os.environ["DRY_RUN"] = "false"
os.environ["POLYMARKET_PRIVATE_KEY"] = "0xb0984a253593290e99ff725851929c5bed779805d300aa316b9a368727f5498b"
os.environ["POLYMARKET_API_KEY"] = "derive"
os.environ["POLYMARKET_API_SECRET"] = "derive"
os.environ["POLYMARKET_API_PASSPHRASE"] = "derive"
os.environ["POLYMARKET_HOST"] = "https://clob.polymarket.com"
os.environ["WIPE_ON_START"] = "true"
os.environ["BANKROLL_USD"] = "32"
os.environ["MAX_BET_USD"] = "1.50"
os.environ["DAILY_LOSS_LIMIT_USD"] = "15"
os.environ["MAX_AI_CALLS_PER_SCAN"] = "200"
os.environ["MAX_MARKETS_PER_SCAN"] = "500"
os.environ["SCAN_INTERVAL_MIN"] = "2"
os.environ["DEMO_HOURS_WINDOW"] = "336"
os.environ["CLASSIFICATION_MODEL"] = "mimo-v2.5-pro"
os.environ["LLM_PROVIDER"] = "mimo"
os.environ["MIMO_API_KEY"] = "tp-smb26vqnngif8xfg9yumoj1npvc0cr0jjy0csju1rnbc83zz"
os.environ["MIMO_BASE_URL"] = "https://token-plan-sgp.xiaomimimo.com/v1"
os.environ["MIMO_MODEL"] = "mimo-v2.5-pro"
os.environ["GEMINI_API_KEY"] = "AIzaSyB7PRJ9Mqmlk31KbV4P5PJtazmYINRnaN8"
os.environ["GROQ_API_KEY"] = "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"
os.environ["NVIDIA_API_KEY"] = "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"

print(f"DRY_RUN={os.environ['DRY_RUN']}")
print(f"POLYMARKET_HOST={os.environ['POLYMARKET_HOST']}")
print(f"Starting pipeline...")

# Import and run
import demo_runner
demo_runner.main()