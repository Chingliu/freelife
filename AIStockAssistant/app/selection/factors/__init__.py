"""Factor registry and scoring helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.data.models import Bar
from app.selection.meta import MetaStore
from app.selection.types import FactorHealth, FactorValue, Lifecycle


@dataclass(frozen=True)
class FactorSpec:
    factor_id: str
    category: str
    name_zh: str
    higher_is_better: bool
    phase: int
    compute: Callable[..., float | None]


def percentile_scores(
    raws: dict[str, float | None],
    *,
    higher_is_better: bool = True,
) -> dict[str, float | None]:
    """Cross-sectional percentile in [0, 100]. Ties get mid-rank."""
    items = [(c, v) for c, v in raws.items() if v is not None]
    if not items:
        return {c: None for c in raws}
    # Sort ascending by value
    items.sort(key=lambda x: float(x[1]))
    n = len(items)
    ranks: dict[str, float] = {}
    i = 0
    while i < n:
        j = i
        while j + 1 < n and items[j + 1][1] == items[i][1]:
            j += 1
        # average rank of ties (1-based)
        avg_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[items[k][0]] = avg_rank
        i = j + 1
    out: dict[str, float | None] = {}
    for code in raws:
        if code not in ranks:
            out[code] = None
            continue
        pct = (ranks[code] - 1.0) / max(n - 1, 1) * 100.0
        out[code] = pct if higher_is_better else (100.0 - pct)
    return out


def active_factor_ids(health: dict[str, FactorHealth] | None) -> set[str] | None:
    """None means 'all non-demoted by default (no L7 yet)'."""
    if not health:
        return None
    return {fid for fid, h in health.items() if h.lifecycle == "active"}


def lifecycle_of(health: dict[str, FactorHealth] | None, factor_id: str) -> Lifecycle:
    if not health or factor_id not in health:
        return "active"
    return health[factor_id].lifecycle
