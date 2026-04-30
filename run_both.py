#!/usr/bin/env python3
"""
run_both.py — Launches the pipeline (demo_runner.run_loop) AND web dashboard
together. Dashboard runs in a daemon thread, pipeline in main thread.
"""
import logging
import os
import sys
import threading


def _run_dashboard():
    try:
        from web_dashboard import app
        port = int(os.getenv("PORT", "8080"))
        print(f"📊 Dashboard listening on 0.0.0.0:{port}", flush=True)
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
    except Exception as e:
        print(f"⚠️  Dashboard failed to start: {e}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")

    # DB RESET (Temporary for fresh start on Railway)
    from config import DB_PATH
    if os.path.exists(DB_PATH):
        print(f"🗑️ Wiping DB at {DB_PATH} for fresh start...", flush=True)
        try:
            os.remove(DB_PATH)
            print("✅ DB Reset Complete.", flush=True)
        except Exception as e:
            print(f"❌ Failed to reset DB: {e}", flush=True)
    else:
        print(f"ℹ️ No existing DB found at {DB_PATH}. Starting fresh.", flush=True)

    # Dashboard in background daemon thread
    threading.Thread(target=_run_dashboard, daemon=True).start()

    # Pipeline loop in main thread (avoid argparse from demo_runner.main)
    from demo_runner import run_loop
    run_loop()
