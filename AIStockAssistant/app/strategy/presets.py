from __future__ import annotations

from app.strategy.screener import ScreenRules

STRATEGY_DESCRIPTIONS: dict[str, str] = {
    "ma_macd_rsi": "MA short>long + MACD positive + RSI mid-range (default)",
    "ma_trend": "MA short>long trend only (no MACD golden required)",
    "rsi_mid": "MA trend + RSI between 45 and 65",
}


def rules_for_strategy(strategy: str) -> ScreenRules:
    key = (strategy or "ma_macd_rsi").strip().lower()
    if key == "ma_trend":
        return ScreenRules(
            ma_short=5,
            ma_long=20,
            require_macd_golden=False,
            rsi_min=0.0,
            rsi_max=100.0,
        )
    if key == "rsi_mid":
        return ScreenRules(
            ma_short=5,
            ma_long=20,
            require_macd_golden=False,
            rsi_min=45.0,
            rsi_max=65.0,
        )
    # default ma_macd_rsi
    return ScreenRules(
        ma_short=5,
        ma_long=20,
        require_macd_golden=True,
        rsi_min=40.0,
        rsi_max=70.0,
    )


def list_strategy_ids() -> list[str]:
    return list(STRATEGY_DESCRIPTIONS.keys())
