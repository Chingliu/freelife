from __future__ import annotations

from app.data.models import Bar
from app.research.backtest.metrics import compute_metrics
from app.research.backtest.types import BacktestResult, Trade
from app.research.strategies.base import Strategy


class BacktestEngine:
    """Long-only engine: target weight in [0, 1], fill at next bar open."""

    def __init__(
        self,
        *,
        commission_bps: float = 3.0,
        slippage_bps: float = 2.0,
        initial_capital: float = 1.0,
    ) -> None:
        self.commission_bps = commission_bps
        self.slippage_bps = slippage_bps
        self.initial_capital = initial_capital

    def _cost_rate(self) -> float:
        return (self.commission_bps + self.slippage_bps) / 10000.0

    def run(self, strategy: Strategy, bars: list[Bar], code: str) -> BacktestResult:
        if len(bars) < 5:
            empty = compute_metrics([], [], [], [])
            return BacktestResult(
                strategy_id=strategy.strategy_id,
                code=code,
                metrics=empty,
                params=dict(strategy.params),
                notes=["insufficient bars"],
            )

        targets = strategy.generate(bars)
        if len(targets) != len(bars):
            raise ValueError("strategy target length mismatch")

        cost = self._cost_rate()
        cash = self.initial_capital
        shares = 0.0
        equity: list[float] = []
        positions: list[float] = []
        dates = [b.trade_date for b in bars]
        trades: list[Trade] = []
        current_weight = max(0.0, min(1.0, float(targets[-1]))) if targets else 0.0

        entry_date = None
        entry_price = 0.0
        entry_i = 0
        pending_target: float | None = None

        for i, bar in enumerate(bars):
            # Execute pending rebalance at today's open
            if pending_target is not None:
                price = bar.open * (1 + cost if pending_target > shares * bar.open else 1 - cost)
                # Mark-to-market before trade using open
                equity_before = cash + shares * bar.open
                desired_value = pending_target * equity_before
                desired_shares = desired_value / price if price > 0 else 0.0
                delta = desired_shares - shares
                if abs(delta) > 1e-12:
                    # opening / adding
                    if shares <= 1e-12 and desired_shares > 1e-12:
                        entry_date = bar.trade_date
                        entry_price = price
                        entry_i = i
                    # closing
                    if shares > 1e-12 and desired_shares <= 1e-12 and entry_date is not None:
                        ret = price / entry_price - 1.0 if entry_price else 0.0
                        trades.append(
                            Trade(
                                entry_date=entry_date,
                                exit_date=bar.trade_date,
                                entry_price=entry_price,
                                exit_price=price,
                                return_pct=ret,
                                bars_held=max(i - entry_i, 1),
                            )
                        )
                        entry_date = None
                    cash -= delta * price
                    shares = desired_shares
                pending_target = None

            mark = cash + shares * bar.close
            equity.append(mark)
            positions.append(0.0 if mark <= 0 else (shares * bar.close) / mark)

            # Signal today → trade tomorrow open
            if i < len(bars) - 1:
                t = max(0.0, min(1.0, float(targets[i])))
                pending_target = t

        # Close open trade at last close for reporting
        if entry_date is not None and shares > 1e-12:
            last = bars[-1]
            trades.append(
                Trade(
                    entry_date=entry_date,
                    exit_date=last.trade_date,
                    entry_price=entry_price,
                    exit_price=last.close,
                    return_pct=last.close / entry_price - 1.0 if entry_price else 0.0,
                    bars_held=max(len(bars) - 1 - entry_i, 1),
                )
            )

        metrics = compute_metrics(equity, dates, positions, trades)
        return BacktestResult(
            strategy_id=strategy.strategy_id,
            code=code,
            metrics=metrics,
            params=dict(strategy.params),
            trades=trades,
            equity_curve=list(zip(dates, equity)),
            positions=positions,
            current_weight=current_weight,
        )
