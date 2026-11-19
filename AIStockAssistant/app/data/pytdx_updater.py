from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from pytdx.hq import TdxHq_API

from app.data.day_bar_validate import (
    bars_match,
    continuity_ok,
    effective_target,
    filter_bars_through,
)
from app.data.models import Bar
from app.data.session_calendar import settled_as_of
from app.data.tdx_day_reader import read_day_file
from app.data.tdx_day_writer import last_trade_date, trim_day_bars_after, upsert_day_bars

logger = logging.getLogger(__name__)

# Prefer known-reachable hosts first; then common public HQ endpoints.
_DEFAULT_HOSTS: tuple[tuple[str, int], ...] = (
    ("180.153.18.170", 7709),
    ("180.153.39.51", 7709),
    ("114.80.80.222", 7709),
    ("119.147.212.81", 7709),
    ("218.75.126.9", 7709),
    ("211.100.23.120", 7709),
    ("14.17.75.71", 7709),
    ("113.105.73.88", 7709),
)

# Default: pytdx volumes are in "hands" (100 shares); many vipdoc .day files store shares.
_VOL_SCALE = 100.0

_MARKET_MAP = {"sz": 0, "sh": 1, "bj": 2}

# Per-symbol attempts inside a chunk (1 initial + retries).
_DEFAULT_SYMBOL_RETRIES = 2
# Extra full pass over symbols that still failed after chunk retries.
_DEFAULT_SECOND_PASS_RETRIES = 3


@dataclass(frozen=True)
class PytdxUpdateResult:
    ok: bool
    message: str
    files_scanned: int = 0
    files_updated: int = 0
    bars_appended: int = 0
    errors: int = 0


def list_day_files(vipdoc: Path) -> list[Path]:
    vipdoc = Path(vipdoc)
    files: list[Path] = []
    for market in ("sh", "sz", "bj"):
        lday = vipdoc / market / "lday"
        if lday.is_dir():
            files.extend(sorted(lday.glob("*.day")))
    return files


def day_path_for(vipdoc: Path, code: str) -> Path | None:
    """Resolve vipdoc lday path for a code like sh510300."""
    stem = code.strip().lower()
    if len(stem) < 8:
        return None
    market = stem[:2]
    if market not in _MARKET_MAP:
        return None
    path = Path(vipdoc) / market / "lday" / f"{stem}.day"
    return path if path.is_file() else None


def code_from_day_path(path: Path) -> tuple[str, int, str] | None:
    """Return (full_code, market_id, symbol6) or None if unusable."""
    stem = path.stem.lower()
    if len(stem) < 8:
        return None
    market = stem[:2]
    symbol = stem[2:]
    if market not in _MARKET_MAP or not symbol.isdigit():
        return None
    return stem, _MARKET_MAP[market], symbol


def _bars_from_raw(
    code: str,
    rows: Iterable[dict[str, Any]],
    after: date | None,
    *,
    vol_scale: float = _VOL_SCALE,
) -> list[Bar]:
    out: list[Bar] = []
    for row in rows:
        try:
            td = date(int(row["year"]), int(row["month"]), int(row["day"]))
        except (KeyError, TypeError, ValueError):
            continue
        if after is not None and td <= after:
            continue
        out.append(
            Bar(
                code=code,
                trade_date=td,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("vol") or 0.0) * vol_scale,
                amount=float(row.get("amount") or 0.0),
            )
        )
    return out


def _infer_vol_scale(
    path: Path,
    code: str,
    rows: Iterable[dict[str, Any]],
) -> float:
    """
    Infer pytdx->vipdoc volume multiplier from overlapping trade dates.

    Some .day files (often written by the Tongdaxin client) already store the
    same volume unit as pytdx (scale=1). Others store share counts (scale=100).
    Blindly using 100 overflows uint32 on liquid ETFs like sh588000.

    Prefer the *most recent* overlapping bars: vipdoc history can mix both
    units after partial updates.
    """
    if not path.is_file():
        return _VOL_SCALE
    try:
        local = {b.trade_date: b for b in read_day_file(path, code=code)}
    except Exception:  # noqa: BLE001
        return _VOL_SCALE

    samples: list[tuple[date, float]] = []
    for row in rows:
        try:
            td = date(int(row["year"]), int(row["month"]), int(row["day"]))
        except (KeyError, TypeError, ValueError):
            continue
        bar = local.get(td)
        if bar is None:
            continue
        # Skip corrupt/incomplete local bars (price or amount diverge from HQ).
        pc = float(row.get("close") or 0.0)
        if pc > 0 and abs(bar.close - pc) / pc > 0.02:
            continue
        pa = float(row.get("amount") or 0.0)
        if pa > 0 and abs(bar.amount - pa) / pa > 0.02:
            continue
        pv = float(row.get("vol") or 0.0)
        if pv <= 0 or bar.volume <= 0:
            continue
        samples.append((td, bar.volume / pv))

    if not samples:
        return _VOL_SCALE

    samples.sort(key=lambda x: x[0])
    recent = samples[-8:]
    near_one = sum(1 for _, r in recent if 0.5 <= r <= 2.0)
    near_hundred = sum(1 for _, r in recent if 50.0 <= r <= 200.0)
    if near_one == 0 and near_hundred == 0:
        return _VOL_SCALE
    scale = 1.0 if near_one >= near_hundred else _VOL_SCALE
    if scale != _VOL_SCALE:
        logger.info(
            "pytdx vol_scale=%s for %s (recent near1=%s near100=%s)",
            scale,
            code,
            near_one,
            near_hundred,
        )
    return scale


def _connect(hosts: Iterable[tuple[str, int]], timeout: float = 3.0) -> TdxHq_API | None:
    api = TdxHq_API(multithread=True, heartbeat=True)
    for host, port in hosts:
        try:
            if api.connect(host, port, time_out=timeout):
                logger.info("pytdx connected %s:%s", host, port)
                return api
        except Exception as exc:  # noqa: BLE001
            logger.debug("pytdx connect failed %s:%s: %s", host, port, exc)
    return None


def _disconnect(api: TdxHq_API | None) -> None:
    if api is None:
        return
    try:
        api.disconnect()
    except Exception:  # noqa: BLE001
        pass


def _fetch_bars(api: TdxHq_API, market: int, symbol: str, count: int) -> list[dict[str, Any]]:
    rows = api.get_security_bars(9, market, symbol, 0, count)
    if not rows and market == 1 and symbol.startswith("000"):
        rows = api.get_index_bars(9, market, symbol, 0, count)
    return list(rows or [])


def _update_one(
    api: TdxHq_API,
    path: Path,
    bar_count: int,
    *,
    target_as_of: date,
) -> int:
    """
    Fetch HQ bars and sync one .day file under the settled-session policy.

    - Never write bars after ``target_as_of`` (intraday / unformed session).
    - For each HQ day through the settled target:
        * local missing → write if continuity vs prior close passes
        * local matches HQ → skip (no rewrite)
        * local diverges → rewrite with HQ only if HQ passes continuity
    - Trim any local bars after the settled target.

    Returns bars inserted/updated (0 when verify-ok / nothing to do).
    """
    parsed = code_from_day_path(path)
    if parsed is None:
        return 0
    code, market, symbol = parsed
    rows = _fetch_bars(api, market, symbol, bar_count)
    vol_scale = _infer_vol_scale(path, code, rows)
    hq_all = _bars_from_raw(code, rows, after=None, vol_scale=vol_scale)
    hq_bars = filter_bars_through(hq_all, target_as_of)
    target = effective_target(hq_bars, target_as_of)
    if target is None:
        logger.info("pytdx %s: no HQ bars <= %s", code, target_as_of.isoformat())
        return 0

    trimmed = trim_day_bars_after(path, target, code=code)
    if trimmed:
        logger.info(
            "pytdx %s: trimmed %s post-settled bar(s) after %s",
            code,
            trimmed,
            target.isoformat(),
        )

    try:
        existing = read_day_file(path, code=code) if path.is_file() else []
    except Exception:  # noqa: BLE001
        existing = []
    existing_by = {b.trade_date: b for b in existing}

    # Merge view for continuity as we accept HQ bars chronologically.
    merged = dict(existing_by)
    writable: list[Bar] = []
    for hq_bar in sorted(hq_bars, key=lambda b: b.trade_date):
        if hq_bar.trade_date > target:
            continue
        local = existing_by.get(hq_bar.trade_date)
        if local is not None and bars_match(local, hq_bar):
            continue
        prior_dates = [d for d in merged if d < hq_bar.trade_date]
        prior = merged[max(prior_dates)] if prior_dates else None
        if not continuity_ok(prior, hq_bar):
            logger.warning(
                "pytdx %s %s: reject HQ close=%s (prior=%s)%s",
                code,
                hq_bar.trade_date.isoformat(),
                hq_bar.close,
                prior.close if prior else None,
                f"; keep local={local.close}" if local is not None else "",
            )
            continue
        if local is None:
            logger.info(
                "pytdx %s %s: append settled bar close=%s",
                code,
                hq_bar.trade_date.isoformat(),
                hq_bar.close,
            )
        else:
            logger.warning(
                "pytdx %s %s: cross-check mismatch local=%s hq=%s; repairing",
                code,
                hq_bar.trade_date.isoformat(),
                local.close,
                hq_bar.close,
            )
        writable.append(hq_bar)
        merged[hq_bar.trade_date] = hq_bar

    if not writable:
        return 0
    return upsert_day_bars(path, writable, code=code)


def _paths_lagging(paths: Iterable[Path], min_as_of: date) -> list[Path]:
    """Local files whose last trade_date is older than min_as_of."""
    out: list[Path] = []
    for path in paths:
        ltd = last_trade_date(path)
        if ltd is None or ltd < min_as_of:
            out.append(path)
    return out


def _update_chunk(
    paths: list[Path],
    hosts: tuple[tuple[str, int], ...],
    bar_count: int,
    *,
    target_as_of: date,
    retries: int = _DEFAULT_SYMBOL_RETRIES,
    retry_sleep: float = 0.2,
) -> tuple[int, int, list[Path]]:
    """
    Process a chunk with one shared connection.
    Returns (files_updated, bars_appended, failed_paths).
    """
    if not paths:
        return 0, 0, []
    api = _connect(hosts)
    if api is None:
        return 0, 0, list(paths)

    updated = 0
    appended = 0
    failed: list[Path] = []
    attempts = max(1, int(retries) + 1)
    try:
        for path in paths:
            parsed = code_from_day_path(path)
            if parsed is None:
                continue
            last_exc: Exception | None = None
            ok = False
            for attempt in range(attempts):
                try:
                    if api is None:
                        api = _connect(hosts)
                        if api is None:
                            raise RuntimeError("cannot reconnect to HQ")
                    n = _update_one(
                        api, path, bar_count, target_as_of=target_as_of
                    )
                    if n:
                        updated += 1
                        appended += n
                    ok = True
                    break
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    _disconnect(api)
                    api = None
                    if attempt + 1 < attempts:
                        time.sleep(retry_sleep * (attempt + 1))
            if not ok:
                failed.append(path)
                logger.warning(
                    "pytdx update failed %s after %s attempts: %s",
                    path.name,
                    attempts,
                    last_exc,
                )
    finally:
        _disconnect(api)
    return updated, appended, failed


def refresh_vipdoc_via_pytdx(
    vipdoc: Path,
    *,
    workers: int = 4,
    bar_count: int = 40,
    hosts: Iterable[tuple[str, int]] | None = None,
    max_symbols: int | None = None,
    symbol_retries: int = _DEFAULT_SYMBOL_RETRIES,
    second_pass_retries: int = _DEFAULT_SECOND_PASS_RETRIES,
    target_as_of: date | None = None,
    eod_hour: int = 16,
    eod_minute: int = 0,
) -> PytdxUpdateResult:
    """
    Incrementally upsert settled daily bars into existing vipdoc .day files.
    Requires at least one local .day file (no full-market cold start).

    Failed symbols are retried in-chunk, then once more in a second pass.
    Bars after the settled session date are never written.
    """
    vipdoc = Path(vipdoc)
    files = list_day_files(vipdoc)
    if max_symbols is not None:
        files = files[: max(0, max_symbols)]
    if not files:
        return PytdxUpdateResult(
            ok=False,
            message="pytdx skip: no local .day files (need vipdoc history first)",
        )

    host_list = tuple(hosts) if hosts is not None else _DEFAULT_HOSTS
    probe = _connect(host_list)
    if probe is None:
        return PytdxUpdateResult(
            ok=False,
            message="pytdx failed: cannot connect to any HQ server",
            files_scanned=len(files),
        )
    _disconnect(probe)

    wall_target = target_as_of or settled_as_of(
        eod_hour=eod_hour, eod_minute=eod_minute
    )
    workers = max(1, int(workers))
    bar_count = max(1, min(int(bar_count), 800))
    chunks: list[list[Path]] = [[] for _ in range(workers)]
    for i, path in enumerate(files):
        chunks[i % workers].append(path)

    logger.info(
        "pytdx incremental start files=%s workers=%s bar_count=%s "
        "retries=%s settled_as_of=%s",
        len(files),
        workers,
        bar_count,
        symbol_retries,
        wall_target.isoformat(),
    )
    updated = 0
    appended = 0
    failed: list[Path] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(
                _update_chunk,
                chunk,
                host_list,
                bar_count,
                target_as_of=wall_target,
                retries=symbol_retries,
            )
            for chunk in chunks
            if chunk
        ]
        for fut in as_completed(futures):
            u, n, fails = fut.result()
            updated += u
            appended += n
            failed.extend(fails)

    if failed:
        logger.warning(
            "pytdx second pass for %s failed symbols (e.g. %s)",
            len(failed),
            ", ".join(p.name for p in failed[:8]),
        )
        u2, n2, still = _update_chunk(
            failed,
            host_list,
            bar_count,
            target_as_of=wall_target,
            retries=second_pass_retries,
            retry_sleep=0.4,
        )
        updated += u2
        appended += n2
        failed = still

    errors = len(failed)
    if updated == 0 and errors >= len(files):
        return PytdxUpdateResult(
            ok=False,
            message=f"pytdx failed: all {len(files)} symbols errored",
            files_scanned=len(files),
            files_updated=0,
            bars_appended=0,
            errors=errors,
        )

    status = "ok" if errors == 0 else "partial"
    msg = (
        f"pytdx incremental {status} scanned={len(files)} "
        f"updated={updated} bars={appended} errors={errors} "
        f"settled_as_of={wall_target.isoformat()}"
    )
    if failed:
        msg = f"{msg} failed=[{', '.join(p.stem for p in failed[:12])}"
        msg += ", ...]" if len(failed) > 12 else "]"
    logger.info(msg)
    return PytdxUpdateResult(
        ok=True,
        message=msg,
        files_scanned=len(files),
        files_updated=updated,
        bars_appended=appended,
        errors=errors,
    )


def refresh_codes_via_pytdx(
    vipdoc: Path,
    codes: Iterable[str],
    *,
    bar_count: int = 40,
    hosts: Iterable[tuple[str, int]] | None = None,
    symbol_retries: int = _DEFAULT_SECOND_PASS_RETRIES,
    min_as_of: date | None = None,
    target_as_of: date | None = None,
    eod_hour: int = 16,
    eod_minute: int = 0,
) -> PytdxUpdateResult:
    """
    Settled-session upsert/verify for a small watchlist of codes.
    Missing local .day files are skipped (counted as errors).

    When min_as_of is set, symbols still lagging after the first pass are
    retried (covers silent empty HQ replies that leave files stale).
    """
    vipdoc = Path(vipdoc)
    paths: list[Path] = []
    missing: list[str] = []
    seen: set[str] = set()
    for raw in codes:
        code = str(raw).strip().lower()
        if not code or code in seen:
            continue
        seen.add(code)
        path = day_path_for(vipdoc, code)
        if path is None:
            missing.append(code)
            continue
        paths.append(path)

    if not paths and missing:
        return PytdxUpdateResult(
            ok=False,
            message=f"pytdx watchlist: no local .day files ({', '.join(missing[:8])})",
            files_scanned=0,
            errors=len(missing),
        )
    if not paths:
        return PytdxUpdateResult(ok=True, message="pytdx watchlist: empty", files_scanned=0)

    host_list = tuple(hosts) if hosts is not None else _DEFAULT_HOSTS
    bar_count = max(1, min(int(bar_count), 800))
    wall_target = target_as_of or settled_as_of(
        eod_hour=eod_hour, eod_minute=eod_minute
    )
    # Prefer explicit min_as_of (caller) but never ask for an unformed session.
    lag_floor = min(min_as_of, wall_target) if min_as_of is not None else wall_target

    updated, appended, failed = _update_chunk(
        paths,
        host_list,
        bar_count,
        target_as_of=wall_target,
        retries=symbol_retries,
        retry_sleep=0.3,
    )

    lagging: list[Path] = []
    if lag_floor is not None:
        ok_paths = [p for p in paths if p not in set(failed)]
        lagging = _paths_lagging(ok_paths, lag_floor)
        if lagging:
            logger.warning(
                "pytdx watchlist lagging vs %s: %s",
                lag_floor.isoformat(),
                ", ".join(p.stem for p in lagging[:8]),
            )
            u2, n2, still = _update_chunk(
                lagging,
                host_list,
                bar_count,
                target_as_of=wall_target,
                retries=symbol_retries,
                retry_sleep=0.4,
            )
            updated += u2
            appended += n2
            failed.extend(still)
            still_lag = _paths_lagging(
                [p for p in lagging if p not in set(still)],
                lag_floor,
            )
            for path in still_lag:
                if path not in failed:
                    failed.append(path)
                    logger.warning(
                        "pytdx watchlist still lagging %s last=%s want=%s",
                        path.stem,
                        last_trade_date(path),
                        lag_floor,
                    )

    errors = len(failed) + len(missing)
    status = "ok" if errors == 0 else "partial"
    parts = [
        f"pytdx watchlist {status}",
        f"codes={len(paths)}",
        f"updated={updated}",
        f"bars={appended}",
        f"errors={errors}",
        f"settled_as_of={wall_target.isoformat()}",
    ]
    if failed:
        parts.append(f"failed=[{', '.join(p.stem for p in failed[:8])}]")
    if missing:
        parts.append(f"missing=[{', '.join(missing[:8])}]")
    msg = " ".join(parts)
    logger.info(msg)
    return PytdxUpdateResult(
        ok=errors == 0 or updated > 0 or appended > 0,
        message=msg,
        files_scanned=len(paths),
        files_updated=updated,
        bars_appended=appended,
        errors=errors,
    )
