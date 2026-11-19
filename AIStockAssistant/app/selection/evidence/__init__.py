"""L6 evidence chain + grade."""

from __future__ import annotations

from typing import Any

from app.selection.types import (
    EvidenceGrade,
    EvidenceRow,
    FactorHealth,
    ReasonItem,
    StockScore,
)


def build_evidence_rows(
    score: StockScore,
    reasons: list[ReasonItem],
    health: dict[str, FactorHealth] | None = None,
    event_stats: dict[str, dict[str, Any]] | None = None,
) -> list[EvidenceRow]:
    rows: list[EvidenceRow] = []
    for r in reasons:
        fid = r.factor_id
        fv = score.factors.get(fid) if fid else None
        source = "本地通达信日线横截面计算"
        verify = "selection.factors + percentile_scores"
        if fv and fv.category in {"价值", "质量"}:
            source = "finance_cache(eps/bps)+local close"
            if fv.factor_id == "quality_roe":
                source = "finance_cache(roe) / pytdx.get_finance_info"
            if fv.factor_id == "quality_cagr":
                source = "finance_cache(profit_cagr seed)"
            verify = "fundamental factor raw + cross-section percentile"
        if fv and fid.startswith("flow_"):
            source = "capital_flow.json"
            verify = "flow factor raw + cross-section percentile"
        if fv and fid == "sector_mom":
            source = "sectors.json + 20日动量聚合"
            verify = "sector average momentum percentile"

        stats = None
        if event_stats and fid in event_stats:
            stats = event_stats[fid]
        elif health and fid in health:
            h = health[fid]
            stats = {
                "ic_1y": h.ic_1y,
                "rank_ic_1y": h.rank_ic_1y,
                "lifecycle": h.lifecycle,
                "oos_pass": h.oos_pass,
                "evidence_grade": h.evidence_grade,
            }

        rows.append(
            EvidenceRow(
                claim=r.claim or r.text,
                source=source,
                verify_method=verify,
                stats=stats,
                factor_id=fid,
            )
        )
    return rows


def grade_stock_conclusion(
    score: StockScore,
    health: dict[str, FactorHealth] | None,
) -> EvidenceGrade:
    ok_factors = [f for f in score.factors.values() if f.status == "ok" and f.score is not None]
    if not ok_factors:
        return "D"
    if not health:
        return "C"
    used = []
    for f in ok_factors:
        h = health.get(f.factor_id)
        if h is None:
            continue
        used.append(h)
    if not used:
        return "C"
    if any(h.lifecycle == "demoted" for h in used):
        return "D"
    oos_ok = sum(1 for h in used if h.oos_pass) / len(used)
    ic_ok = sum(1 for h in used if (h.rank_ic_1y or 0) > 0) / len(used)
    if oos_ok >= 0.6 and ic_ok >= 0.6 and all(h.evidence_grade in {"A", "B"} for h in used):
        return "A"
    if ic_ok >= 0.5 and any(h.lifecycle == "active" for h in used):
        return "B"
    return "C"
