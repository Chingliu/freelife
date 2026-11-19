from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from pytdx.hq import TdxHq_API

from app.data.models import MinuteBar
from app.data.pytdx_updater import _DEFAULT_HOSTS, _MARKET_MAP, _connect
from app.data.tdx_minute_writer import minute_path_for, write_minute_file

logger = logging.getLogger(__name__)

# pytdx category: 0=5min, 7/8=1min (servers vary; try 8 then 7)
_FREQ_CATEGORY: dict[str, tuple[int, ...]] = {
    "1m": (8, 7),
    "1": (8, 7),
    "lc1": (8, 7),
    "5m": (0,),
    "5": (0,),
    "lc5": (0,),
}


@dataclass(frozen=True)
class PytdxMinuteResult:
    ok: bool
    message: str
    code: str = ""
    freq: str = ""
    bars_written: int = 0
    path: str = ""


def _row_to_minute(code: str, row: dict[str, Any]) -> MinuteBar | None:
    try:
        ts = datetime(
            int(row["year"]),
            int(row["month"]),
            int(row["day"]),
            int(row.get("hour") or 0),
            int(row.get("minute") or 0),
        )
    except (KeyError, TypeError, ValueError):
        return None
    # pytdx minute vol is already in shares (amount ≈ close * vol)
    return MinuteBar(
        code=code,
        trade_time=ts,
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=float(row.get("vol") or 0.0),
        amount=float(row.get("amount") or 0.0),
    )


def _parse_code(code: str) -> tuple[str, int, str] | None:
    code = code.lower().strip().replace(".", "")
    if len(code) == 6 and code.isdigit():
        market = "sh" if code.startswith(("5", "6", "9")) else "sz"
        code = f"{market}{code}"
    if len(code) < 8:
        return None
    market, symbol = code[:2], code[2:]
    if market not in _MARKET_MAP or not symbol.isdigit():
        return None
    return code, _MARKET_MAP[market], symbol


def _fetch_minute_pages(
    api: TdxHq_API,
    market: int,
    symbol: str,
    categories: tuple[int, ...],
    max_bars: int,
) -> list[dict[str, Any]]:
    """Fetch up to max_bars newest minute bars (pytdx returns newest-first pages)."""
    max_bars = max(1, min(int(max_bars), 8000))
    page = 800
    collected: list[dict[str, Any]] = []
    used_cat: int | None = None
    for cat in categories:
        probe = api.get_security_bars(cat, market, symbol, 0, 10)
        if probe:
            used_cat = cat
            break
    if used_cat is None:
        return []

    start = 0
    while len(collected) < max_bars:
        n = min(page, max_bars - len(collected))
        rows = api.get_security_bars(used_cat, market, symbol, start, n)
        if not rows:
            break
        collected.extend(list(rows))
        if len(rows) < n:
            break
        start += len(rows)
    # API pages are typically newest→oldest within each page; reverse to chronological
    collected.reverse()
    # de-dup by datetime
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for row in collected:
        key = str(row.get("datetime") or "")
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def fetch_minute_bars_pytdx(
    code: str,
    *,
    freq: str = "1m",
    max_bars: int = 2400,
    hosts: Iterable[tuple[str, int]] | None = None,
) -> list[MinuteBar]:
    parsed = _parse_code(code)
    if parsed is None:
        return []
    full, market, symbol = parsed
    cats = _FREQ_CATEGORY.get(freq, (8, 7))
    host_list = tuple(hosts) if hosts is not None else _DEFAULT_HOSTS
    api = _connect(host_list)
    if api is None:
        return []
    try:
        rows = _fetch_minute_pages(api, market, symbol, cats, max_bars)
        out: list[MinuteBar] = []
        for row in rows:
            bar = _row_to_minute(full, row)
            if bar is not None:
                out.append(bar)
        out.sort(key=lambda b: b.trade_time)
        return out
    finally:
        try:
            api.disconnect()
        except Exception:  # noqa: BLE001
            pass


def sync_minute_to_vipdoc(
    vipdoc: Path,
    code: str,
    *,
    freq: str = "1m",
    max_bars: int = 2400,
    replace: bool = False,
    hosts: Iterable[tuple[str, int]] | None = None,
) -> PytdxMinuteResult:
    """Download minute bars via pytdx and write into vipdoc minline/fzline."""
    parsed = _parse_code(code)
    if parsed is None:
        return PytdxMinuteResult(ok=False, message=f"bad code: {code}", code=code, freq=freq)
    full, _, _ = parsed
    bars = fetch_minute_bars_pytdx(full, freq=freq, max_bars=max_bars, hosts=hosts)
    if not bars:
        return PytdxMinuteResult(
            ok=False,
            message="pytdx returned no minute bars (network or symbol)",
            code=full,
            freq=freq,
        )
    path = minute_path_for(vipdoc, full, freq=freq)
    n = write_minute_file(path, bars, replace=replace)
    msg = f"minute sync ok code={full} freq={freq} wrote={n} total_fetched={len(bars)} path={path}"
    logger.info(msg)
    return PytdxMinuteResult(
        ok=True,
        message=msg,
        code=full,
        freq=freq,
        bars_written=n,
        path=str(path),
    )


def sync_minutes_batch(
    vipdoc: Path,
    codes: list[str],
    *,
    freq: str = "1m",
    max_bars: int = 2400,
    replace: bool = False,
) -> list[PytdxMinuteResult]:
    return [
        sync_minute_to_vipdoc(
            vipdoc, c, freq=freq, max_bars=max_bars, replace=replace
        )
        for c in codes
    ]
