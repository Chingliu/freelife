"""L5 structured reasons (no free-form buy recommendations)."""

from __future__ import annotations

from app.selection.types import ReasonItem, StockScore


def build_reasons(score: StockScore, *, max_items: int = 5) -> list[ReasonItem]:
    candidates: list[tuple[float, ReasonItem]] = []
    idx = 0

    def add(factor_id: str, text: str, claim: str, weight: float) -> None:
        nonlocal idx
        idx += 1
        candidates.append(
            (
                weight,
                ReasonItem(index=idx, text=text, factor_id=factor_id, claim=claim),
            )
        )

    for fid, fv in score.factors.items():
        if fv.status != "ok" or fv.score is None:
            continue
        if fv.score < 60:
            continue
        raw_s = f"{fv.raw:.4g}" if fv.raw is not None else "n/a"
        text = f"{fv.name_zh}横截面分 {fv.score:.1f}/100（原始值 {raw_s}）"
        if fv.detail:
            text += f"；{fv.detail}"
        claim = f"{fid} score={fv.score:.1f}"
        add(fid, text, claim, fv.score)

    candidates.sort(key=lambda x: x[0], reverse=True)
    out: list[ReasonItem] = []
    for i, (_, item) in enumerate(candidates[:max_items], start=1):
        out.append(
            ReasonItem(
                index=i,
                text=item.text,
                factor_id=item.factor_id,
                claim=item.claim,
            )
        )
    if not out:
        out.append(
            ReasonItem(
                index=1,
                text="当期无显著高分因子（多数分项<60或数据不足）",
                factor_id="",
                claim="no_strong_factor",
            )
        )
    return out
