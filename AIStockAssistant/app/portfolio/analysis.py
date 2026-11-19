from __future__ import annotations

from dataclasses import dataclass

from app.config.settings import TargetSettings
from app.data.provider import IDataProvider


@dataclass(frozen=True)
class Position:
    code: str
    shares: float
    cost: float


@dataclass(frozen=True)
class PortfolioReport:
    market_value: float
    cost_value: float
    pnl_pct: float
    annual_proxy: float
    vs_target: str
    lines: tuple[str, ...]


class PortfolioAnalyzer:
    def __init__(
        self,
        provider: IDataProvider,
        targets: TargetSettings,
    ) -> None:
        self.provider = provider
        self.targets = targets

    def analyze(self, positions: list[Position]) -> PortfolioReport:
        market = 0.0
        cost = 0.0
        lines: list[str] = []
        for pos in positions:
            bars = self.provider.get_daily_bars(pos.code)
            price = bars[-1].close if bars else pos.cost
            mv = price * pos.shares
            cv = pos.cost * pos.shares
            market += mv
            cost += cv
            pnl = (price - pos.cost) / pos.cost if pos.cost else 0.0
            lines.append(
                f"{pos.code}: px={price:.2f} cost={pos.cost:.2f} pnl={pnl:.2%}"
            )
        pnl_pct = (market - cost) / cost if cost else 0.0
        # crude annualization assuming holding ~1 year if unknown
        annual_proxy = pnl_pct
        lo, hi = self.targets.annual_return_min, self.targets.annual_return_max
        if annual_proxy < lo:
            vs = f"below target band [{lo:.0%}, {hi:.0%}]"
        elif annual_proxy > hi:
            vs = f"above target band [{lo:.0%}, {hi:.0%}]"
        else:
            vs = f"within target band [{lo:.0%}, {hi:.0%}]"
        return PortfolioReport(
            market_value=market,
            cost_value=cost,
            pnl_pct=pnl_pct,
            annual_proxy=annual_proxy,
            vs_target=vs,
            lines=tuple(lines),
        )
