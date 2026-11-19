"""Evidence grades A/B/C/D for research conclusions."""

from __future__ import annotations

from typing import Any


def grade_strategy_row(row: dict[str, Any]) -> str:
    """
    A: OOS test pass + cross-ETF pass
    B: multi-horizon stable on this ETF (3y ok & calmar>0, not demoted)
    C: full-sample backtest only
    D: insufficient / demoted / no usable metrics
    """
    oos = row.get("oos") or {}
    test = oos.get("test") or {}
    oos_ok = test.get("status") == "ok" and (test.get("calmar") is not None) and float(
        test.get("calmar") or 0
    ) > 0

    cross = row.get("cross_etf") or {}
    cross_pass = bool(cross.get("pass"))

    m3 = row.get("metrics_3y") or {}
    m5 = row.get("metrics_5y") or {}
    lifecycle = str(row.get("lifecycle") or "active")
    multi_stable = (
        lifecycle != "demoted"
        and m3.get("status") == "ok"
        and (m3.get("calmar") is not None and float(m3["calmar"]) > 0)
        and (
            m5.get("status") == "insufficient"
            or (
                m5.get("status") == "ok"
                and m5.get("calmar") is not None
                and float(m5["calmar"]) > 0
            )
        )
    )

    if oos_ok and cross_pass:
        return "A"
    if multi_stable and (oos_ok or m3.get("status") == "ok"):
        return "B"
    if row.get("calmar") is not None and lifecycle != "demoted":
        return "C"
    return "D"


def grade_decision(
    comparison: list[dict[str, Any]],
    *,
    preferred_ids: list[str] | None = None,
) -> str:
    """Conservative: min grade among preferred (or Top3 active) rows."""
    by_id = {str(r["strategy_id"]): r for r in comparison}
    ids = list(preferred_ids or [])
    rows = [by_id[i] for i in ids if i in by_id]
    if not rows:
        rows = [
            r
            for r in comparison
            if str(r.get("lifecycle") or "active") != "demoted"
        ][:3]
    if not rows:
        return "D"
    order = {"A": 0, "B": 1, "C": 2, "D": 3}
    grades = [str(r.get("evidence_grade") or grade_strategy_row(r)) for r in rows]
    return max(grades, key=lambda g: order.get(g, 3))


def cross_etf_pass_from_score(score: dict[str, Any] | None) -> bool:
    if not score:
        return False
    return bool(score.get("pass"))
