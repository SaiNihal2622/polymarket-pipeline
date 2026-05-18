"""
Portfolio risk manager — enforces position limits, correlation limits,
and portfolio-level risk controls. Integrates with correlation engine.

Industry standard: never risk more than X% of bankroll per trade,
max N correlated positions, stop-loss enforcement.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from collections import defaultdict

import config
import logger
from correlation import get_portfolio_risk, _categorize_market

log = logging.getLogger(__name__)


@dataclass
class RiskLimits:
    """Configurable risk limits."""
    max_position_pct: float = 0.15          # Max % of bankroll per position
    max_correlated_pct: float = 0.40        # Max % in correlated positions
    max_same_direction_pct: float = 0.70    # Max % in same direction (YES/NO)
    max_positions_per_category: int = 3     # Max positions in same category
    max_total_positions: int = 10           # Max total open positions
    min_bankroll_reserve: float = 0.20      # Keep 20% in reserve
    max_daily_loss_pct: float = 0.10        # Stop trading if daily loss > 10%
    cooldown_after_loss_minutes: int = 30   # Cooldown after a losing trade


@dataclass
class PositionState:
    """Current portfolio position state."""
    total_bankroll: float = 0.0
    deployed_capital: float = 0.0
    available_capital: float = 0.0
    open_positions: list[dict] = field(default_factory=list)
    daily_pnl: float = 0.0
    last_loss_time: float = 0.0
    position_count_by_category: dict[str, int] = field(default_factory=lambda: defaultdict(int))


class PortfolioRiskManager:
    """
    Manages portfolio-level risk. Called before every trade to validate sizing.
    """

    def __init__(self, limits: RiskLimits | None = None):
        self.limits = limits or RiskLimits()
        self._state = PositionState()
        self._update_state()

    def _update_state(self):
        """Refresh position state from trade logger."""
        try:
            trades = logger.get_recent_trades(limit=100)
            open_trades = [t for t in trades if t.get("status") in ("dry_run", "executed")]
            resolved = [t for t in trades if t.get("status") == "resolved"]

            self._state.open_positions = open_trades
            self._state.deployed_capital = sum(t.get("bet_amount", 0) for t in open_trades)

            # Estimate bankroll from config
            self._state.total_bankroll = config.BANKROLL
            self._state.available_capital = self._state.total_bankroll - self._state.deployed_capital

            # Category breakdown
            self._state.position_count_by_category.clear()
            for t in open_trades:
                cats = _categorize_market(t.get("market", ""))
                for cat in cats:
                    self._state.position_count_by_category[cat] += 1

            # Daily P&L
            today_start = time.time() - 86400
            self._state.daily_pnl = sum(
                t.get("pnl", 0) for t in resolved
                if t.get("resolved_at", 0) > today_start
            )

            # Last loss time
            losses = [t for t in resolved if t.get("pnl", 0) < 0]
            if losses:
                self._state.last_loss_time = max(t.get("resolved_at", 0) for t in losses)

        except Exception as e:
            log.debug(f"[risk_manager] State update failed: {e}")

    def validate_trade(
        self,
        bet_amount: float,
        side: str,
        market_question: str,
        composite_score: float = 0.0,
    ) -> tuple[bool, str, float]:
        """
        Validate a proposed trade against risk limits.
        Returns (approved, reason, adjusted_amount).

        If approved=False, the trade should be skipped.
        If adjusted_amount < bet_amount, the trade should be reduced.
        """
        self._update_state()
        state = self._state
        limits = self.limits

        # 1. Check daily loss limit
        if state.daily_pnl < 0 and abs(state.daily_pnl) > state.total_bankroll * limits.max_daily_loss_pct:
            return False, f"DAILY LOSS LIMIT: Lost ${abs(state.daily_pnl):.2f} today ({abs(state.daily_pnl)/state.total_bankroll:.1%}). Trading paused.", 0

        # 2. Check cooldown after loss
        if state.last_loss_time > 0:
            elapsed = time.time() - state.last_loss_time
            if elapsed < limits.cooldown_after_loss_minutes * 60:
                remaining = (limits.cooldown_after_loss_minutes * 60 - elapsed) / 60
                return False, f"LOSS COOLDOWN: {remaining:.0f}m remaining after last loss.", 0

        # 3. Check total position count
        if len(state.open_positions) >= limits.max_total_positions:
            return False, f"MAX POSITIONS: {len(state.open_positions)}/{limits.max_total_positions} open.", 0

        # 4. Check bankroll reserve
        min_available = state.total_bankroll * limits.min_bankroll_reserve
        if state.available_capital - bet_amount < min_available:
            adjusted = max(0, state.available_capital - min_available)
            if adjusted < config.MIN_TRADE_USD:
                return False, f"RESERVE LIMIT: Only ${state.available_capital:.2f} available, need ${min_available:.2f} reserve.", 0
            return True, f"REDUCED: Bankroll reserve limit. ${bet_amount:.2f} → ${adjusted:.2f}", adjusted

        # 5. Check max position size
        max_bet = state.total_bankroll * limits.max_position_pct * (composite_score / 0.7 if composite_score > 0 else 1.0)
        max_bet = max(config.MIN_TRADE_USD, min(max_bet, config.MAX_TRADE_USD))
        if bet_amount > max_bet:
            return True, f"SIZED DOWN: ${bet_amount:.2f} → ${max_bet:.2f} (position limit)", max_bet

        # 6. Check category concentration
        cats = _categorize_market(market_question)
        for cat in cats:
            if state.position_count_by_category[cat] >= limits.max_positions_per_category:
                return False, f"CATEGORY LIMIT: Already {state.position_count_by_category[cat]} positions in '{cat}'.", 0

        # 7. Check direction concentration
        same_direction = sum(1 for p in state.open_positions if p.get("side") == side)
        direction_pct = (same_direction + 1) / (len(state.open_positions) + 1)
        if direction_pct > limits.max_same_direction_pct:
            return False, f"DIRECTION LIMIT: {direction_pct:.0%} in {side} direction (max {limits.max_same_direction_pct:.0%}).", 0

        # 8. Correlation check via correlation engine
        portfolio_risk = get_portfolio_risk(state.open_positions)
        if portfolio_risk["risk_level"] == "high":
            warnings = portfolio_risk.get("warnings", [])
            warning_text = "; ".join(warnings[:2])
            return True, f"CORRELATION WARNING: {warning_text}. Reduced sizing.", bet_amount * 0.5

        return True, "APPROVED", bet_amount

    def get_portfolio_summary(self) -> dict:
        """Get current portfolio risk summary."""
        self._update_state()
        risk = get_portfolio_risk(self._state.open_positions)

        return {
            "bankroll": self._state.total_bankroll,
            "deployed": self._state.deployed_capital,
            "available": self._state.available_capital,
            "open_positions": len(self._state.open_positions),
            "daily_pnl": self._state.daily_pnl,
            "risk_level": risk["risk_level"],
            "warnings": risk.get("warnings", []),
            "categories": dict(self._state.position_count_by_category),
            "direction": risk.get("direction", {}),
        }


# Singleton
_manager = PortfolioRiskManager()


def validate_trade(bet_amount: float, side: str, market_question: str, composite_score: float = 0.0) -> tuple[bool, str, float]:
    """Module-level: validate a proposed trade."""
    return _manager.validate_trade(bet_amount, side, market_question, composite_score)


def get_portfolio_summary() -> dict:
    """Module-level: get portfolio risk summary."""
    return _manager.get_portfolio_summary()