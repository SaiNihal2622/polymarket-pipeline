#!/usr/bin/env python3
"""Check if the pipeline is configured for real-money trading."""
import os
from dotenv import load_dotenv
load_dotenv()

print("=" * 60)
print("  POLYMARKET PIPELINE — LIVE TRADING READINESS CHECK")
print("=" * 60)

# 1. .env file exists
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
env_exists = os.path.exists(env_path)
print(f"\n{'✅' if env_exists else '❌'} .env file exists: {env_exists}")

# 2. DRY_RUN setting
dry_run = os.getenv("DRY_RUN", "true").lower()
print(f"{'🔴' if dry_run == 'false' else '🟢'} DRY_RUN = {dry_run} ({'LIVE MODE' if dry_run == 'false' else 'DRY RUN (safe)'})")

# 3. Polymarket API credentials
api_key = os.getenv("POLYMARKET_API_KEY", "")
priv_key = os.getenv("POLYMARKET_PRIVATE_KEY", "")
api_secret = os.getenv("POLYMARKET_API_SECRET", "")
api_pass = os.getenv("POLYMARKET_API_PASSPHRASE", "")

print(f"{'✅' if api_key else '❌'} POLYMARKET_API_KEY = {'SET (' + api_key[:8] + '...)' if api_key else 'NOT SET'}")
print(f"{'✅' if priv_key else '❌'} POLYMARKET_PRIVATE_KEY = {'SET (' + priv_key[:8] + '...)' if priv_key else 'NOT SET'}")
print(f"{'✅' if api_secret else '❌'} POLYMARKET_API_SECRET = {'SET (' + api_secret[:8] + '...)' if api_secret else 'NOT SET'}")
print(f"{'✅' if api_pass else '❌'} POLYMARKET_API_PASSPHRASE = {'SET (' + api_pass[:8] + '...)' if api_pass else 'NOT SET'}")

# 4. Bankroll settings
bankroll = os.getenv("BANKROLL_USD", "100")
max_bet = os.getenv("MAX_BET_USD", "2.0")
daily_limit = os.getenv("DAILY_LOSS_LIMIT_USD", "20")
print(f"\n💰 BANKROLL_USD = ${bankroll}")
print(f"💰 MAX_BET_USD = ${max_bet}")
print(f"💰 DAILY_LOSS_LIMIT_USD = ${daily_limit}")

# 5. Real trades flag
real_trades = os.getenv("REAL_TRADES_ENABLED", "false").lower()
print(f"{'🔴' if real_trades == 'true' else '🟢'} REAL_TRADES_ENABLED = {real_trades}")

# 6. Check py_clob_client
try:
    from py_clob_client.client import ClobClient
    print(f"\n✅ py_clob_client installed")
except ImportError:
    print(f"\n❌ py_clob_client NOT installed (pip install py-clob-client)")

# 7. Brave wallet check
print("\n" + "=" * 60)
print("  BRAVE WALLET / PRIVATE KEY ANALYSIS")
print("=" * 60)
if priv_key:
    clean = priv_key.replace("0x", "").replace("0X", "")
    print(f"  Private key length: {len(clean)} hex chars")
    if len(clean) == 64:
        print(f"  ✅ Valid Ethereum private key format (32 bytes)")
    else:
        print(f"  ⚠️  Unexpected length (expected 64 hex chars)")
    print(f"  This key will be used as the 'funder' in ClobClient")
    print(f"  The ClobClient uses this to sign orders on Polygon (chain_id=137)")
else:
    print("  ❌ No private key set")
    print("  To trade with your Brave wallet:")
    print("  1. Export your private key from Brave Wallet")
    print("  2. Set POLYMARKET_PRIVATE_KEY in .env")

# 8. Summary
print("\n" + "=" * 60)
can_trade_live = (
    dry_run == "false"
    and api_key
    and priv_key
    and api_secret
    and api_pass
)
if can_trade_live:
    print("  🔴 STATUS: READY FOR LIVE TRADING")
    print("  The pipeline WILL place real orders when a strategy fires.")
else:
    print("  🟢 STATUS: NOT configured for live trading yet")
    if dry_run != "false":
        print("  → DRY_RUN is still true (no real orders)")
    missing = []
    if not api_key: missing.append("POLYMARKET_API_KEY")
    if not priv_key: missing.append("POLYMARKET_PRIVATE_KEY")
    if not api_secret: missing.append("POLYMARKET_API_SECRET")
    if not api_pass: missing.append("POLYMARKET_API_PASSPHRASE")
    if missing:
        print(f"  → Missing credentials: {', '.join(missing)}")
print("=" * 60)