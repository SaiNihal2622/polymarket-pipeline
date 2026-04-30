#!/usr/bin/env python3
"""
run_both.py — Launches the pipeline (demo_runner.run_loop) AND web dashboard
together. Dashboard runs in a daemon thread, pipeline in main thread.
"""
import logging
import os
import sys
import threading
from logger import DB_PATH


def _run_pipeline():
    try:
        from demo_runner import run_loop
        run_loop()
    except Exception as e:
        print(f"❌ Pipeline crashed: {e}", file=sys.stderr, flush=True)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    # ── FRESH START: wipe all old trades if requested ──
    wipe_env = os.getenv("WIPE_ON_START", "true").lower()
    if wipe_env == "true":
        print("🔄 WIPE_ON_START=true — clearing all old trades for fresh start", flush=True)
        try:
            from demo_runner import _wipe_all_trades
            _wipe_all_trades()
        except Exception as e:
            print(f"⚠️  Wipe failed: {e}", file=sys.stderr, flush=True)

    # Pipeline in background thread
    print("🤖 Starting Trading Pipeline in background...", flush=True)
    threading.Thread(target=_run_pipeline, daemon=True).start()

    # Dashboard in main thread to ensure Railway health checks pass
    try:
        from web_dashboard import app
        port = int(os.getenv("PORT", "8080"))
        print(f"📊 Dashboard listening on 0.0.0.0:{port}", flush=True)
        # We run the Flask app in the main thread
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
    except Exception as e:
        print(f"⚠️  Dashboard failed to start: {e}", file=sys.stderr, flush=True)
        # If dashboard fails, we should still keep the process alive for the pipeline
        import time
        while True:
            time.sleep(60)
