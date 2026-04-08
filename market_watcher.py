"""
Polymarket WebSocket subscriber — live price feed + niche market filtering.
Maintains a live snapshot of tracked markets and detects momentum shifts.

Fixed WS protocol: uses assets_ids field, PING keepalive every 10s.
"""
from __future__ import annotations

import asyncio
import json
import time
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field

import config
from markets import Market, fetch_active_markets, filter_by_categories

log = logging.getLogger(__name__)


@dataclass
class MarketSnapshot:
    market: Market
    last_price: float
    prev_price: float
    last_update: datetime
    momentum: float = 0.0  # price change per minute

    @property
    def price_change(self) -> float:
        return self.last_price - self.prev_price


class MarketWatcher:
    """Watches niche Polymarket markets via WebSocket + periodic Gamma API refresh."""

    def __init__(self):
        self.snapshots: dict[str, MarketSnapshot] = {}
        self.tracked_markets: list[Market] = []
        self._refresh_interval = 300  # refresh market list every 5 min
        self._ws_connected = False
        self.stats = {
            "ws_messages": 0,
            "price_updates": 0,
            "market_refreshes": 0,
        }

    def get_niche_markets(self, markets: list[Market]) -> list[Market]:
        """Filter to niche markets within volume bounds."""
        return [
            m for m in markets
            if config.MIN_VOLUME_USD <= m.volume <= config.MAX_VOLUME_USD
            and m.active
        ]

    async def refresh_markets(self):
        """Fetch and filter markets from Gamma API."""
        try:
            all_markets = await asyncio.get_event_loop().run_in_executor(
                None, lambda: fetch_active_markets(limit=200)
            )
            categorized = filter_by_categories(all_markets)
            self.tracked_markets = self.get_niche_markets(categorized)

            # Update snapshots
            now = datetime.now(timezone.utc)
            existing_ids = set(self.snapshots.keys())
            new_ids = set()

            for m in self.tracked_markets:
                new_ids.add(m.condition_id)
                if m.condition_id not in self.snapshots:
                    self.snapshots[m.condition_id] = MarketSnapshot(
                        market=m,
                        last_price=m.yes_price,
                        prev_price=m.yes_price,
                        last_update=now,
                    )
                else:
                    snap = self.snapshots[m.condition_id]
                    snap.market = m  # update metadata

            # Remove stale snapshots
            for stale_id in existing_ids - new_ids:
                del self.snapshots[stale_id]

            self.stats["market_refreshes"] += 1
            log.info(f"[watcher] Tracking {len(self.tracked_markets)} niche markets")

        except Exception as e:
            log.warning(f"[watcher] Market refresh error: {e}")

    def _get_all_token_ids(self) -> list[str]:
        """Collect all token IDs from tracked markets for WS subscription."""
        token_ids = []
        for m in self.tracked_markets:
            for t in m.tokens:
                tid = t.get("token_id", "")
                if tid:
                    token_ids.append(tid)
        return token_ids

    async def _connect_websocket(self):
        """Connect to Polymarket WebSocket for live price updates."""
        try:
            import websockets
        except ImportError:
            log.warning("[watcher] websockets not installed — using polling fallback")
            return

        backoff = 1
        while True:
            try:
                async with websockets.connect(config.POLYMARKET_WS_HOST) as ws:
                    self._ws_connected = True
                    log.info("[watcher] WebSocket connected")

                    # Subscribe to tracked markets using correct format
                    token_ids = self._get_all_token_ids()
                    if token_ids:
                        # Subscribe in batches (avoid giant messages)
                        batch_size = 50
                        for i in range(0, len(token_ids), batch_size):
                            batch = token_ids[i:i + batch_size]
                            sub_msg = {
                                "assets_ids": batch,
                                "type": "market",
                            }
                            await ws.send(json.dumps(sub_msg))
                        log.info(f"[watcher] Subscribed to {len(token_ids)} tokens")
                    else:
                        log.warning("[watcher] No token IDs to subscribe to")

                    # Start keepalive ping task
                    ping_task = asyncio.create_task(self._ws_ping(ws))
                    backoff = 1

                    try:
                        # Listen for updates
                        while True:
                            try:
                                msg = await asyncio.wait_for(ws.recv(), timeout=15)

                                # Ignore PONG responses
                                if msg == "PONG":
                                    continue

                                self.stats["ws_messages"] += 1

                                try:
                                    data = json.loads(msg)
                                    self._handle_ws_message(data)
                                except json.JSONDecodeError:
                                    # Non-JSON message (could be control frame)
                                    pass

                            except asyncio.TimeoutError:
                                # No message in 15s — connection may be stale
                                pass
                    finally:
                        ping_task.cancel()

            except Exception as e:
                self._ws_connected = False
                log.warning(f"[watcher] WebSocket error: {e}, reconnecting in {backoff}s")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

    async def _ws_ping(self, ws):
        """Send PING every 10 seconds to keep WebSocket alive."""
        while True:
            try:
                await asyncio.sleep(10)
                await ws.send("PING")
            except Exception:
                break

    def _handle_ws_message(self, data: dict):
        """Process a WebSocket price update."""
        # Handle array of events
        events = data if isinstance(data, list) else [data]

        for event in events:
            msg_type = event.get("event_type", event.get("type", ""))
            asset_id = event.get("asset_id", event.get("market", ""))

            if msg_type == "price_change":
                # price_changes is an array: [{"asset_id": "...", "price": "0.55"}, ...]
                price_changes = event.get("price_changes", [])
                for pc in price_changes:
                    pc_asset = pc.get("asset_id", "")
                    pc_price = pc.get("price")
                    if pc_asset and pc_price is not None:
                        self._update_snapshot(pc_asset, float(pc_price))
                continue

            elif msg_type == "last_trade_price":
                price = event.get("price")
            elif msg_type == "book":
                # Full orderbook — extract best bid as price proxy
                bids = event.get("bids", [])
                asks = event.get("asks", [])
                if bids:
                    best_bid = float(bids[0].get("price", 0))
                    best_ask = float(asks[0].get("price", 1)) if asks else best_bid
                    price = (best_bid + best_ask) / 2  # mid-price
                else:
                    continue
            else:
                continue

            if not asset_id or price is None:
                continue

            self._update_snapshot(asset_id, float(price))

    def _update_snapshot(self, asset_id: str, price: float):
        """Update a market snapshot with a new price from WebSocket."""
        for cid, snap in self.snapshots.items():
            token_ids = [t.get("token_id", "") for t in snap.market.tokens]
            if asset_id in token_ids or asset_id == cid:
                now = datetime.now(timezone.utc)
                elapsed = (now - snap.last_update).total_seconds()
                snap.prev_price = snap.last_price
                snap.last_price = price
                snap.last_update = now
                if elapsed > 0:
                    snap.momentum = (snap.last_price - snap.prev_price) / (elapsed / 60)
                # Update market object price too
                snap.market.yes_price = price
                snap.market.no_price = 1.0 - price
                self.stats["price_updates"] += 1
                break

    async def _polling_fallback(self):
        """Poll Gamma API for price updates when WebSocket unavailable."""
        while True:
            await asyncio.sleep(30)
            if self._ws_connected:
                continue
            await self.refresh_markets()

    async def run(self):
        """Start the market watcher — refresh + WebSocket + polling fallback."""
        await self.refresh_markets()

        async def refresh_loop():
            while True:
                await asyncio.sleep(self._refresh_interval)
                await self.refresh_markets()

        await asyncio.gather(
            refresh_loop(),
            self._connect_websocket(),
            self._polling_fallback(),
            return_exceptions=True,
        )

    def get_market_by_question(self, question_fragment: str) -> Market | None:
        """Find a tracked market by partial question match."""
        frag = question_fragment.lower()
        for m in self.tracked_markets:
            if frag in m.question.lower():
                return m
        return None

    def get_snapshot(self, condition_id: str) -> MarketSnapshot | None:
        return self.snapshots.get(condition_id)


if __name__ == "__main__":
    async def _test():
        watcher = MarketWatcher()
        await watcher.refresh_markets()
        print(f"Tracking {len(watcher.tracked_markets)} niche markets:")
        token_count = sum(len(m.tokens) for m in watcher.tracked_markets)
        print(f"Total token IDs for WS: {token_count}")
        for m in watcher.tracked_markets[:10]:
            tids = [t.get("token_id", "")[:20] for t in m.tokens]
            print(f"  [{m.category}] ${m.volume:,.0f} | YES:{m.yes_price:.2f} | {m.question[:50]} tokens:{len(tids)}")

    asyncio.run(_test())
