"""Research indicator library (Phase 1)."""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.data.models import Bar
from app.indicators.ma import sma
from app.indicators.macd_rsi import MacdPoint, ema, macd, rsi
from app.research.indicators.divergence import (
    detect_regular_divergences,
    pivot_highs,
    pivot_lows,
)


def _none_pad(n: int) -> list[float | None]:
    return [None] * n


def ema_series(values: list[float], window: int) -> list[float | None]:
    """EMA aligned to input; warm-up values before window are None."""
    if window <= 0:
        raise ValueError("window must be positive")
    if not values:
        return []
    raw = ema(values, window)
    out: list[float | None] = []
    for i, v in enumerate(raw):
        out.append(None if i + 1 < window else v)
    return out


def momentum(values: list[float], lookback: int) -> list[float | None]:
    """Simple return over lookback: p[t]/p[t-lookback] - 1."""
    out: list[float | None] = _none_pad(len(values))
    for i in range(lookback, len(values)):
        base = values[i - lookback]
        out[i] = (values[i] / base - 1.0) if base else None
    return out


def realized_volatility(
    values: list[float],
    window: int = 20,
    *,
    annualize: bool = True,
) -> list[float | None]:
    """Std of log returns over window; optional sqrt(252) annualization."""
    out: list[float | None] = _none_pad(len(values))
    if len(values) < 2:
        return out
    logrets: list[float | None] = [None]
    for i in range(1, len(values)):
        if values[i - 1] <= 0 or values[i] <= 0:
            logrets.append(None)
        else:
            logrets.append(math.log(values[i] / values[i - 1]))
    scale = math.sqrt(252.0) if annualize else 1.0
    for i in range(len(values)):
        if i + 1 < window + 1:
            continue
        chunk = logrets[i - window + 1 : i + 1]
        if any(x is None for x in chunk):
            continue
        vals = [float(x) for x in chunk]
        mean = sum(vals) / len(vals)
        var = sum((x - mean) ** 2 for x in vals) / max(len(vals) - 1, 1)
        out[i] = math.sqrt(var) * scale
    return out


def true_range(high: list[float], low: list[float], close: list[float]) -> list[float]:
    out: list[float] = []
    for i in range(len(close)):
        if i == 0:
            out.append(high[i] - low[i])
            continue
        out.append(
            max(
                high[i] - low[i],
                abs(high[i] - close[i - 1]),
                abs(low[i] - close[i - 1]),
            )
        )
    return out


def atr(
    high: list[float],
    low: list[float],
    close: list[float],
    window: int = 14,
) -> list[float | None]:
    tr = true_range(high, low, close)
    return sma(tr, window)


def bars_atr(bars: list[Bar], window: int = 14) -> list[float | None]:
    return atr(
        [b.high for b in bars],
        [b.low for b in bars],
        [b.close for b in bars],
        window,
    )


@dataclass(frozen=True)
class BollingerPoint:
    mid: float | None
    upper: float | None
    lower: float | None
    width: float | None


def bollinger(
    values: list[float],
    window: int = 20,
    num_std: float = 2.0,
) -> list[BollingerPoint]:
    mid = sma(values, window)
    out: list[BollingerPoint] = []
    for i in range(len(values)):
        if mid[i] is None:
            out.append(BollingerPoint(None, None, None, None))
            continue
        chunk = values[i + 1 - window : i + 1]
        mean = mid[i]
        assert mean is not None
        var = sum((x - mean) ** 2 for x in chunk) / window
        std = math.sqrt(var)
        upper = mean + num_std * std
        lower = mean - num_std * std
        width = (upper - lower) / mean if mean else None
        out.append(BollingerPoint(mean, upper, lower, width))
    return out


@dataclass(frozen=True)
class KdjPoint:
    k: float | None
    d: float | None
    j: float | None


def kdj(
    high: list[float],
    low: list[float],
    close: list[float],
    n: int = 9,
    m1: int = 3,
    m2: int = 3,
) -> list[KdjPoint]:
    length = len(close)
    rsv: list[float | None] = _none_pad(length)
    for i in range(length):
        if i + 1 < n:
            continue
        hh = max(high[i + 1 - n : i + 1])
        ll = min(low[i + 1 - n : i + 1])
        denom = hh - ll
        rsv[i] = 50.0 if denom == 0 else (close[i] - ll) / denom * 100.0

    k_vals: list[float | None] = _none_pad(length)
    d_vals: list[float | None] = _none_pad(length)
    j_vals: list[float | None] = _none_pad(length)
    k_prev, d_prev = 50.0, 50.0
    for i in range(length):
        if rsv[i] is None:
            continue
        k_prev = (k_prev * (m1 - 1) + float(rsv[i])) / m1
        d_prev = (d_prev * (m2 - 1) + k_prev) / m2
        k_vals[i] = k_prev
        d_vals[i] = d_prev
        j_vals[i] = 3 * k_prev - 2 * d_prev
    return [KdjPoint(k_vals[i], d_vals[i], j_vals[i]) for i in range(length)]


def bars_kdj(bars: list[Bar], n: int = 9) -> list[KdjPoint]:
    return kdj(
        [b.high for b in bars],
        [b.low for b in bars],
        [b.close for b in bars],
        n=n,
    )


def _wilder_smooth(values: list[float], window: int) -> list[float | None]:
    out: list[float | None] = _none_pad(len(values))
    if len(values) < window:
        return out
    seed = sum(values[:window]) / window
    out[window - 1] = seed
    prev = seed
    for i in range(window, len(values)):
        prev = (prev * (window - 1) + values[i]) / window
        out[i] = prev
    return out


def adx(
    high: list[float],
    low: list[float],
    close: list[float],
    window: int = 14,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """Return (adx, plus_di, minus_di)."""
    n = len(close)
    plus_dm = [0.0] * n
    minus_dm = [0.0] * n
    tr = true_range(high, low, close)
    for i in range(1, n):
        up = high[i] - high[i - 1]
        down = low[i - 1] - low[i]
        plus_dm[i] = up if up > down and up > 0 else 0.0
        minus_dm[i] = down if down > up and down > 0 else 0.0

    atr_s = _wilder_smooth(tr, window)
    plus_s = _wilder_smooth(plus_dm, window)
    minus_s = _wilder_smooth(minus_dm, window)

    plus_di: list[float | None] = _none_pad(n)
    minus_di: list[float | None] = _none_pad(n)
    dx: list[float | None] = _none_pad(n)
    for i in range(n):
        if atr_s[i] is None or not atr_s[i]:
            continue
        p = 100.0 * float(plus_s[i] or 0.0) / float(atr_s[i])
        m = 100.0 * float(minus_s[i] or 0.0) / float(atr_s[i])
        plus_di[i] = p
        minus_di[i] = m
        denom = p + m
        dx[i] = 0.0 if denom == 0 else abs(p - m) / denom * 100.0

    # ADX = Wilder smooth of DX (skip leading Nones)
    adx_out: list[float | None] = _none_pad(n)
    buf: list[float] = []
    prev: float | None = None
    for i, v in enumerate(dx):
        if v is None:
            continue
        if prev is None:
            buf.append(v)
            if len(buf) == window:
                prev = sum(buf) / window
                adx_out[i] = prev
            continue
        prev = (prev * (window - 1) + v) / window
        adx_out[i] = prev
    return adx_out, plus_di, minus_di


def bars_adx(
    bars: list[Bar], window: int = 14
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    return adx(
        [b.high for b in bars],
        [b.low for b in bars],
        [b.close for b in bars],
        window,
    )


def _linreg_slope(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    var_x = sum((x - mean_x) ** 2 for x in xs)
    if var_x == 0:
        return None
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    return cov / var_x


def rsrs(
    high: list[float],
    low: list[float],
    window: int = 18,
    z_window: int = 600,
) -> list[float | None]:
    """RSRS (阻力支撑相对强度) z-score of high~low beta."""
    n = len(high)
    beta: list[float | None] = _none_pad(n)
    for i in range(window - 1, n):
        ys = high[i + 1 - window : i + 1]
        xs = low[i + 1 - window : i + 1]
        beta[i] = _linreg_slope(xs, ys)

    out: list[float | None] = _none_pad(n)
    for i in range(n):
        if beta[i] is None:
            continue
        start = max(0, i + 1 - z_window)
        hist = [b for b in beta[start : i + 1] if b is not None]
        if len(hist) < max(30, window):
            continue
        mean = sum(hist) / len(hist)
        var = sum((x - mean) ** 2 for x in hist) / max(len(hist) - 1, 1)
        std = math.sqrt(var)
        out[i] = 0.0 if std == 0 else (float(beta[i]) - mean) / std
    return out


def bars_rsrs(bars: list[Bar], window: int = 18, z_window: int = 600) -> list[float | None]:
    return rsrs(
        [b.high for b in bars],
        [b.low for b in bars],
        window=window,
        z_window=z_window,
    )


def compute_indicator_snapshot(bars: list[Bar]) -> dict[str, float | None]:
    """Latest values for market-state reporting."""
    if len(bars) < 60:
        return {}
    closes = [b.close for b in bars]
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    ma5 = sma(closes, 5)
    ma20 = sma(closes, 20)
    ma60 = sma(closes, 60)
    macd_pts = macd(closes)
    rsi_v = rsi(closes, 14)
    atr_v = atr(highs, lows, closes, 14)
    adx_v, _, _ = adx(highs, lows, closes, 14)
    vol = realized_volatility(closes, 20)
    mom = momentum(closes, 20)
    bb = bollinger(closes, 20)
    last = -1
    return {
        "close": closes[last],
        "ma5": ma5[last],
        "ma20": ma20[last],
        "ma60": ma60[last],
        "macd_dif": macd_pts[last].dif,
        "macd_dea": macd_pts[last].dea,
        "rsi14": rsi_v[last],
        "atr14": atr_v[last],
        "adx14": adx_v[last],
        "vol20": vol[last],
        "mom20": mom[last],
        "bb_width": bb[last].width,
    }


__all__ = [
    "MacdPoint",
    "BollingerPoint",
    "KdjPoint",
    "sma",
    "ema",
    "ema_series",
    "macd",
    "rsi",
    "momentum",
    "realized_volatility",
    "true_range",
    "atr",
    "bars_atr",
    "bollinger",
    "kdj",
    "bars_kdj",
    "adx",
    "bars_adx",
    "rsrs",
    "bars_rsrs",
    "pivot_highs",
    "pivot_lows",
    "detect_regular_divergences",
    "compute_indicator_snapshot",
]
