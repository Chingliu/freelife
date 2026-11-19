from __future__ import annotations

from dataclasses import dataclass

from app.data.models import Bar
from app.data.provider import IDataProvider
from app.indicators.ma import bars_close_sma
from app.indicators.macd_rsi import bars_macd, bars_rsi


@dataclass(frozen=True)
class ScreenHit:
    code: str
    reasons: tuple[str, ...]
    close: float
    as_of: str


@dataclass
class ScreenRules:
    ma_short: int = 5
    ma_long: int = 20
    require_macd_golden: bool = True
    rsi_min: float = 40.0
    rsi_max: float = 70.0


class StockScreener:
    def __init__(self, provider: IDataProvider, rules: ScreenRules | None = None) -> None:
        self.provider = provider
        self.rules = rules or ScreenRules()

    def screen(self, codes: list[str] | None = None, limit: int = 50) -> list[ScreenHit]:
        if codes is None:
            codes = [s.code for s in self.provider.get_stock_list()[:limit]]
        hits: list[ScreenHit] = []
        for code in codes:
            hit = self._eval(code)
            if hit:
                hits.append(hit)
        return hits

    def _eval(self, code: str) -> ScreenHit | None:
        bars = self.provider.get_daily_bars(code)
        need = max(self.rules.ma_long, 35)
        if len(bars) < need:
            return None
        reasons: list[str] = []
        ma_s = bars_close_sma(bars, self.rules.ma_short)
        ma_l = bars_close_sma(bars, self.rules.ma_long)
        if ma_s[-1] is None or ma_l[-1] is None:
            return None
        if ma_s[-1] > ma_l[-1]:
            reasons.append(
                f"MA{self.rules.ma_short}>{self.rules.ma_long}"
            )
        else:
            return None
        if self.rules.require_macd_golden:
            macd_pts = bars_macd(bars)
            if len(macd_pts) < 2:
                return None
            prev, cur = macd_pts[-2], macd_pts[-1]
            if (
                prev.dif is not None
                and prev.dea is not None
                and cur.dif is not None
                and cur.dea is not None
                and prev.dif <= prev.dea
                and cur.dif > cur.dea
            ):
                reasons.append("MACD golden cross")
            elif cur.dif is not None and cur.dea is not None and cur.dif > cur.dea:
                reasons.append("MACD dif>dea")
            else:
                return None
        rsi_vals = bars_rsi(bars)
        rsi_last = rsi_vals[-1]
        if rsi_last is None:
            return None
        if not (self.rules.rsi_min <= rsi_last <= self.rules.rsi_max):
            return None
        reasons.append(f"RSI={rsi_last:.1f}")
        last = bars[-1]
        return ScreenHit(
            code=code,
            reasons=tuple(reasons),
            close=last.close,
            as_of=last.trade_date.isoformat(),
        )
