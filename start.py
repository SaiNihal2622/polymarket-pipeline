#!/usr/bin/env python3
"""
One-click startup script for Polymarket Pipeline.
- Checks Ollama is running and model is loaded
- Auto-upgrades to gemma3:12b if available
- Runs pipeline with auto-restart on crash
"""
import subprocess
import sys
import time
import os
import signal

# Ensure we're in the right directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()


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


def run_pipeline(mode="watch"):
    """Run the pipeline with auto-restart on crash."""
    max_restarts = 10
    restart_count = 0
    cooldown = 5

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
