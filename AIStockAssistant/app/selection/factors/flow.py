"""Phase-4 capital flow / sector / macro factors."""

from __future__ import annotations

from typing import Any


def flow_net_inflow_5d(item: dict[str, Any] | None) -> float | None:
    if not item:
        return None
    v = item.get("net_inflow_5d")
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def flow_northbound_days(item: dict[str, Any] | None) -> float | None:
    if not item:
        return None
    v = item.get("northbound_days")
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def sector_momentum_proxy(
    code: str,
    sector: str,
    sector_avg_mom: dict[str, float],
) -> float | None:
    """Industry relative: sector average 20d momentum (precomputed)."""
    if sector == "unknown":
        return None
    return sector_avg_mom.get(sector)


def macro_scale(macro: dict[str, Any] | None) -> float:
    if not macro:
        return 1.0
    try:
        return float(macro.get("scale", 1.0))
    except (TypeError, ValueError):
        return 1.0
