from __future__ import annotations

from dataclasses import dataclass

from app.data.models import Bar


@dataclass(frozen=True)
class MacdPoint:
    dif: float | None
    dea: float | None
    hist: float | None


def ema(values: list[float], window: int) -> list[float]:
    if not values:
        return []
    k = 2 / (window + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def macd(
    closes: list[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> list[MacdPoint]:
    if len(closes) < slow:
        return [MacdPoint(None, None, None) for _ in closes]
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    dif = [f - s for f, s in zip(ema_fast, ema_slow)]
    dea = ema(dif, signal)
    hist = [d - e for d, e in zip(dif, dea)]
    return [
        MacdPoint(dif=d, dea=e, hist=h) for d, e, h in zip(dif, dea, hist)
    ]


def rsi(closes: list[float], window: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(closes)
    if len(closes) <= window:
        return out
    gains = 0.0
    losses = 0.0
    for i in range(1, window + 1):
        change = closes[i] - closes[i - 1]
        if change >= 0:
            gains += change
        else:
            losses -= change
    avg_gain = gains / window
    avg_loss = losses / window
    out[window] = 100.0 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss))
    for i in range(window + 1, len(closes)):
        change = closes[i] - closes[i - 1]
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        avg_gain = (avg_gain * (window - 1) + gain) / window
        avg_loss = (avg_loss * (window - 1) + loss) / window
        out[i] = (
            100.0
            if avg_loss == 0
            else 100 - (100 / (1 + avg_gain / avg_loss))
        )
    return out


def bars_macd(bars: list[Bar]) -> list[MacdPoint]:
    return macd([b.close for b in bars])


def bars_rsi(bars: list[Bar], window: int = 14) -> list[float | None]:
    return rsi([b.close for b in bars], window)
