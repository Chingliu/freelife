from __future__ import annotations

import struct
from datetime import date
from pathlib import Path

from app.data.models import Bar

RECORD_SIZE = 32
FMT = "<IIIIIfII"


def parse_code_from_filename(path: Path) -> str:
    return path.stem.lower()


def price_divisor(code: str) -> float:
    """Tongdaxin .day OHLC integer scale by instrument type.

    Stocks / indices: /100
    Funds / ETFs / (non-CB) bonds / reverse repo: /1000
    Convertible bonds (sh11xxxx, sz12xxxx): /10000
    """
    code = code.lower().strip()
    market = ""
    num = code
    if len(code) >= 8 and code[:2] in {"sh", "sz", "bj"}:
        market, num = code[:2], code[2:]
    if not num.isdigit():
        return 100.0

    # Convertible bonds trade near par (~100); stored as price * 10000.
    if market == "sh" and num.startswith("11"):
        return 10000.0
    if market == "sz" and num.startswith("12"):
        return 10000.0

    # SH funds/ETFs (5xxxxx), reverse repo (204xxx), treasury-ish (01/02).
    if market == "sh":
        if num.startswith("5") or num.startswith("204"):
            return 1000.0
        if num.startswith(("01", "02")):
            return 1000.0

    # SZ funds / bonds / ETFs / reverse repo (1xxxxx); CBs handled above.
    if market == "sz" and num.startswith("1"):
        return 1000.0

    # A-shares, ChiNext, B-shares, indices, BJ stocks: /100
    return 100.0


def read_day_file(path: Path, code: str | None = None) -> list[Bar]:
    code = code or parse_code_from_filename(path)
    raw = path.read_bytes()
    if len(raw) % RECORD_SIZE != 0:
        raise ValueError(f"bad day file size {len(raw)} for {path}")
    div = price_divisor(code)
    bars: list[Bar] = []
    for i in range(0, len(raw), RECORD_SIZE):
        d, o, h, l, c, amount, vol, _ = struct.unpack(FMT, raw[i : i + RECORD_SIZE])
        y, m, day = d // 10000, (d % 10000) // 100, d % 100
        bars.append(
            Bar(
                code=code,
                trade_date=date(y, m, day),
                open=o / div,
                high=h / div,
                low=l / div,
                close=c / div,
                volume=float(vol),
                amount=float(amount),
            )
        )
    return bars


def filter_bars(
    bars: list[Bar],
    start: date | None = None,
    end: date | None = None,
) -> list[Bar]:
    return [
        b
        for b in bars
        if (start is None or b.trade_date >= start)
        and (end is None or b.trade_date <= end)
    ]
