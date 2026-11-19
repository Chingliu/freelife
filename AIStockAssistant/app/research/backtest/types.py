from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True)
class Trade:
    entry_date: date
    exit_date: date | None
    entry_price: float
    exit_price: float | None
    return_pct: float | None
    bars_held: int


@dataclass(frozen=True)
class PerformanceMetrics:
    total_return: float
    annual_return: float
    max_drawdown: float
    sharpe: float
    calmar: float
    win_rate: float
    trades: int
    avg_holding_bars: float
    time_in_market: float  # fraction of bars with position > 0
    volatility: float
    final_equity: float

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict

        return asdict(self)


@dataclass
class BacktestResult:
    strategy_id: str
    code: str
    metrics: PerformanceMetrics
    params: dict[str, Any] = field(default_factory=dict)
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[tuple[date, float]] = field(default_factory=list)
    positions: list[float] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    # Last bar target weight from strategy.generate (signal as of as_of close).
    current_weight: float = 0.0

    @property
    def current_signal(self) -> str:
        """Long-only: 做多 if target weight > 0, else 看跌 (flat / no long)."""
        return "做多" if self.current_weight > 1e-12 else "看跌"

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "code": self.code,
            "params": self.params,
            "metrics": self.metrics.to_dict(),
            "current_signal": self.current_signal,
            "current_weight": self.current_weight,
            "trades": [
                {
                    "entry_date": t.entry_date.isoformat(),
                    "exit_date": t.exit_date.isoformat() if t.exit_date else None,
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "return_pct": t.return_pct,
                    "bars_held": t.bars_held,
                }
                for t in self.trades
            ],
            "equity_curve_tail": [
                {"date": d.isoformat(), "equity": e}
                for d, e in self.equity_curve[-10:]
            ],
            "notes": self.notes,
        }
