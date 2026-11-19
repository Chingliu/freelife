from __future__ import annotations

import struct
from datetime import date
from pathlib import Path

from app.data.models import Bar
from app.data.tdx_day_reader import (
    FMT,
    RECORD_SIZE,
    parse_code_from_filename,
    price_divisor,
    read_day_file,
)

# Tongdaxin .day volume field is unsigned 32-bit.
_MAX_UINT32 = 0xFFFFFFFF


def _pack_bar(bar: Bar, divisor: float) -> bytes:
    d = bar.trade_date.year * 10000 + bar.trade_date.month * 100 + bar.trade_date.day
    vol = int(round(bar.volume))
    if vol < 0:
        vol = 0
    elif vol > _MAX_UINT32:
        vol = _MAX_UINT32
    return struct.pack(
        FMT,
        d,
        int(round(bar.open * divisor)),
        int(round(bar.high * divisor)),
        int(round(bar.low * divisor)),
        int(round(bar.close * divisor)),
        float(bar.amount),
        vol,
        0,
    )


def _bars_effectively_equal(a: Bar, b: Bar, *, price_eps: float = 1e-6) -> bool:
    """Compare OHLCV after packing scale (ignore tiny float noise)."""
    if a.trade_date != b.trade_date:
        return False
    for attr in ("open", "high", "low", "close"):
        if abs(float(getattr(a, attr)) - float(getattr(b, attr))) > price_eps:
            return False
    if abs(float(a.volume) - float(b.volume)) > 0.5:
        return False
    if abs(float(a.amount) - float(b.amount)) > max(1.0, 0.001 * max(abs(a.amount), abs(b.amount))):
        return False
    return True


def last_trade_date(path: Path) -> date | None:
    """Return the last trade_date in a .day file, or None if empty/missing."""
    if not path.is_file():
        return None
    size = path.stat().st_size
    if size < RECORD_SIZE or size % RECORD_SIZE != 0:
        return None
    raw = path.read_bytes()[-RECORD_SIZE:]
    d = struct.unpack_from("<I", raw, 0)[0]
    return date(d // 10000, (d % 10000) // 100, d % 100)


def append_day_bars(path: Path, bars: list[Bar], code: str | None = None) -> int:
    """
    Append bars with trade_date strictly after the file's last date.
    Creates parent dirs and the file if needed. Returns number of records written.
    """
    code = code or parse_code_from_filename(path)
    if not bars:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    last = last_trade_date(path)
    fresh = [b for b in bars if last is None or b.trade_date > last]
    if not fresh:
        return 0
    fresh.sort(key=lambda b: b.trade_date)
    div = price_divisor(code)
    blob = b"".join(_pack_bar(b, div) for b in fresh)
    with path.open("ab") as fh:
        fh.write(blob)
    return len(fresh)


def upsert_day_bars(path: Path, bars: list[Bar], code: str | None = None) -> int:
    """
    Merge bars by trade_date (incoming wins) and rewrite from the earliest
    incoming date onward. Fixes incomplete/corrupt same-day bars that
    append-only sync would leave stuck forever.

    Returns the number of bars inserted or updated (unchanged overlaps = 0).
    """
    code = code or parse_code_from_filename(path)
    if not bars:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    incoming = {b.trade_date: b for b in bars}
    min_in = min(incoming)

    existing: list[Bar] = []
    if path.is_file() and path.stat().st_size >= RECORD_SIZE:
        try:
            existing = read_day_file(path, code=code)
        except Exception:  # noqa: BLE001
            existing = []

    prefix = [b for b in existing if b.trade_date < min_in]
    tail: dict[date, Bar] = {b.trade_date: b for b in existing if b.trade_date >= min_in}

    changed = 0
    for td, bar in incoming.items():
        old = tail.get(td)
        if old is None or not _bars_effectively_equal(old, bar):
            changed += 1
        # Always prefer HQ/incoming for overlapping dates.
        tail[td] = bar

    if changed == 0:
        return 0

    div = price_divisor(code)
    ordered = prefix + [tail[d] for d in sorted(tail)]
    path.write_bytes(b"".join(_pack_bar(b, div) for b in ordered))
    return changed


def trim_day_bars_after(path: Path, max_date: date, code: str | None = None) -> int:
    """
    Drop bars with trade_date > max_date (incomplete intraday session).
    Returns number of records removed.
    """
    if not path.is_file() or path.stat().st_size < RECORD_SIZE:
        return 0
    code = code or parse_code_from_filename(path)
    try:
        existing = read_day_file(path, code=code)
    except Exception:  # noqa: BLE001
        return 0
    kept = [b for b in existing if b.trade_date <= max_date]
    removed = len(existing) - len(kept)
    if removed == 0:
        return 0
    div = price_divisor(code)
    path.write_bytes(b"".join(_pack_bar(b, div) for b in kept))
    return removed
