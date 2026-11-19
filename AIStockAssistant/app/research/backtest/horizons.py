"""Multi-horizon and rolling performance for Phase-2 research lab."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.research.backtest.metrics import compute_metrics
from app.research.backtest.types import PerformanceMetrics, Trade

# Approximate trading days per calendar year
_TD_YEAR = 252
_MIN_BARS = {
    "3y": _TD_YEAR * 3,
    "5y": _TD_YEAR * 5,
    "10y": _TD_YEAR * 10,
}
_CAL_YEARS = {"3y": 3, "5y": 5, "10y": 10}


def metrics_dict(m: PerformanceMetrics | None, *, status: str = "ok") -> dict[str, Any]:
    if m is None or status != "ok":
        return {
            "status": status if status != "ok" else "insufficient",
            "annual_return": None,
            "max_drawdown": None,
            "sharpe": None,
            "calmar": None,
            "win_rate": None,
            "trades": None,
        }
    return {
        "status": "ok",
        "annual_return": round(m.annual_return, 4),
        "max_drawdown": round(m.max_drawdown, 4),
        "sharpe": round(m.sharpe, 3),
        "calmar": round(m.calmar, 3),
        "win_rate": round(m.win_rate, 3),
        "trades": m.trades,
    }


def _slice_indices(
    dates: list[date],
    *,
    start: date | None = None,
    end: date | None = None,
) -> tuple[int, int] | None:
    if not dates:
        return None
    lo = 0
    hi = len(dates) - 1
    if start is not None:
        while lo <= hi and dates[lo] < start:
            lo += 1
    if end is not None:
        while hi >= lo and dates[hi] > end:
            hi -= 1
    if lo > hi:
        return None
    return lo, hi


def metrics_on_slice(
    equity: list[float],
    dates: list[date],
    positions: list[float],
    trades: list[Trade],
    *,
    start: date | None = None,
    end: date | None = None,
) -> PerformanceMetrics | None:
    """
    Performance on [start, end] with equity rebased to 1.0 at slice start.
    Warmup signals may exist before start; only path stats inside the window count.
    """
    bounds = _slice_indices(dates, start=start, end=end)
    if bounds is None:
        return None
    lo, hi = bounds
    if hi - lo + 1 < 5:
        return None
    base = equity[lo]
    if base <= 0:
        return None
    eq = [e / base for e in equity[lo : hi + 1]]
    dts = dates[lo : hi + 1]
    pos = positions[lo : hi + 1]
    # Trades that close inside the window (or open and still open at end)
    win_trades: list[Trade] = []
    for t in trades:
        exit_d = t.exit_date or dts[-1]
        if exit_d < dts[0] or t.entry_date > dts[-1]:
            continue
        if t.entry_date >= dts[0] and exit_d <= dts[-1]:
            win_trades.append(t)
    return compute_metrics(eq, dts, pos, win_trades)


def metrics_for_windows(
    equity: list[float],
    dates: list[date],
    positions: list[float],
    trades: list[Trade],
    *,
    windows: tuple[str, ...] = ("3y", "5y", "10y"),
) -> dict[str, dict[str, Any]]:
    """Calendar lookback windows ending at last bar date."""
    out: dict[str, dict[str, Any]] = {}
    if not dates:
        for w in windows:
            out[w] = metrics_dict(None, status="insufficient")
        return out
    end = dates[-1]
    n = len(dates)
    for w in windows:
        need = _MIN_BARS.get(w, _TD_YEAR * 3)
        cal_y = _CAL_YEARS.get(w, 3)
        if n < need:
            out[w] = metrics_dict(None, status="insufficient")
            continue
        start = end - timedelta(days=365 * cal_y)
        m = metrics_on_slice(equity, dates, positions, trades, start=start, end=end)
        if m is None:
            out[w] = metrics_dict(None, status="insufficient")
        else:
            out[w] = metrics_dict(m)
    return out


def rolling_calmar_series(
    equity: list[float],
    dates: list[date],
    positions: list[float],
    trades: list[Trade],
    *,
    window: int = 252,
    step: int = 63,
) -> list[dict[str, Any]]:
    """Rolling Calmar ending at each step; last point always included."""
    series: list[dict[str, Any]] = []
    n = len(dates)
    if n < window:
        return series
    ends = list(range(window - 1, n, step))
    if ends[-1] != n - 1:
        ends.append(n - 1)
    for end_i in ends:
        start_i = end_i - window + 1
        m = metrics_on_slice(
            equity,
            dates,
            positions,
            trades,
            start=dates[start_i],
            end=dates[end_i],
        )
        series.append(
            {
                "end_date": dates[end_i].isoformat(),
                "calmar": round(m.calmar, 3) if m else None,
                "annual_return": round(m.annual_return, 4) if m else None,
                "max_drawdown": round(m.max_drawdown, 4) if m else None,
            }
        )
    return series


def rolling_calmar_summary(
    equity: list[float],
    dates: list[date],
    positions: list[float],
    trades: list[Trade],
    *,
    window: int = 252,
) -> dict[str, Any]:
    series = rolling_calmar_series(
        equity, dates, positions, trades, window=window, step=63
    )
    if not series:
        return {
            "status": "insufficient",
            "last": None,
            "series_tail": [],
            "bottom_streak": 0,
        }
    last = series[-1].get("calmar")
    return {
        "status": "ok",
        "last": last,
        "series_tail": series[-8:],
        "bottom_streak": 0,  # filled later vs peers
    }


def assign_lifecycles(
    rows: list[dict[str, Any]],
    *,
    bottom_pct: float = 0.30,
    demote_streak: int = 3,
) -> None:
    """
    Mutate rows in-place with lifecycle active|watch|demoted.
    Rules (conservative):
    - watch: rolling 12m Calmar in bottom 30% AND metrics_3y.calmar <= 0 (when ok)
    - demoted: last `demote_streak` quarterly rolling points all in bottom 30% among peers
      (approximated: last N rolling points each rank in bottom cohort vs peers' last N)
    """
    n = len(rows)
    if n == 0:
        return

    # Rank by last rolling calmar (None → worst)
    indexed = []
    for i, r in enumerate(rows):
        rc = r.get("rolling_calmar_12m") or {}
        val = rc.get("last")
        indexed.append((i, float("-inf") if val is None else float(val)))
    indexed.sort(key=lambda x: x[1])
    cutoff = max(1, int(n * bottom_pct))
    bottom_idx = {i for i, _ in indexed[:cutoff]}

    # Peer bottom streak: compare each strategy's series_tail calmar ranks
    # Simpler rule: if last demote_streak points of rolling series are all below
    # peer median of corresponding last points → demoted when also in bottom_idx
    for i, r in enumerate(rows):
        m3 = r.get("metrics_3y") or {}
        cal3 = m3.get("calmar")
        in_bottom = i in bottom_idx
        poor_3y = m3.get("status") == "ok" and cal3 is not None and cal3 <= 0
        insufficient_3y = m3.get("status") == "insufficient"

        rc = r.get("rolling_calmar_12m") or {}
        tail = rc.get("series_tail") or []
        # Count how many of last demote_streak points are None or negative
        last_pts = tail[-demote_streak:] if tail else []
        weak_streak = (
            len(last_pts) >= demote_streak
            and all(
                (p.get("calmar") is None or float(p["calmar"]) <= 0) for p in last_pts
            )
        )

        if in_bottom and weak_streak and not insufficient_3y:
            lifecycle = "demoted"
        elif in_bottom and (poor_3y or (insufficient_3y and (rc.get("last") or 0) <= 0)):
            lifecycle = "watch"
        elif in_bottom and poor_3y:
            lifecycle = "watch"
        else:
            lifecycle = "active"

        # Prefer watch over active when bottom + non-positive 3y
        if lifecycle == "active" and in_bottom and poor_3y:
            lifecycle = "watch"

        r["lifecycle"] = lifecycle
        if isinstance(rc, dict):
            rc["bottom_streak"] = demote_streak if weak_streak else 0
            r["rolling_calmar_12m"] = rc


def enrich_result_horizons(result: Any) -> dict[str, Any]:
    """Build horizon + rolling fields from a BacktestResult."""
    dates = [d for d, _ in result.equity_curve]
    equity = [e for _, e in result.equity_curve]
    positions = list(result.positions)
    trades = list(result.trades)
    windows = metrics_for_windows(equity, dates, positions, trades)
    rolling = rolling_calmar_summary(equity, dates, positions, trades, window=252)
    return {
        "metrics_3y": windows.get("3y", metrics_dict(None, status="insufficient")),
        "metrics_5y": windows.get("5y", metrics_dict(None, status="insufficient")),
        "metrics_10y": windows.get("10y", metrics_dict(None, status="insufficient")),
        "rolling_calmar_12m": rolling,
    }
