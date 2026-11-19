from __future__ import annotations

import math
from datetime import date

from app.research.backtest.types import PerformanceMetrics, Trade


def _safe_div(a: float, b: float, default: float = 0.0) -> float:
    return default if b == 0 else a / b


def compute_metrics(
    equity: list[float],
    dates: list[date],
    positions: list[float],
    trades: list[Trade],
    *,
    risk_free: float = 0.02,
) -> PerformanceMetrics:
    if not equity or not dates:
        return PerformanceMetrics(
            total_return=0.0,
            annual_return=0.0,
            max_drawdown=0.0,
            sharpe=0.0,
            calmar=0.0,
            win_rate=0.0,
            trades=0,
            avg_holding_bars=0.0,
            time_in_market=0.0,
            volatility=0.0,
            final_equity=1.0,
        )

    final = equity[-1]
    total_return = final - 1.0
    days = max((dates[-1] - dates[0]).days, 1)
    annual = (final ** (365.0 / days) - 1.0) if final > 0 else -1.0

    peak = equity[0]
    max_dd = 0.0
    for e in equity:
        peak = max(peak, e)
        max_dd = max(max_dd, (peak - e) / peak if peak else 0.0)

    rets: list[float] = []
    for i in range(1, len(equity)):
        if equity[i - 1] > 0:
            rets.append(equity[i] / equity[i - 1] - 1.0)

    vol = 0.0
    sharpe = 0.0
    if rets:
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / max(len(rets) - 1, 1)
        daily_vol = math.sqrt(var)
        vol = daily_vol * math.sqrt(252.0)
        excess = mean - risk_free / 252.0
        sharpe = _safe_div(excess, daily_vol) * math.sqrt(252.0)

    calmar = _safe_div(annual, max_dd) if max_dd > 0 else (annual if annual > 0 else 0.0)

    closed = [t for t in trades if t.return_pct is not None]
    wins = sum(1 for t in closed if (t.return_pct or 0) > 0)
    win_rate = _safe_div(wins, len(closed))
    avg_hold = (
        sum(t.bars_held for t in closed) / len(closed) if closed else 0.0
    )
    time_in = (
        sum(1 for p in positions if p > 1e-9) / len(positions) if positions else 0.0
    )

    return PerformanceMetrics(
        total_return=total_return,
        annual_return=annual,
        max_drawdown=max_dd,
        sharpe=sharpe,
        calmar=calmar,
        win_rate=win_rate,
        trades=len(trades),
        avg_holding_bars=avg_hold,
        time_in_market=time_in,
        volatility=vol,
        final_equity=final,
    )
