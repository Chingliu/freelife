"""Phase-4 macro gate from broad ETF regime (optional hook into research analyst)."""

from __future__ import annotations

from typing import Any

from app.data.models import Bar
from app.data.provider import IDataProvider
from app.indicators.ma import sma
from app.indicators.macd_rsi import rsi
from app.research.indicators import bars_adx, realized_volatility
from app.research.ai.analyst import classify_market_regime


def macro_from_etf_regime(
    provider: IDataProvider,
    *,
    code: str = "sh510300",
) -> dict[str, Any]:
    """Map ETF market regime to a composite score scale in ~[0.7, 1.0]."""
    bars = provider.get_daily_bars(code)
    if len(bars) < 80:
        return {
            "regime_hint": "unknown",
            "scale": 1.0,
            "note": f"insufficient bars for {code}",
            "source": "unavailable",
        }
    closes = [b.close for b in bars]
    ma5 = sma(closes, 5)[-1]
    ma20 = sma(closes, 20)[-1]
    ma60 = sma(closes, 60)[-1]
    adx_s, _, _ = bars_adx(bars, 14)
    vol = realized_volatility(closes, 20)[-1]
    rsi_s = rsi(closes, 14)
    snap = {
        "ma5": ma5,
        "ma20": ma20,
        "ma60": ma60,
        "adx14": adx_s[-1],
        "vol20": vol,
        "rsi14": rsi_s[-1] if rsi_s else None,
    }
    regime = classify_market_regime(snap)
    trend = str(regime.get("trend") or "unknown")
    vol_label = str(regime.get("volatility") or regime.get("vol_state") or "normal")
    scale = 1.0
    if trend == "downtrend":
        scale *= 0.75
    elif trend == "sideways":
        scale *= 0.9
    if vol_label == "high":
        scale *= 0.9
    return {
        "regime_hint": trend,
        "volatility": vol_label,
        "scale": round(scale, 3),
        "preferred_strategies": regime.get("preferred_strategies"),
        "note": "macro scale from ETF regime gate (sh510300)",
        "source": code,
        "evidence": regime.get("evidence"),
    }


def merge_macro(
    file_macro: dict[str, Any],
    etf_macro: dict[str, Any] | None,
) -> dict[str, Any]:
    """Prefer explicit file scale unless regime_hint is unknown and ETF available."""
    if not etf_macro:
        return dict(file_macro or {})
    out = dict(etf_macro)
    if file_macro.get("scale") is not None and file_macro.get("regime_hint") not in {
        None,
        "",
        "unknown",
    }:
        # Keep file override when intentionally set
        out["scale"] = float(file_macro["scale"])
        out["regime_hint"] = file_macro.get("regime_hint", out.get("regime_hint"))
        out["note"] = f"file macro override; etf={etf_macro.get('regime_hint')}"
    return out
