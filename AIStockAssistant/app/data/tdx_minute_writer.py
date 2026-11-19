from __future__ import annotations

import struct
from datetime import datetime
from pathlib import Path

from app.data.models import MinuteBar
from app.data.tdx_day_reader import parse_code_from_filename
from app.data.tdx_minute_reader import FMT, RECORD_SIZE, read_minute_file


def _pack_date(ts: datetime) -> int:
    return (ts.year - 2004) * 2048 + ts.month * 100 + ts.day


def _pack_time(ts: datetime) -> int:
    return ts.hour * 100 + ts.minute


def _pack_bar(bar: MinuteBar) -> bytes:
    return struct.pack(
        FMT,
        _pack_date(bar.trade_time),
        _pack_time(bar.trade_time),
        float(bar.open),
        float(bar.high),
        float(bar.low),
        float(bar.close),
        float(bar.amount),
        int(round(max(bar.volume, 0.0))),
    )


def last_minute_time(path: Path) -> datetime | None:
    if not path.is_file():
        return None
    size = path.stat().st_size
    if size < RECORD_SIZE or size % RECORD_SIZE != 0:
        return None
    bars = read_minute_file(path)
    return bars[-1].trade_time if bars else None


def write_minute_file(path: Path, bars: list[MinuteBar], *, replace: bool = False) -> int:
    """Write bars to .lc1/.lc5. If replace=False, append only newer bars."""
    if not bars:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    bars = sorted(bars, key=lambda b: b.trade_time)
    if replace or not path.is_file() or path.stat().st_size == 0:
        blob = b"".join(_pack_bar(b) for b in bars)
        path.write_bytes(blob)
        return len(bars)

    last = last_minute_time(path)
    fresh = [b for b in bars if last is None or b.trade_time > last]
    if not fresh:
        return 0
    with path.open("ab") as fh:
        fh.write(b"".join(_pack_bar(b) for b in fresh))
    return len(fresh)


def minute_path_for(
    vipdoc: Path,
    code: str,
    freq: str = "1m",
) -> Path:
    """Intended vipdoc path for a code (may not exist yet)."""
    code = code.lower().strip()
    market = code[:2] if code[:2] in {"sh", "sz", "bj"} else "sh"
    if not code.startswith(market):
        code = f"{market}{code}"
    folder = "minline" if freq in {"1m", "1", "lc1"} else "fzline"
    suffix = ".lc1" if folder == "minline" else ".lc5"
    return Path(vipdoc) / market / folder / f"{code}{suffix}"


def parse_code_from_minute_path(path: Path) -> str:
    return parse_code_from_filename(path)
