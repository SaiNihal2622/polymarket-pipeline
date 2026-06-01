#!/usr/bin/env python3
"""
One-click startup script for Polymarket Pipeline.
- Checks Ollama is running and model is loaded
- Auto-upgrades to gemma3:12b if available
- Runs pipeline with auto-restart on crash
- Launches background modules: on-chain scanner, market maker, AI insights
"""
import subprocess
import sys
import time
import os
import signal
import threading

# Ensure we're in the right directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

# Apply Polymarket CLOB V2 patches (domain version + order body)
try:
    import patch_clob_v2
except Exception as e:
    print(f"[startup] CLOB V2 patch failed: {e}")

# Apply residential proxy patch (routes CLOB traffic through residential IP)
try:
    import patch_clob_proxy
except Exception as e:
    print(f"[startup] CLOB proxy patch failed: {e}")


def check_ollama():
    """Ensure Ollama is running and model is available."""
    provider = os.getenv("LLM_PROVIDER", "ollama")
    if provider != "ollama":
        print(f"  LLM provider: {provider} (not Ollama, skipping check)")
        return True

    model = os.getenv("CLASSIFICATION_MODEL", "gemma3:4b")

    # Check if Ollama is running
    try:
        import httpx
        base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        resp = httpx.get(f"{base}/api/tags", timeout=5)
        models = [m["name"] for m in resp.json().get("models", [])]
    except Exception:
        print("  Ollama not running. Starting...")
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(3)
        try:
            resp = httpx.get(f"{base}/api/tags", timeout=5)
            models = [m["name"] for m in resp.json().get("models", [])]
        except Exception:
            print("  ERROR: Cannot start Ollama. Install from https://ollama.com")
            return False

    # Check if model exists
    if model not in models and f"{model}:latest" not in models:
        # Check for exact match with tag
        found = any(model.split(":")[0] in m for m in models)
        if not found:
            print(f"  Model {model} not found. Pulling...")
            subprocess.run(["ollama", "pull", model], check=True)

    # Auto-upgrade: if gemma3:12b available but config says 4b, upgrade
    if "gemma3:12b" in models or "gemma3:12b:latest" in models:
        if "4b" in model:
            print("  Upgrading to gemma3:12b (better accuracy)...")
            # Update .env
            env_path = os.path.join(os.path.dirname(__file__), ".env")
            with open(env_path, "r") as f:
                content = f.read()
            content = content.replace("CLASSIFICATION_MODEL=gemma3:4b", "CLASSIFICATION_MODEL=gemma3:12b")
            content = content.replace("SCORING_MODEL=gemma3:4b", "SCORING_MODEL=gemma3:12b")
            with open(env_path, "w") as f:
                f.write(content)
            print("  .env updated to gemma3:12b")

    print(f"  Ollama OK. Models: {', '.join(models)}")
    return True


# ── Background Modules ──────────────────────────────────────────────────────

def _run_onchain_scanner():
    """Background thread: periodically scan on-chain whale activity."""
    try:
        from onchain_scanner import scan_onchain
    except ImportError:
        print("[onchain_scanner] Module not available, skipping.")
        return
    while True:
        try:
            result = scan_onchain()
            alerts = result.get("new_alerts", 0)
            flows = result.get("order_flows", 0)
            if alerts or flows:
                print(f"[onchain_scanner] {alerts} new alerts, {flows} order flows")
        except Exception as e:
            print(f"[onchain_scanner] Error: {e}")
        time.sleep(300)  # Scan every 5 minutes


def _run_market_maker():
    """Background thread: periodically scan for spread-based market maker pairs."""
    try:
        from market_maker import run_maker_cycle
    except ImportError:
        print("[market_maker] Module not available, skipping.")
        return
    while True:
        try:
            result = run_maker_cycle()
            opps = result.get("opportunities", 0)
            trades = result.get("trades_executed", 0)
            if opps or trades:
                print(f"[market_maker] {opps} opportunities, {trades} trades executed")
        except Exception as e:
            print(f"[market_maker] Error: {e}")
        time.sleep(600)  # Scan every 10 minutes


def _run_sniper():
    """Background thread: sniper execution engine — event-driven from on-chain alerts."""
    try:
        from sniper import run_sniper_cycle, monitor_positions
        from onchain_scanner import scan_onchain
    except ImportError:
        print("[sniper] Module not available, skipping.")
        return
    while True:
        try:
            # First, get fresh on-chain data
            scan_result = scan_onchain()
            alerts = scan_result.get("alert_objects", [])

            # Run sniper cycle with whale alerts as input
            if alerts:
                result = run_sniper_cycle(whale_alerts=alerts)
                trades = result.get("trades_executed", 0)
                signals = result.get("signals_total", 0)
                if signals:
                    print(f"[sniper] {signals} signals, {trades} trades executed")

            # Monitor existing positions for stop-loss/safety-cut
            # (In real mode, this would fetch live prices)
        except Exception as e:
            print(f"[sniper] Error: {e}")
        time.sleep(120)  # Check every 2 minutes


def _run_ai_insights():
    """Background thread: periodically generate AI probability estimates."""
    try:
        from ai_insights import generate_batch_insights
        import httpx
    except ImportError:
        print("[ai_insights] Module not available, skipping.")
        return
    while True:
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.get(
                    "https://gamma-api.polymarket.com/markets",
                    params={
                        "limit": 10, "active": "true", "closed": "false",
                        "order": "volume", "ascending": "false",
                    }
                )
                resp.raise_for_status()
                markets = resp.json()
            insights = generate_batch_insights(markets)
            if insights:
                print(f"[ai_insights] Generated {len(insights)} probability estimates")
        except Exception as e:
            print(f"[ai_insights] Error: {e}")
        time.sleep(900)  # Generate every 15 minutes


def _start_background_modules():
    """Start all background modules as daemon threads."""
    threads = []
    for name, target in [
        ("onchain_scanner", _run_onchain_scanner),
        ("market_maker", _run_market_maker),
        ("sniper", _run_sniper),
        ("ai_insights", _run_ai_insights),
    ]:
        t = threading.Thread(target=target, name=name, daemon=True)
        t.start()
        threads.append(t)
        print(f"  [+] Background module started: {name}")
    return threads


def run_pipeline(mode="watch"):
    """Run the pipeline with auto-restart on crash."""
    max_restarts = 10
    restart_count = 0
    cooldown = 5

    # Start background modules
    _start_background_modules()

    while restart_count < max_restarts:
        print(f"\n{'='*60}")
        print(f"  Starting pipeline ({mode}) | Restart #{restart_count}")
        print(f"{'='*60}\n")

        try:
            result = subprocess.run(
                [sys.executable, "cli.py", mode],
                check=False,
            )
            if result.returncode == 0:
                print("\n  Pipeline exited cleanly.")
                break
            else:
                print(f"\n  Pipeline crashed (exit code {result.returncode})")
        except KeyboardInterrupt:
            print("\n  Stopped by user.")
            break
        except Exception as e:
            print(f"\n  Error: {e}")

        restart_count += 1
        wait = cooldown * restart_count
        print(f"  Restarting in {wait}s... ({restart_count}/{max_restarts})")
        time.sleep(wait)

    if restart_count >= max_restarts:
        print(f"\n  Too many restarts ({max_restarts}). Giving up.")


if __name__ == "__main__":
    print("\n  Polymarket Pipeline — Startup Check")
    print("  " + "-" * 40)

    if not check_ollama():
        sys.exit(1)

    mode = sys.argv[1] if len(sys.argv) > 1 else "watch"
    run_pipeline(mode)