"""Stock research report builders (L5+L6 packaging)."""

from __future__ import annotations

from typing import Any

from app.data.models import Bar
from app.data.provider import IDataProvider
from app.indicators.ma import sma
from app.selection.evidence import build_evidence_rows, grade_stock_conclusion
from app.selection.explain import build_reasons
from app.selection.types import FactorHealth, RankedStock, StockScore
from app.selection.validation import event_stats_for_factor


def build_stock_report(
    score: StockScore,
    provider: IDataProvider,
    *,
    health: dict[str, FactorHealth] | None = None,
    rank: int | None = None,
    provider_id: str = "",
    as_of: str | None = None,
) -> dict[str, Any]:
    reasons = build_reasons(score)
    event_stats = None
    if health:
        event_stats = {
            fid: event_stats_for_factor(h)
            for fid, h in health.items()
            if fid in score.factors
        }
    evidence = build_evidence_rows(score, reasons, health=health, event_stats=event_stats)
    grade = grade_stock_conclusion(score, health)

    bars = provider.get_daily_bars(score.code)
    levels = _price_levels(bars)
    gaps = [
        f"{fv.factor_id}（{fv.name_zh}）: {fv.detail or fv.status}"
        for fv in score.factors.values()
        if fv.status == "unavailable"
    ]

    entry, stop, invalidate, observe = _plan_levels(levels, score)

    return {
        "code": score.code,
        "name": score.name,
        "rank": rank,
        "composite": score.composite,
        "category_scores": score.category_scores,
        "sector": score.sector,
        "indices": score.indices,
        "factors": {k: v.to_dict() for k, v in score.factors.items()},
        "reasons": [r.to_dict() for r in reasons],
        "evidence": [e.to_dict() for e in evidence],
        "evidence_grade": grade,
        "data_gaps": gaps,
        "risks": _risks(score, levels, grade),
        "entry_zone": entry,
        "stop_loss": stop,
        "invalidate": invalidate,
        "observe": observe,
        "price_levels": levels,
        "disclaimer": "研究观察，非正式投资建议；C/D 证据等级仅作实验性观察。",
        "provider_id": provider_id,
        "as_of": as_of,
    }


def build_daily_selection_report(
    ranked: list[RankedStock],
    *,
    filter_audit: dict[str, Any],
    universe: dict[str, Any],
    health: dict[str, FactorHealth] | None,
    provider_id: str,
    as_of: str | None,
    stock_reports: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "as_of": as_of,
        "provider_id": provider_id,
        "universe": universe,
        "filter_audit": filter_audit,
        "top10": [r.to_dict() for r in ranked],
        "factor_health": {k: v.to_dict() for k, v in (health or {}).items()},
        "stock_reports": stock_reports or [],
        "disclaimer": "研究观察，非正式投资建议。",
    }


def _price_levels(bars: list[Bar]) -> dict[str, Any]:
    if not bars:
        return {}
    closes = [b.close for b in bars]
    ma20 = sma(closes, 20)[-1]
    ma60 = sma(closes, 60)[-1]
    last = bars[-1]
    window = bars[-60:] if len(bars) >= 60 else bars
    return {
        "last_close": last.close,
        "last_date": last.trade_date.isoformat(),
        "ma20": ma20,
        "ma60": ma60,
        "high_60": max(b.high for b in window),
        "low_60": min(b.low for b in window),
    }


def _plan_levels(
    levels: dict[str, Any],
    score: StockScore,
) -> tuple[str, str, str, list[str]]:
    if not levels:
        return (
            "无法评估：无行情",
            "价格止损待补",
            "数据不足则计划不适用",
            ["等待日线就绪后重评"],
        )
    px = levels.get("last_close")
    ma20 = levels.get("ma20")
    ma60 = levels.get("ma60")
    low60 = levels.get("low_60")
    entry = (
        f"观察区：回踩 MA20({ma20:.2f}) 附近且综合分仍居前"
        if ma20
        else f"观察区：现价附近 {px}"
    )
    stop = (
        f"条件止损：收盘跌破 MA60({ma60:.2f}) 或跌破近60日低点({low60:.2f})"
        if ma60 and low60
        else "条件止损：门禁翻空或综合分跌出观察池"
    )
    invalidate = "失效：趋势因子看跌且相对强弱转负，或关键因子被 L7 demote"
    observe = [
        "综合分与行业约束是否仍支持留在 Top10",
        "vol_target/波动分项是否恶化",
        "L7 RankIC 是否仍为正",
        f"现价相对 MA20/MA60 位置（现价={px}）",
    ]
    return entry, stop, invalidate, observe


def _risks(score: StockScore, levels: dict[str, Any], grade: str) -> list[str]:
    risks = [
        f"证据等级 {grade}：不得解读为投资建议",
        "横截面因子存在拥挤与失效风险",
    ]
    vol = score.factors.get("vol_20")
    if vol and vol.score is not None and vol.score < 30:
        risks.append("波动率偏高（低分=高波动）")
    if score.sector == "unknown":
        risks.append("行业未知，行业分散约束弱化")
    if levels.get("last_close") and levels.get("high_60"):
        if float(levels["last_close"]) >= 0.98 * float(levels["high_60"]):
            risks.append("接近近60日高点，追高风险上升")
    return risks
