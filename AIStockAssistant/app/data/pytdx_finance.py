"""Fetch fundamentals via pytdx get_finance_info and merge into finance_cache.json."""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

from pytdx.hq import TdxHq_API

from app.data.pytdx_updater import _DEFAULT_HOSTS, _MARKET_MAP, _connect, _disconnect

logger = logging.getLogger(__name__)

_BPS_CROSSCHECK_TOL = 0.05
_PRESERVE_KEYS = ("profit_cagr",)


@dataclass(frozen=True)
class FinanceSyncResult:
    ok: bool
    message: str
    codes_requested: int = 0
    codes_ok: int = 0
    codes_failed: int = 0
    path: str = ""


def parse_code(code: str) -> tuple[int, str] | None:
    stem = code.strip().lower()
    if len(stem) < 8:
        return None
    market = stem[:2]
    symbol = stem[2:]
    if market not in _MARKET_MAP or not symbol.isdigit():
        return None
    return _MARKET_MAP[market], symbol


def map_finance_info(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    """Map pytdx get_finance_info row → cache fields (eps/bps/roe). Values already scaled by pytdx."""
    if not raw or not isinstance(raw, dict):
        return None

    jinglirun = _f(raw.get("jinglirun"))
    jingzichan = _f(raw.get("jingzichan"))
    zongguben = _f(raw.get("zongguben"))
    meigu = _f(raw.get("meigujingzichan"))
    updated = raw.get("updated_date")

    out: dict[str, Any] = {"source": "pytdx.get_finance_info"}
    if updated is not None:
        try:
            out["updated_date"] = int(updated)
        except (TypeError, ValueError):
            out["updated_date"] = updated

    eps: float | None = None
    if jinglirun is not None and zongguben is not None and zongguben > 0 and jinglirun > 0:
        eps = jinglirun / zongguben
        out["eps"] = eps

    bps: float | None = None
    if meigu is not None and meigu > 0:
        bps = meigu
        out["bps"] = bps
    elif jingzichan is not None and zongguben is not None and zongguben > 0 and jingzichan > 0:
        bps = jingzichan / zongguben
        out["bps"] = bps

    if (
        bps is not None
        and jingzichan is not None
        and zongguben is not None
        and zongguben > 0
        and jingzichan > 0
    ):
        cross = jingzichan / zongguben
        if bps > 0:
            rel = abs(bps - cross) / bps
            out["bps_crosscheck_ok"] = rel <= _BPS_CROSSCHECK_TOL
            out["bps_from_nav"] = cross
        else:
            out["bps_crosscheck_ok"] = False

    if jinglirun is not None and jingzichan is not None and jingzichan > 0 and jinglirun > 0:
        out["roe"] = jinglirun / jingzichan

    # Keep light audit trail (already-scaled yuan / shares).
    if jinglirun is not None:
        out["jinglirun"] = jinglirun
    if jingzichan is not None:
        out["jingzichan"] = jingzichan
    if zongguben is not None:
        out["zongguben"] = zongguben

    if not any(k in out for k in ("eps", "bps", "roe")):
        return None
    return out


def fetch_finance_info(
    code: str,
    *,
    api: TdxHq_API | None = None,
    hosts: Iterable[tuple[str, int]] | None = None,
    timeout: float = 3.0,
) -> dict[str, Any] | None:
    """Fetch one code; returns mapped cache dict or None."""
    parsed = parse_code(code)
    if parsed is None:
        return None
    market, symbol = parsed
    own = api is None
    client = api or _connect(hosts or _DEFAULT_HOSTS, timeout=timeout)
    if client is None:
        return None
    try:
        raw = client.get_finance_info(market, symbol)
        mapped = map_finance_info(dict(raw) if raw else None)
        return mapped
    except Exception as exc:  # noqa: BLE001
        logger.debug("get_finance_info failed %s: %s", code, exc)
        return None
    finally:
        if own:
            _disconnect(client)


def merge_finance_item(
    existing: dict[str, Any] | None,
    mapped: dict[str, Any],
) -> dict[str, Any]:
    """Merge new mapped fields into existing row; preserve profit_cagr and unknown keys."""
    base = dict(existing) if isinstance(existing, dict) else {}
    preserved = {k: base[k] for k in _PRESERVE_KEYS if k in base}
    # Drop stale pe/pb when eps/bps arrive (analysis will recompute).
    if "eps" in mapped or "bps" in mapped:
        base.pop("pe", None)
        base.pop("pb", None)
    base.update(mapped)
    base.update(preserved)
    return base


def load_finance_cache_blob(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"items": {}}
    with path.open(encoding="utf-8") as fh:
        raw = json.load(fh)
    if not isinstance(raw, dict):
        return {"items": {}}
    items = raw.get("items")
    if not isinstance(items, dict):
        raw["items"] = {}
    return raw


def write_finance_cache_blob(path: Path, blob: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(blob, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    tmp.replace(path)


def upsert_finance_cache_item(path: Path, code: str, mapped: dict[str, Any]) -> dict[str, Any]:
    """Merge one code into finance_cache.json and return the merged item."""
    blob = load_finance_cache_blob(path)
    items = blob.setdefault("items", {})
    assert isinstance(items, dict)
    c = code.lower()
    prev = items.get(c) if isinstance(items.get(c), dict) else None
    merged = merge_finance_item(prev, mapped)
    items[c] = merged
    blob["synced_at"] = datetime.now().isoformat(timespec="seconds")
    write_finance_cache_blob(path, blob)
    return merged


def refresh_finance_cache(
    codes: list[str],
    path: Path,
    *,
    workers: int = 4,
    hosts: Iterable[tuple[str, int]] | None = None,
    as_of: date | None = None,
) -> FinanceSyncResult:
    """Batch fetch get_finance_info for codes and merge into finance_cache.json."""
    uniq = sorted({c.strip().lower() for c in codes if c and parse_code(c)})
    if not uniq:
        return FinanceSyncResult(ok=False, message="no valid codes", path=str(path))

    host_list = tuple(hosts or _DEFAULT_HOSTS)
    workers = max(1, min(int(workers), 16))
    ok_map: dict[str, dict[str, Any]] = {}
    failed = 0

    def _one(code: str) -> tuple[str, dict[str, Any] | None]:
        # Short sleep to reduce hammering public HQ nodes.
        time.sleep(0.02)
        return code, fetch_finance_info(code, hosts=host_list)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_one, c) for c in uniq]
        for fut in as_completed(futs):
            try:
                code, mapped = fut.result()
            except Exception:  # noqa: BLE001
                failed += 1
                continue
            if mapped is None:
                failed += 1
            else:
                ok_map[code] = mapped

    blob = load_finance_cache_blob(path)
    items = blob.setdefault("items", {})
    assert isinstance(items, dict)
    for code, mapped in ok_map.items():
        prev = items.get(code) if isinstance(items.get(code), dict) else None
        items[code] = merge_finance_item(prev, mapped)

    blob["synced_at"] = datetime.now().isoformat(timespec="seconds")
    if as_of is not None:
        blob["as_of"] = as_of.isoformat()
    write_finance_cache_blob(path, blob)

    n_ok = len(ok_map)
    msg = f"finance sync ok={n_ok} failed={failed} path={path}"
    logger.info(msg)
    return FinanceSyncResult(
        ok=n_ok > 0,
        message=msg,
        codes_requested=len(uniq),
        codes_ok=n_ok,
        codes_failed=failed,
        path=str(path),
    )


def _f(v: object) -> float | None:
    if v is None:
        return None
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
