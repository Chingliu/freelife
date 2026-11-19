"""Phase-3 value / quality factors from finance meta or provider."""

from __future__ import annotations

from app.data.models import FinanceInfo


def value_ep(fin: FinanceInfo | None) -> float | None:
    """Earnings yield = 1/PE when PE>0."""
    if fin is None or fin.pe is None or fin.pe <= 0:
        return None
    return 1.0 / float(fin.pe)


def value_bp(fin: FinanceInfo | None) -> float | None:
    if fin is None or fin.pb is None or fin.pb <= 0:
        return None
    return 1.0 / float(fin.pb)


def quality_roe(fin: FinanceInfo | None) -> float | None:
    if fin is None or fin.roe is None:
        return None
    return float(fin.roe)


def quality_profit_cagr(fin: FinanceInfo | None) -> float | None:
    if fin is None:
        return None
    v = fin.extras.get("profit_cagr")
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
