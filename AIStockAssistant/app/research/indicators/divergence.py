"""Pivot and regular (classic) price–oscillator divergence detection."""

from __future__ import annotations


def _none_pad(n: int) -> list[float | None]:
    return [None] * n


def pivot_highs(
    series: list[float],
    left: int = 5,
    right: int = 5,
) -> list[float | None]:
    """
    Mark swing highs at the pivot bar index (not the confirmation bar).

    Index i is a pivot high iff series[i] is strictly greater than every other
    value in [i-left, i+right]. Requires i+right < len(series) (no look-ahead
    beyond available history when used in a full-series backtest).
    """
    if left < 1 or right < 1:
        raise ValueError("left and right must be >= 1")
    n = len(series)
    out: list[float | None] = _none_pad(n)
    for i in range(left, n - right):
        v = series[i]
        if all(v > series[j] for j in range(i - left, i + right + 1) if j != i):
            out[i] = v
    return out


def pivot_lows(
    series: list[float],
    left: int = 5,
    right: int = 5,
) -> list[float | None]:
    """Mark swing lows at the pivot bar index (strict local minimum)."""
    if left < 1 or right < 1:
        raise ValueError("left and right must be >= 1")
    n = len(series)
    out: list[float | None] = _none_pad(n)
    for i in range(left, n - right):
        v = series[i]
        if all(v < series[j] for j in range(i - left, i + right + 1) if j != i):
            out[i] = v
    return out


def _osc_ok(
    prev: float,
    cur: float,
    *,
    min_osc_delta: float,
    min_osc_rel: float,
) -> bool:
    if abs(cur - prev) < min_osc_delta:
        return False
    if min_osc_rel > 0:
        base = max(abs(prev), 1e-12)
        if abs(cur - prev) / base < min_osc_rel:
            return False
    return True


def detect_regular_divergences(
    price: list[float],
    osc: list[float | None],
    *,
    left: int = 5,
    right: int = 5,
    min_bars: int = 6,
    min_osc_delta: float = 3.0,
    min_osc_rel: float = 0.0,
) -> list[str | None]:
    """
    Regular bullish/bearish divergence events on the pivot *confirmation* bar.

    Uses price pivots; oscillator values are taken at the same pivot bar index
    (not independent osc pivots). Emits \"bullish\" or \"bearish\" at index
    pivot_idx + right; other bars are None.
    """
    if len(price) != len(osc):
        raise ValueError("price and osc must have the same length")
    n = len(price)
    out: list[str | None] = [None] * n
    if n < left + right + 2:
        return out

    ph = pivot_highs(price, left, right)
    pl = pivot_lows(price, left, right)

    low_pivots: list[tuple[int, float, float]] = []
    high_pivots: list[tuple[int, float, float]] = []

    for confirm in range(n):
        pivot_idx = confirm - right
        if pivot_idx < left:
            continue

        if pl[pivot_idx] is not None:
            o = osc[pivot_idx]
            if o is not None:
                price_v = float(pl[pivot_idx])
                if low_pivots:
                    prev_i, prev_p, prev_o = low_pivots[-1]
                    if pivot_idx - prev_i >= min_bars:
                        # bullish: price lower low, osc higher low
                        if (
                            price_v < prev_p
                            and float(o) > prev_o
                            and _osc_ok(
                                prev_o,
                                float(o),
                                min_osc_delta=min_osc_delta,
                                min_osc_rel=min_osc_rel,
                            )
                        ):
                            out[confirm] = "bullish"
                low_pivots.append((pivot_idx, price_v, float(o)))

        if ph[pivot_idx] is not None:
            o = osc[pivot_idx]
            if o is not None:
                price_v = float(ph[pivot_idx])
                if high_pivots:
                    prev_i, prev_p, prev_o = high_pivots[-1]
                    if pivot_idx - prev_i >= min_bars:
                        # bearish: price higher high, osc lower high
                        if (
                            price_v > prev_p
                            and float(o) < prev_o
                            and _osc_ok(
                                prev_o,
                                float(o),
                                min_osc_delta=min_osc_delta,
                                min_osc_rel=min_osc_rel,
                            )
                        ):
                            # Prefer not to overwrite bullish on same bar; bearish wins if both
                            # (rare). Keep last write.
                            out[confirm] = "bearish"
                high_pivots.append((pivot_idx, price_v, float(o)))

    return out
