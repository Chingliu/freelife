"""L4 Top-N ranking with sector exposure cap."""

from __future__ import annotations

from app.selection.types import RankedStock, StockScore


def rank_top_n(
    scores: list[StockScore],
    *,
    top_n: int = 10,
    max_per_sector: int = 3,
) -> list[RankedStock]:
    ordered = sorted(
        scores,
        key=lambda s: (
            s.composite is not None,
            s.composite if s.composite is not None else -1.0,
            # tie-break: liquidity factor score then lower vol preference via mdd
            (s.factors.get("liq_amt_20").score or -1.0)
            if "liq_amt_20" in s.factors
            else -1.0,
            (s.factors.get("mdd_60").score or -1.0) if "mdd_60" in s.factors else -1.0,
        ),
        reverse=True,
    )
    picked: list[RankedStock] = []
    sector_counts: dict[str, int] = {}
    for s in ordered:
        if s.composite is None:
            continue
        sec = s.sector or "unknown"
        if sector_counts.get(sec, 0) >= max_per_sector:
            continue
        sector_counts[sec] = sector_counts.get(sec, 0) + 1
        picked.append(RankedStock(rank=len(picked) + 1, score=s))
        if len(picked) >= top_n:
            break
    return picked
