from __future__ import annotations

from dataclasses import dataclass

from app.config.settings import TargetSettings
from app.strategy.backtest import BacktestResult


@dataclass(frozen=True)
class RiskVerdict:
    allowed: bool
    experimental_only: bool
    messages: tuple[str, ...]


def evaluate_backtest(
    result: BacktestResult,
    targets: TargetSettings,
) -> RiskVerdict:
    msgs: list[str] = []
    experimental = False
    if result.trades < 3:
        msgs.append("trades < 3")
        experimental = True
    if result.max_drawdown > targets.max_drawdown:
        msgs.append(
            f"max_drawdown {result.max_drawdown:.2%} > {targets.max_drawdown:.2%}"
        )
        experimental = True
    # Prefer annual return inside or above min; below min => experimental
    if result.annual_return < targets.annual_return_min:
        msgs.append(
            f"annual_return {result.annual_return:.2%} < target min "
            f"{targets.annual_return_min:.2%}"
        )
        experimental = True
    if result.annual_return > targets.annual_return_max * 2:
        msgs.append("annual_return unusually high; treat carefully")
    allowed = True
    if experimental:
        msgs.append("mark as experimental recommendation only")
    else:
        msgs.append("passes target/risk gate for recommendation tone")
    return RiskVerdict(
        allowed=allowed,
        experimental_only=experimental,
        messages=tuple(msgs),
    )


def position_size_ok(
    weight: float,
    total_exposure: float,
    targets: TargetSettings,
) -> RiskVerdict:
    msgs: list[str] = []
    ok = True
    if weight > targets.max_position_pct:
        ok = False
        msgs.append(
            f"single position {weight:.0%} > max {targets.max_position_pct:.0%}"
        )
    if total_exposure > targets.max_total_exposure:
        ok = False
        msgs.append(
            f"total exposure {total_exposure:.0%} > max "
            f"{targets.max_total_exposure:.0%}"
        )
    if ok:
        msgs.append("position sizing within limits")
    return RiskVerdict(allowed=ok, experimental_only=False, messages=tuple(msgs))
