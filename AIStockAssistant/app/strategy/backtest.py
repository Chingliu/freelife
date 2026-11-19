from __future__ import annotations

from dataclasses import dataclass

from app.data.models import Bar
from app.data.provider import IDataProvider
from app.indicators.ma import bars_close_sma


@dataclass(frozen=True)
class BacktestResult:
    code: str
    trades: int
    total_return: float
    annual_return: float
    max_drawdown: float
    win_rate: float
    evidence: str


class SimpleMaBacktester:
    """Long-only MA cross backtest used as recommendation evidence gate."""

    def __init__(
        self,
        provider: IDataProvider,
        short: int = 5,
        long: int = 20,
    ) -> None:
        self.provider = provider
        self.short = short
        self.long = long

    def run(self, code: str) -> BacktestResult:
        bars = self.provider.get_daily_bars(code)
        return self.run_bars(code, bars)

    def run_bars(self, code: str, bars: list[Bar]) -> BacktestResult:
        if len(bars) < self.long + 2:
            return BacktestResult(
                code=code,
                trades=0,
                total_return=0.0,
                annual_return=0.0,
                max_drawdown=0.0,
                win_rate=0.0,
                evidence="insufficient bars",
            )
        ma_s = bars_close_sma(bars, self.short)
        ma_l = bars_close_sma(bars, self.long)
        cash = 1.0
        position = 0.0
        entry = 0.0
        equity = 1.0
        peak = 1.0
        max_dd = 0.0
        trades = 0
        wins = 0
        returns: list[float] = []

        for i in range(1, len(bars)):
            if ma_s[i] is None or ma_l[i] is None or ma_s[i - 1] is None or ma_l[i - 1] is None:
                continue
            price = bars[i].close
            # golden
            if position == 0 and ma_s[i - 1] <= ma_l[i - 1] and ma_s[i] > ma_l[i]:
                position = cash / price
                cash = 0.0
                entry = price
                trades += 1
            # death
            elif position > 0 and ma_s[i - 1] >= ma_l[i - 1] and ma_s[i] < ma_l[i]:
                cash = position * price
                ret = (price - entry) / entry
                returns.append(ret)
                if ret > 0:
                    wins += 1
                position = 0.0

            equity = cash + position * price
            peak = max(peak, equity)
            dd = (peak - equity) / peak if peak else 0.0
            max_dd = max(max_dd, dd)

        if position > 0:
            cash = position * bars[-1].close
            equity = cash
            ret = (bars[-1].close - entry) / entry
            returns.append(ret)
            if ret > 0:
                wins += 1
            position = 0.0

        total_return = equity - 1.0
        days = max((bars[-1].trade_date - bars[0].trade_date).days, 1)
        annual = (1 + total_return) ** (365 / days) - 1
        win_rate = (wins / len(returns)) if returns else 0.0
        evidence = (
            f"MA{self.short}/{self.long} long-only; trades={trades}; "
            f"ann={annual:.2%}; mdd={max_dd:.2%}"
        )
        return BacktestResult(
            code=code,
            trades=trades,
            total_return=total_return,
            annual_return=annual,
            max_drawdown=max_dd,
            win_rate=win_rate,
            evidence=evidence,
        )
