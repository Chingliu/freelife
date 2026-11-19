"""Enhance finance lookup: cache file + local close → PE/PB."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from app.data.models import Bar, FinanceInfo
from app.data.provider import IDataProvider


def load_finance_cache(path: Path) -> dict[str, FinanceInfo]:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as fh:
        raw = json.load(fh)
    items = raw.get("items") if isinstance(raw, dict) else {}
    out: dict[str, FinanceInfo] = {}
    if not isinstance(items, dict):
        return out
    for code, row in items.items():
        if not isinstance(row, dict):
            continue
        out[str(code).lower()] = row_to_finance_info(str(code).lower(), row)
    return out


def row_to_finance_info(code: str, row: dict[str, Any]) -> FinanceInfo:
    """Build FinanceInfo from cache row without price (legacy pe/pb or bare fundamentals)."""
    return FinanceInfo(
        code=code.lower(),
        pe=_f(row.get("pe")),
        pb=_f(row.get("pb")),
        roe=_f(row.get("roe")),
        extras={k: v for k, v in row.items() if k not in {"pe", "pb", "roe"}},
    )


def cache_row_has_fundamentals(row: dict[str, Any] | None) -> bool:
    if not isinstance(row, dict):
        return False
    return any(_f(row.get(k)) is not None for k in ("eps", "bps", "roe", "pe", "pb"))


def finance_info_usable(fin: FinanceInfo | None) -> bool:
    if fin is None:
        return False
    if fin.pe is not None or fin.pb is not None or fin.roe is not None:
        return True
    extras = fin.extras or {}
    return any(_f(extras.get(k)) is not None for k in ("eps", "bps"))


def finance_with_price(
    code: str,
    *,
    cache_row: dict[str, Any] | None = None,
    fin: FinanceInfo | None = None,
    last_close: float | None = None,
    price_as_of: date | str | None = None,
) -> FinanceInfo | None:
    """
    Prefer eps/bps + local close to compute pe/pb; else legacy pe/pb from cache.
    ROE / profit_cagr come from cache extras.
    """
    c = code.lower()
    if fin is None and cache_row is not None:
        fin = row_to_finance_info(c, cache_row)
    if fin is None:
        return None

    extras = dict(fin.extras or {})
    if cache_row:
        for k, v in cache_row.items():
            if k not in {"pe", "pb", "roe"}:
                extras.setdefault(k, v)

    eps = _f(extras.get("eps"))
    bps = _f(extras.get("bps"))
    roe = fin.roe if fin.roe is not None else _f(extras.get("roe"))

    pe = fin.pe
    pb = fin.pb
    pe_source = extras.get("pe_source")

    if last_close is not None and last_close > 0:
        if eps is not None and eps > 0:
            pe = last_close / eps
            pe_source = "local_close/eps"
            extras["eps"] = eps
        if bps is not None and bps > 0:
            pb = last_close / bps
            extras["pb_source"] = "local_close/bps"
            extras["bps"] = bps
        extras["last_close"] = last_close
        if price_as_of is not None:
            extras["price_as_of"] = (
                price_as_of.isoformat()
                if hasattr(price_as_of, "isoformat")
                else str(price_as_of)
            )

    if pe_source:
        extras["pe_source"] = pe_source
    if eps is not None:
        extras["eps"] = eps
    if bps is not None:
        extras["bps"] = bps

    return FinanceInfo(code=c, pe=pe, pb=pb, roe=roe, extras=extras)


def last_close_from_bars(bars: list[Bar] | None) -> tuple[float | None, date | None]:
    if not bars:
        return None, None
    b = bars[-1]
    return float(b.close), b.trade_date


def resolve_finance(
    code: str,
    *,
    provider: IDataProvider,
    cache: dict[str, FinanceInfo] | None = None,
    cache_rows: dict[str, dict[str, Any]] | None = None,
    vipdoc: Path | None = None,
    last_close: float | None = None,
    price_as_of: date | str | None = None,
) -> FinanceInfo | None:
    """Prefer cache (+ optional live PE/PB from close); else provider; annotate cw."""
    c = code.lower()
    row = (cache_rows or {}).get(c)
    base = (cache or {}).get(c) if cache else None
    if base is not None or row is not None:
        return finance_with_price(
            c,
            cache_row=row,
            fin=base,
            last_close=last_close,
            price_as_of=price_as_of,
        )

    fin = provider.get_finance(c)
    if fin is not None and (fin.pe is not None or fin.pb is not None or fin.roe is not None):
        return finance_with_price(
            c, fin=fin, last_close=last_close, price_as_of=price_as_of
        )
    extras = dict(fin.extras) if fin else {}
    if vipdoc is not None:
        cw = Path(vipdoc) / "cw"
        extras["cw_present"] = cw.is_dir() and any(cw.iterdir())
        if not extras.get("cw_present"):
            extras["note"] = "cw empty or unparsed — use finance_cache.json for value/quality"
        else:
            extras.setdefault(
                "note",
                "cw present but binary parser not implemented; use finance_cache.json",
            )
    return FinanceInfo(code=c, pe=None, pb=None, roe=None, extras=extras)


def _f(v: object) -> float | None:
    if v is None:
        return None
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
