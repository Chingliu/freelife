from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from app.data.global_universe import (
    GLOBAL_UNIVERSE,
    GlobalSymbol,
    list_global_universe,
    resolve_global_symbol,
)
from app.data.models import Bar

logger = logging.getLogger(__name__)

PROVIDER_ID = "yfinance_global"


class YFinanceGlobalClient:
    """Fetch EU/US/APAC index & mega-cap quotes via Yahoo Finance (yfinance)."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    @property
    def provider_id(self) -> str:
        return PROVIDER_ID

    def list_universe(
        self, region: str | None = None, kind: str | None = None
    ) -> list[dict[str, str]]:
        return [
            {
                "symbol": s.symbol,
                "name": s.name,
                "region": s.region,
                "kind": s.kind,
            }
            for s in list_global_universe(region=region, kind=kind)
        ]

    def get_quotes(
        self,
        symbols: list[str] | None = None,
        region: str | None = None,
        kind: str | None = None,
    ) -> dict[str, Any]:
        if not self.enabled:
            return {
                "provider_id": PROVIDER_ID,
                "ok": False,
                "message": "global market disabled in config",
                "quotes": [],
            }
        targets = self._resolve_targets(symbols, region=region, kind=kind)
        if not targets:
            return {
                "provider_id": PROVIDER_ID,
                "ok": False,
                "message": "no symbols resolved",
                "quotes": [],
            }
        try:
            import yfinance as yf
        except ImportError as exc:  # pragma: no cover
            return {
                "provider_id": PROVIDER_ID,
                "ok": False,
                "message": f"yfinance not installed: {exc}",
                "quotes": [],
            }

        ysyms = [t.symbol for t in targets]
        meta = {t.symbol: t for t in targets}
        quotes: list[dict[str, Any]] = []
        errors: list[str] = []

        # Batch download recent daily bars for last/prev close.
        try:
            frame = yf.download(
                ysyms,
                period="10d",
                interval="1d",
                group_by="ticker",
                auto_adjust=True,
                threads=True,
                progress=False,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("yfinance download failed")
            return {
                "provider_id": PROVIDER_ID,
                "ok": False,
                "message": f"download failed: {exc}",
                "quotes": [],
            }

        for sym in ysyms:
            try:
                q = _quote_from_frame(frame, sym, len(ysyms) == 1)
                if q is None:
                    errors.append(f"{sym}: no data")
                    continue
                info = meta.get(sym)
                quotes.append(
                    {
                        "symbol": sym,
                        "name": info.name if info else sym,
                        "region": info.region if info else "",
                        "kind": info.kind if info else "",
                        **q,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{sym}: {exc}")

        as_of = None
        if quotes:
            as_of = max(q["as_of"] for q in quotes if q.get("as_of"))
        return {
            "provider_id": PROVIDER_ID,
            "ok": bool(quotes),
            "as_of": as_of,
            "count": len(quotes),
            "quotes": quotes,
            "errors": errors,
            "note": "Data via Yahoo Finance; may be delayed. Not for HFT.",
        }

    def get_daily_bars(self, code: str, limit: int = 30) -> dict[str, Any]:
        if not self.enabled:
            return {
                "provider_id": PROVIDER_ID,
                "ok": False,
                "symbol": code,
                "message": "global market disabled in config",
                "bars": [],
            }
        symbol = resolve_global_symbol(code)
        if not symbol:
            return {
                "provider_id": PROVIDER_ID,
                "ok": False,
                "symbol": code,
                "message": f"unknown symbol: {code}",
                "bars": [],
            }
        try:
            import yfinance as yf
        except ImportError as exc:  # pragma: no cover
            return {
                "provider_id": PROVIDER_ID,
                "ok": False,
                "symbol": symbol,
                "message": f"yfinance not installed: {exc}",
                "bars": [],
            }

        limit = max(1, min(int(limit), 500))
        try:
            hist = yf.Ticker(symbol).history(period="1y", auto_adjust=True)
        except Exception as exc:  # noqa: BLE001
            return {
                "provider_id": PROVIDER_ID,
                "ok": False,
                "symbol": symbol,
                "message": f"history failed: {exc}",
                "bars": [],
            }
        if hist is None or hist.empty:
            return {
                "provider_id": PROVIDER_ID,
                "ok": False,
                "symbol": symbol,
                "message": "empty history",
                "bars": [],
            }
        bars = _bars_from_history(symbol, hist)[-limit:]
        return {
            "provider_id": PROVIDER_ID,
            "ok": True,
            "symbol": symbol,
            "as_of": bars[-1].trade_date.isoformat() if bars else None,
            "bars": [
                {
                    "date": b.trade_date.isoformat(),
                    "open": b.open,
                    "high": b.high,
                    "low": b.low,
                    "close": b.close,
                    "volume": b.volume,
                }
                for b in bars
            ],
        }

    def _resolve_targets(
        self,
        symbols: list[str] | None,
        region: str | None = None,
        kind: str | None = None,
    ) -> list[GlobalSymbol]:
        if symbols:
            out: list[GlobalSymbol] = []
            by_sym = {s.symbol: s for s in GLOBAL_UNIVERSE}
            for raw in symbols:
                resolved = resolve_global_symbol(raw)
                if not resolved:
                    continue
                if resolved in by_sym:
                    out.append(by_sym[resolved])
                else:
                    out.append(
                        GlobalSymbol(
                            symbol=resolved,
                            name=resolved,
                            region="",
                            kind="",
                        )
                    )
            return out
        return list_global_universe(region=region, kind=kind)


def _quote_from_frame(frame: Any, symbol: str, single: bool) -> dict[str, Any] | None:
    import pandas as pd

    if frame is None or getattr(frame, "empty", True):
        return None
    try:
        if single and not isinstance(frame.columns, pd.MultiIndex):
            sub = frame
        else:
            if isinstance(frame.columns, pd.MultiIndex):
                # yfinance may use (symbol, field) or (field, symbol)
                level0 = set(frame.columns.get_level_values(0))
                if symbol in level0:
                    sub = frame[symbol]
                else:
                    sub = frame.xs(symbol, axis=1, level=1)
            else:
                sub = frame
        sub = sub.dropna(how="all")
        if sub.empty:
            return None
        last = sub.iloc[-1]
        prev = sub.iloc[-2] if len(sub) >= 2 else None
        close = float(last["Close"])
        prev_close = float(prev["Close"]) if prev is not None else None
        change = (close - prev_close) if prev_close not in (None, 0) else None
        change_pct = (change / prev_close * 100.0) if change is not None and prev_close else None
        as_of = _index_to_date(sub.index[-1])
        return {
            "as_of": as_of.isoformat() if as_of else None,
            "open": float(last["Open"]),
            "high": float(last["High"]),
            "low": float(last["Low"]),
            "close": close,
            "volume": float(last.get("Volume") or 0.0),
            "prev_close": prev_close,
            "change": change,
            "change_pct": change_pct,
        }
    except Exception:  # noqa: BLE001
        return None


def _bars_from_history(symbol: str, hist: Any) -> list[Bar]:
    bars: list[Bar] = []
    for idx, row in hist.iterrows():
        td = _index_to_date(idx)
        if td is None:
            continue
        bars.append(
            Bar(
                code=symbol,
                trade_date=td,
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=float(row.get("Volume") or 0.0),
            )
        )
    return bars


def _index_to_date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return value.to_pydatetime().date()  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        return None
