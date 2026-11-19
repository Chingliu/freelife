"""Phase-1 price / volume factors."""

from __future__ import annotations

from app.data.models import Bar
from app.indicators.ma import sma
from app.research.indicators import adx, momentum, realized_volatility


def _closes(bars: list[Bar]) -> list[float]:
    return [b.close for b in bars]


def trend_ma_align(bars: list[Bar]) -> float | None:
    """Score proxy: MA20>MA60>MA120 (+ADX boost). Raw in roughly [-1, 2]."""
    if len(bars) < 130:
        return None
    closes = _closes(bars)
    ma20 = sma(closes, 20)
    ma60 = sma(closes, 60)
    ma120 = sma(closes, 120)
    a20, a60, a120 = ma20[-1], ma60[-1], ma120[-1]
    if a20 is None or a60 is None or a120 is None:
        return None
    score = 0.0
    if a20 > a60:
        score += 1.0
    if a60 > a120:
        score += 1.0
    if closes[-1] > a20:
        score += 0.5
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    adx_s, _, _ = adx(highs, lows, closes, 14)
    if adx_s[-1] is not None:
        score += min(float(adx_s[-1]) / 50.0, 1.0)
    return score


def mom_20(bars: list[Bar]) -> float | None:
    m = momentum(_closes(bars), 20)
    return m[-1]


def mom_60(bars: list[Bar]) -> float | None:
    m = momentum(_closes(bars), 60)
    return m[-1]


def vol_20(bars: list[Bar]) -> float | None:
    """Lower vol better → raw is volatility (invert at percentile)."""
    v = realized_volatility(_closes(bars), 20, annualize=True)
    return v[-1]


def max_drawdown_60(bars: list[Bar]) -> float | None:
    """Max DD over last 60 sessions (negative or 0); higher (closer to 0) better."""
    if len(bars) < 60:
        return None
    closes = _closes(bars[-60:])
    peak = closes[0]
    mdd = 0.0
    for c in closes:
        peak = max(peak, c)
        if peak > 0:
            mdd = min(mdd, c / peak - 1.0)
    return mdd  # e.g. -0.12


def relative_strength_60(bars: list[Bar], bench: list[Bar]) -> float | None:
    if len(bars) < 61 or len(bench) < 61:
        return None
    # Align by date from the end using last common window length
    bmap = {b.trade_date: b.close for b in bench}
    paired: list[tuple[float, float]] = []
    for b in bars[-80:]:
        bc = bmap.get(b.trade_date)
        if bc is not None and bc > 0:
            paired.append((b.close, bc))
    if len(paired) < 61:
        return None
    s0, b0 = paired[-61]
    s1, b1 = paired[-1]
    if s0 <= 0 or b0 <= 0:
        return None
    return (s1 / s0) - (b1 / b0)


def liquidity_amount_20(bars: list[Bar]) -> float | None:
    if len(bars) < 20:
        return None
    chunk = bars[-20:]
    return sum(b.amount for b in chunk) / len(chunk)


def ma_stack_detail(bars: list[Bar]) -> str:
    if len(bars) < 120:
        return "bars insufficient for MA stack"
    closes = _closes(bars)
    ma20 = sma(closes, 20)[-1]
    ma60 = sma(closes, 60)[-1]
    ma120 = sma(closes, 120)[-1]
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    adx_s, _, _ = adx(highs, lows, closes, 14)
    adx_v = adx_s[-1]
    parts = [
        f"MA20={ma20:.2f}" if ma20 else "MA20=na",
        f"MA60={ma60:.2f}" if ma60 else "MA60=na",
        f"MA120={ma120:.2f}" if ma120 else "MA120=na",
        f"ADX={adx_v:.1f}" if adx_v is not None else "ADX=na",
    ]
    return ", ".join(parts)
