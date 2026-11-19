"""Shared types for the seven-layer selection engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

FactorStatus = Literal["ok", "unavailable", "demoted", "watch"]
Lifecycle = Literal["active", "watch", "demoted"]
EvidenceGrade = Literal["A", "B", "C", "D"]


@dataclass
class UniverseSnapshot:
    as_of: date | None
    source: str
    stale: bool
    by_index: dict[str, list[str]]
    codes: list[str]
    gaps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_of": self.as_of.isoformat() if self.as_of else None,
            "source": self.source,
            "stale": self.stale,
            "by_index": {k: list(v) for k, v in self.by_index.items()},
            "codes": list(self.codes),
            "count": len(self.codes),
            "gaps": list(self.gaps),
        }


@dataclass
class FilterReject:
    code: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "reason": self.reason}


@dataclass
class FilterResult:
    kept: list[str]
    rejected: list[FilterReject]
    reason_counts: dict[str, int]
    gaps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kept": list(self.kept),
            "kept_count": len(self.kept),
            "rejected": [r.to_dict() for r in self.rejected],
            "rejected_count": len(self.rejected),
            "reason_counts": dict(self.reason_counts),
            "gaps": list(self.gaps),
        }


@dataclass
class FactorValue:
    factor_id: str
    category: str
    name_zh: str
    raw: float | None
    score: float | None  # 0-100 cross-section percentile
    status: FactorStatus
    detail: str = ""
    higher_is_better: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "factor_id": self.factor_id,
            "category": self.category,
            "name_zh": self.name_zh,
            "raw": self.raw,
            "score": self.score,
            "status": self.status,
            "detail": self.detail,
            "higher_is_better": self.higher_is_better,
        }


@dataclass
class StockScore:
    code: str
    name: str
    composite: float | None
    factors: dict[str, FactorValue]
    category_scores: dict[str, float | None]
    sector: str = "unknown"
    indices: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "composite": self.composite,
            "category_scores": dict(self.category_scores),
            "sector": self.sector,
            "indices": list(self.indices),
            "factors": {k: v.to_dict() for k, v in self.factors.items()},
        }


@dataclass
class RankedStock:
    rank: int
    score: StockScore

    def to_dict(self) -> dict[str, Any]:
        d = self.score.to_dict()
        d["rank"] = self.rank
        return d


@dataclass
class ReasonItem:
    index: int
    text: str
    factor_id: str
    claim: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "text": self.text,
            "factor_id": self.factor_id,
            "claim": self.claim,
        }


@dataclass
class EvidenceRow:
    claim: str
    source: str
    verify_method: str
    stats: dict[str, Any] | None = None
    factor_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim": self.claim,
            "source": self.source,
            "verify_method": self.verify_method,
            "stats": self.stats,
            "factor_id": self.factor_id,
        }


@dataclass
class FactorHealth:
    factor_id: str
    lifecycle: Lifecycle
    ic_1y: float | None = None
    rank_ic_1y: float | None = None
    icir_1y: float | None = None
    ic_3y: float | None = None
    rank_ic_3y: float | None = None
    long_short_ann: float | None = None
    long_short_mdd: float | None = None
    long_short_sharpe: float | None = None
    regime: dict[str, Any] = field(default_factory=dict)
    oos_pass: bool | None = None
    evidence_grade: EvidenceGrade = "C"
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "factor_id": self.factor_id,
            "lifecycle": self.lifecycle,
            "ic_1y": self.ic_1y,
            "rank_ic_1y": self.rank_ic_1y,
            "icir_1y": self.icir_1y,
            "ic_3y": self.ic_3y,
            "rank_ic_3y": self.rank_ic_3y,
            "long_short_ann": self.long_short_ann,
            "long_short_mdd": self.long_short_mdd,
            "long_short_sharpe": self.long_short_sharpe,
            "regime": dict(self.regime),
            "oos_pass": self.oos_pass,
            "evidence_grade": self.evidence_grade,
            "note": self.note,
        }
