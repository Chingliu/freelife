from __future__ import annotations

from typing import Callable

from app.research.strategies.adx_trend import AdxTrendStrategy
from app.research.strategies.atr_breakout import AtrBreakoutStrategy
from app.research.strategies.base import Strategy
from app.research.strategies.bollinger import BollingerReversionStrategy
from app.research.strategies.divergence import MacdDivergenceStrategy, RsiDivergenceStrategy
from app.research.strategies.dual_momentum import DualMomentumStrategy
from app.research.strategies.kdj_cross import KdjCrossStrategy
from app.research.strategies.ma_cross import MaCrossStrategy
from app.research.strategies.macd_cross import MacdCrossStrategy
from app.research.strategies.rsi_reversion import RsiReversionStrategy
from app.research.strategies.rsrs_timing import RsrsTimingStrategy
from app.research.strategies.vol_target import VolatilityTargetStrategy

StrategyFactory = Callable[[], Strategy]


def _factories() -> dict[str, StrategyFactory]:
    return {
        "ma_5_20": lambda: MaCrossStrategy(5, 20),
        "ma_20_60": lambda: MaCrossStrategy(20, 60),
        "ma_60_120": lambda: MaCrossStrategy(60, 120),
        "dual_momentum": lambda: DualMomentumStrategy(lookback=252),
        "macd_cross": lambda: MacdCrossStrategy(),
        "rsi_reversion": lambda: RsiReversionStrategy(),
        "bollinger_reversion": lambda: BollingerReversionStrategy(),
        "atr_breakout": lambda: AtrBreakoutStrategy(),
        "adx_ma_trend": lambda: AdxTrendStrategy(),
        "kdj_cross": lambda: KdjCrossStrategy(),
        "rsrs_timing": lambda: RsrsTimingStrategy(),
        "vol_target": lambda: VolatilityTargetStrategy(target_vol=0.12),
        "rsi_divergence": lambda: RsiDivergenceStrategy(),
        "macd_divergence": lambda: MacdDivergenceStrategy(),
    }


def list_research_strategies() -> list[dict[str, str]]:
    out = []
    for sid, factory in _factories().items():
        s = factory()
        out.append(
            {
                "id": sid,
                "name": s.name,
                "description": s.description,
                "params": str(s.params),
            }
        )
    return out


def create_strategy(strategy_id: str) -> Strategy:
    factories = _factories()
    if strategy_id not in factories:
        known = ", ".join(sorted(factories))
        raise KeyError(f"unknown research strategy '{strategy_id}'; known: {known}")
    return factories[strategy_id]()


def all_strategies() -> list[Strategy]:
    return [f() for f in _factories().values()]


DEFAULT_STRATEGY_IDS: tuple[str, ...] = tuple(_factories().keys())
