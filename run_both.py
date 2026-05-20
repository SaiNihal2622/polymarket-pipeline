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


def _startup_revert_bad_resolutions():
    """Auto-revert trades that were incorrectly resolved by the old resolver.

    The old resolver treated closed=true as resolved — but many Polymarket
    markets close (stop trading) long before they actually resolve (outcome
    determined). On startup we check every 'resolved' trade against the
    Gamma API. If the market is NOT actually resolved, we delete its
    outcomes/calibration rows so it goes back to 'pending'.
    """
    import sqlite3
    import urllib.request
    import json as _json

    if not Path(DB_PATH).exists():
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Find all trades that have outcomes but may be incorrectly resolved
    rows = conn.execute("""
        SELECT t.id, t.market_id, t.market_question, t.side,
               o.result, o.pnl
        FROM trades t
        JOIN outcomes o ON t.id = o.trade_id
        WHERE t.status IN ('demo', 'dry_run')
        ORDER BY t.id
    """).fetchall()

    if not rows:
        conn.close()
        return

    GAMMA = "https://gamma-api.polymarket.com"
    reverted = []
    checked = 0

    for row in rows:
        market_id = row["market_id"]
        if not market_id:
            continue

        checked += 1
        actually_resolved = False

        try:
            # Try slug first, then condition_id
            url = f"{GAMMA}/markets?slug={market_id}&limit=1"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = _json.loads(resp.read())
                items = data if isinstance(data, list) else data.get("data", [])
                for m in items:
                    if m.get("resolved"):
                        actually_resolved = True
                        break

            if not actually_resolved:
                # Also try by condition_id
                url2 = f"{GAMMA}/markets?condition_id={market_id}&limit=1"
                req2 = urllib.request.Request(url2)
                with urllib.request.urlopen(req2, timeout=8) as resp2:
                    data2 = _json.loads(resp2.read())
                    items2 = data2 if isinstance(data2, list) else data2.get("data", [])
                    for m in items2:
                        if m.get("resolved"):
                            actually_resolved = True
                            break
        except Exception:
            # Network error — don't revert, keep existing resolution
            continue

        if not actually_resolved:
            conn.execute("DELETE FROM outcomes WHERE trade_id = ?", (row["id"],))
            conn.execute("DELETE FROM calibration WHERE trade_id = ?", (row["id"],))
            reverted.append(f"#{row['id']} {row['market_question'][:50]}... (was {row['result']})")

    conn.commit()
    conn.close()

    if reverted:
        print(f"🔄 Startup revert: {len(reverted)}/{checked} trades reverted to pending (market not yet resolved):", flush=True)
        for r in reverted:
            print(f"   ↩ {r}", flush=True)
    else:
        print(f"✅ Startup check: all {checked} resolved trades verified against Gamma API", flush=True)


def _run_pipeline():
    try:
        from demo_runner import run_loop
        run_loop()
    except Exception as e:
        print(f"❌ Pipeline crashed: {e}", file=sys.stderr, flush=True)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    # Startup: revert any trades incorrectly resolved by old resolver bug
    _startup_revert_bad_resolutions()

    # Pipeline in background thread
    print("🤖 Starting Trading Pipeline in background...", flush=True)
    threading.Thread(target=_run_pipeline, daemon=True).start()

    # Cashout monitor in background thread (position management)
    def _run_cashout():
        import time as _time
        try:
            from cashout import ensure_cashout_columns, check_and_cashout, CHECK_INTERVAL
            ensure_cashout_columns()
            print("💰 Cashout monitor started (take-profit + stop-loss + trailing stop)", flush=True)
            while True:
                try:
                    result = check_and_cashout(verbose=False)
                    if result.get("cashouts", 0) > 0:
                        print(f"💰 {result['cashouts']} cashouts | P&L: ${result['total_pnl']:+.4f}", flush=True)
                except Exception as e:
                    logging.warning(f"Cashout check error: {e}")
                _time.sleep(CHECK_INTERVAL)
        except Exception as e:
            logging.warning(f"Cashout monitor failed to start: {e}")

    threading.Thread(target=_run_cashout, daemon=True).start()

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
