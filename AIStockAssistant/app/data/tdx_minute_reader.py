from __future__ import annotations

import struct
from datetime import datetime
from pathlib import Path

from app.data.models import MinuteBar
from app.data.tdx_day_reader import parse_code_from_filename, price_divisor

# Tongdaxin .lc1 / .lc5: 32-byte records (28-byte payload + 4 reserved)
RECORD_SIZE = 32
FMT = "<HHfffffI4x"


def _decode_date(raw: int) -> tuple[int, int, int]:
    """Decode packed date used by vipdoc minute files."""
    year = (raw // 2048) + 2004
    month = (raw % 2048) // 100
    day = (raw % 2048) % 100
    return year, month, day


def read_minute_file(
    path: Path,
    code: str | None = None,
    *,
    use_price_divisor: bool = False,
) -> list[MinuteBar]:
    """Read .lc1 (1-min) or .lc5 (5-min) vipdoc file.

    OHLC in minute files are typically already float prices (unlike .day ints).
    Set use_price_divisor=True only if a local dump stores scaled integers.
    """
    code = code or parse_code_from_filename(path)
    raw = path.read_bytes()
    if len(raw) == 0:
        return []
    if len(raw) % RECORD_SIZE != 0:
        raise ValueError(f"bad minute file size {len(raw)} for {path}")
    div = price_divisor(code) if use_price_divisor else 1.0
    bars: list[MinuteBar] = []
    for i in range(0, len(raw), RECORD_SIZE):
        d_raw, t_raw, o, h, l, c, amount, vol = struct.unpack(
            FMT, raw[i : i + RECORD_SIZE]
        )
        year, month, day = _decode_date(d_raw)
        hh, mm = divmod(int(t_raw), 100)
        try:
            ts = datetime(year, month, day, hh, mm)
        except ValueError:
            continue
        bars.append(
            MinuteBar(
                code=code,
                trade_time=ts,
                open=float(o) / div,
                high=float(h) / div,
                low=float(l) / div,
                close=float(c) / div,
                volume=float(vol),
                amount=float(amount),
            )
        )
    return bars


def filter_minute_bars(
    bars: list[MinuteBar],
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[MinuteBar]:
    return [
        b
        for b in bars
        if (start is None or b.trade_time >= start)
        and (end is None or b.trade_time <= end)
    ]
