from __future__ import annotations

import asyncio

import config
import logger
from edge import Signal
from markets import get_token_id


def execute_trade(signal: Signal) -> dict:
    """Execute a trade on Polymarket or log a dry-run. Synchronous."""
    daily_spent = abs(logger.get_daily_pnl())
    token_id = get_token_id(signal.market, signal.side)
    
    if daily_spent + signal.bet_amount > config.DAILY_LOSS_LIMIT_USD:
        return _log_and_return(signal, status="rejected_daily_limit", order_id=None, token_id=token_id)

    if config.DRY_RUN:
        return _log_and_return(signal, status="dry_run", order_id=None, token_id=token_id)

    return _execute_live(signal, token_id=token_id)


async def execute_trade_async(signal: Signal) -> dict:
    """Async wrapper around execute_trade."""
    return await asyncio.get_event_loop().run_in_executor(None, execute_trade, signal)


def _execute_live(signal: Signal, token_id: str | None) -> dict:
    """Place a real order via Polymarket CLOB V2 client (deposit wallet flow)."""
    try:
        from py_clob_client_v2.client import ClobClient
        from py_clob_client_v2.clob_types import OrderArgs, OrderType, ApiCreds, PartialCreateOrderOptions

        priv_key = config.POLYMARKET_PRIVATE_KEY
        if priv_key and not priv_key.startswith("0x"):
            priv_key = "0x" + priv_key

        # Use the V2 SDK with deposit wallet as funder
        deposit_wallet = config.POLYMARKET_DEPOSIT_WALLET
        client = ClobClient(
            host=config.POLYMARKET_HOST,
            key=priv_key,
            chain_id=137,
            funder=deposit_wallet,  # V2: deposit/proxy wallet required
        )

        api_key = config.POLYMARKET_API_KEY
        api_secret = config.POLYMARKET_API_SECRET
        api_passphrase = config.POLYMARKET_API_PASSPHRASE

        if api_key and api_key != "derive" and api_secret and api_secret != "derive" and api_passphrase and api_passphrase != "derive":
            creds = ApiCreds(
                api_key=api_key,
                api_secret=api_secret,
                api_passphrase=api_passphrase,
            )
            client.set_api_creds(creds)
        else:
            creds = client.create_or_derive_api_key()
            client.set_api_creds(creds)

        # token_id already passed in
        if not token_id:
            return _log_and_return(signal, status="error_no_token", order_id=None, token_id=None)

        price = signal.market.yes_price if signal.side == "YES" else signal.market.no_price

        order_args = OrderArgs(
            price=price,
            size=signal.bet_amount,
            side="BUY",
            token_id=str(token_id),
        )

        resp = client.create_and_post_order(
            order_args=order_args,
            options=PartialCreateOrderOptions(tick_size="0.01"),
            order_type=OrderType.GTC,
        )

        order_id = resp.get("orderID", resp.get("id", "unknown"))
        return _log_and_return(signal, status="executed", order_id=order_id, token_id=token_id)

    except ImportError:
        return _log_and_return(signal, status="error_no_clob_client", order_id=None)
    except Exception as e:
        return _log_and_return(signal, status=f"error_{type(e).__name__}", order_id=None)


def _log_and_return(signal: Signal, status: str, order_id: str | None, token_id: str | None = None) -> dict:
    """Log trade to SQLite and return result dict."""
    trade_id = logger.log_trade(
        market_id=signal.market.condition_id,
        market_question=signal.market.question,
        claude_score=signal.claude_score,
        market_price=signal.market_price,
        edge=signal.edge,
        side=signal.side,
        amount_usd=signal.bet_amount,
        order_id=order_id,
        status=status,
        reasoning=signal.reasoning,
        headlines=signal.headlines,
        news_source=signal.news_source,
        classification=signal.classification,
        materiality=signal.materiality,
        news_latency_ms=signal.news_latency_ms,
        classification_latency_ms=signal.classification_latency_ms,
        total_latency_ms=signal.total_latency_ms,
        token_id=token_id,
    )

    return {
        "trade_id": trade_id,
        "market": signal.market.question,
        "side": signal.side,
        "amount": signal.bet_amount,
        "edge": signal.edge,
        "status": status,
        "order_id": order_id,
        "classification": signal.classification,
        "materiality": signal.materiality,
        "latency_ms": signal.total_latency_ms,
    }