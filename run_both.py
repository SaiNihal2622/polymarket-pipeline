#!/usr/bin/env python3
"""
run_both.py — Launches the pipeline (demo_runner.run_loop) AND web dashboard
together. Dashboard runs in a daemon thread, pipeline in main thread.
"""
import logging
import os
import sys
import threading
from pathlib import Path

from logger import DB_PATH

# Ensure the parent directory for the DB exists (critical for Railway /data mounts)
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)


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
    wipe_env = os.getenv("WIPE_ON_START", "false").lower()
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
    port = int(os.getenv("PORT", "8081"))
    try:
        from web_dashboard import app
        print(f"📊 Dashboard listening on 0.0.0.0:{port}", flush=True)
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
    except Exception as e:
        import traceback
        print(f"⚠️  Dashboard failed to start: {e}", file=sys.stderr, flush=True)
        traceback.print_exc()
        # Fallback: run a minimal health-check server so Railway doesn't kill us
        _run_fallback(port)


def _run_fallback(port: int = 8081):
    """Minimal HTTP server that always works, even if Flask/imports fail."""
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import json as _json

    class FallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/api/trades":
                # Serve trades from DB directly
                try:
                    import sqlite3
                    from logger import DB_PATH
                    conn = sqlite3.connect(DB_PATH)
                    conn.row_factory = sqlite3.Row
                    rows = conn.execute("SELECT * FROM trades ORDER BY id DESC").fetchall()
                    trades = [dict(r) for r in rows]
                    conn.close()
                    body = _json.dumps({"trades": trades}).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except Exception as ex:
                    body = _json.dumps({"error": str(ex)}).encode()
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(body)
            else:
                body = b"<html><body><h1>Polymarket Pipeline</h1><p>Pipeline running (dashboard loading...)</p></body></html>"
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        def log_message(self, *a):
            pass

    print(f"📊 Fallback health server on 0.0.0.0:{port}", flush=True)
    HTTPServer(("0.0.0.0", port), FallbackHandler).serve_forever()
