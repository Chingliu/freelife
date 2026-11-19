from __future__ import annotations

from app.data.models import Bar


def sma(values: list[float], window: int) -> list[float | None]:
    if window <= 0:
        raise ValueError("window must be positive")
    out: list[float | None] = []
    for i in range(len(values)):
        if i + 1 < window:
            out.append(None)
            continue
        chunk = values[i + 1 - window : i + 1]
        out.append(sum(chunk) / window)
    return out


def bars_close_sma(bars: list[Bar], window: int) -> list[float | None]:
    return sma([b.close for b in bars], window)
