from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True)
class StockInfo:
    code: str
    name: str = ""
    market: str = ""  # sh / sz / bj


@dataclass(frozen=True)
class Bar:
    code: str
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float = 0.0


@dataclass(frozen=True)
class MinuteBar:
    """Tongdaxin minute bar (.lc1 / .lc5)."""

    code: str
    trade_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float = 0.0

    @property
    def trade_date(self) -> date:
        return self.trade_time.date()


@dataclass(frozen=True)
class FinanceInfo:
    code: str
    pe: float | None = None
    pb: float | None = None
    roe: float | None = None
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SectorInfo:
    name: str
    codes: tuple[str, ...] = ()


@dataclass
class SyncResult:
    ok: bool
    message: str
    as_of: date | None = None
    source: str = ""
