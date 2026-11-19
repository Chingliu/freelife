"""Optional walk-forward / grid lab (Phase-2 P3). Not on daily default path."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Callable

from app.data.models import Bar
from app.research.backtest.engine import BacktestEngine
from app.research.backtest.horizons import metrics_on_slice
from app.research.strategies.base import Strategy


def walk_forward(
    strategy_factory: Callable[[], Strategy],
    bars: list[Bar],
    *,
    train_years: float = 3.0,
    test_years: float = 1.0,
    step_years: float = 1.0,
    engine: BacktestEngine | None = None,
    code: str = "",
) -> dict[str, Any]:
    """
    Rolling forward windows: for each fold, run full-path backtest (warmup OK)
    then score metrics only on the test segment.
    Fixed-param strategies: no refit; this validates temporal stability.
    """
    engine = engine or BacktestEngine()
    if len(bars) < 120:
        return {
            "folds": [],
            "summary": {"status": "insufficient", "fold_count": 0},
            "note": "need longer history for walk-forward",
        }

    end = bars[-1].trade_date
    start = bars[0].trade_date
    folds: list[dict[str, Any]] = []
    cursor_test_end = start + timedelta(days=int(365 * (train_years + test_years)))
    step = timedelta(days=int(365 * step_years))
    train_delta = timedelta(days=int(365 * train_years))
    test_delta = timedelta(days=int(365 * test_years))

    while cursor_test_end <= end + timedelta(days=5):
        test_end = min(cursor_test_end, end)
        test_start = test_end - test_delta
        train_end = test_start - timedelta(days=1)
        train_start = train_end - train_delta
        if train_start < start:
            train_start = start
        # Need some train bars and a non-empty test window after train
        if train_end <= train_start or test_start <= train_end or test_start > end:
            cursor_test_end = cursor_test_end + step
            continue
        # Use bars up to test_end for path continuity
        window_bars = [b for b in bars if b.trade_date <= test_end]
        if len(window_bars) < 60:
            cursor_test_end = cursor_test_end + step
            continue
        # Ensure enough bars before test for warmup
        train_bars = [b for b in window_bars if b.trade_date <= train_end]
        if len(train_bars) < 40:
            cursor_test_end = cursor_test_end + step
            continue
        strategy = strategy_factory()
        result = engine.run(strategy, window_bars, code=code or strategy.strategy_id)
        dates = [d for d, _ in result.equity_curve]
        equity = [e for _, e in result.equity_curve]
        m = metrics_on_slice(
            equity,
            dates,
            list(result.positions),
            list(result.trades),
            start=test_start,
            end=test_end,
        )
        folds.append(
            {
                "train_start": train_start.isoformat(),
                "train_end": train_end.isoformat(),
                "test_start": test_start.isoformat(),
                "test_end": test_end.isoformat(),
                "test_calmar": round(m.calmar, 3) if m else None,
                "test_annual_return": round(m.annual_return, 4) if m else None,
                "test_max_drawdown": round(m.max_drawdown, 4) if m else None,
                "test_sharpe": round(m.sharpe, 3) if m else None,
            }
        )
        if test_end >= end:
            break
        cursor_test_end = cursor_test_end + step

    calmars = [f["test_calmar"] for f in folds if f.get("test_calmar") is not None]
    summary = {
        "status": "ok" if folds else "insufficient",
        "fold_count": len(folds),
        "median_test_calmar": (
            round(sorted(calmars)[len(calmars) // 2], 3) if calmars else None
        ),
        "positive_fold_ratio": (
            round(sum(1 for c in calmars if c > 0) / len(calmars), 3) if calmars else None
        ),
    }
    return {
        "strategy_id": strategy_factory().strategy_id,
        "folds": folds,
        "summary": summary,
        "note": "Walk-forward lab; not used on daily default path.",
    }


def grid_search_walk_forward(
    factory_with_params: Callable[[dict[str, Any]], Strategy],
    param_grid: list[dict[str, Any]],
    bars: list[Bar],
    **kwargs: Any,
) -> dict[str, Any]:
    """Run walk_forward for each param set; rank by median_test_calmar."""
    rows = []
    for params in param_grid:
        wf = walk_forward(lambda p=params: factory_with_params(p), bars, **kwargs)
        rows.append(
            {
                "params": params,
                "summary": wf["summary"],
                "fold_count": wf["summary"].get("fold_count"),
            }
        )
    rows.sort(
        key=lambda r: (
            r["summary"].get("median_test_calmar")
            if r["summary"].get("median_test_calmar") is not None
            else -999
        ),
        reverse=True,
    )
    return {"results": rows, "best": rows[0] if rows else None}
