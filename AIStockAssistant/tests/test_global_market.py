from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.ai.service import AnalysisService
from app.config.settings import Settings
from app.data.global_universe import resolve_global_symbol
from app.data.yfinance_global import YFinanceGlobalClient


def test_resolve_aliases() -> None:
    assert resolve_global_symbol("标普") == "^GSPC"
    assert resolve_global_symbol("nasdaq") == "^IXIC"
    assert resolve_global_symbol("AAPL") == "AAPL"
    assert resolve_global_symbol("0700.HK") == "0700.HK"
    assert resolve_global_symbol("腾讯") == "0700.HK"


def test_list_universe_filters() -> None:
    client = YFinanceGlobalClient(enabled=True)
    us_idx = client.list_universe(region="us", kind="index")
    assert {x["symbol"] for x in us_idx} >= {"^GSPC", "^IXIC", "^DJI"}
    assert all(x["region"] == "us" and x["kind"] == "index" for x in us_idx)


def test_global_disabled() -> None:
    client = YFinanceGlobalClient(enabled=False)
    out = client.get_quotes()
    assert out["ok"] is False
    assert "disabled" in out["message"]


def _fake_history_frame(symbols: list[str]) -> pd.DataFrame:
    idx = pd.to_datetime(["2026-07-22", "2026-07-23"])
    if len(symbols) == 1:
        return pd.DataFrame(
            {
                "Open": [100.0, 101.0],
                "High": [102.0, 103.0],
                "Low": [99.0, 100.0],
                "Close": [101.0, 102.5],
                "Volume": [1e6, 1.1e6],
            },
            index=idx,
        )
    cols = pd.MultiIndex.from_product(
        [symbols, ["Open", "High", "Low", "Close", "Volume"]]
    )
    data = {}
    for sym in symbols:
        data[(sym, "Open")] = [100.0, 101.0]
        data[(sym, "High")] = [102.0, 103.0]
        data[(sym, "Low")] = [99.0, 100.0]
        data[(sym, "Close")] = [101.0, 102.5]
        data[(sym, "Volume")] = [1e6, 1.1e6]
    return pd.DataFrame(data, index=idx)


def test_get_quotes_mocked() -> None:
    client = YFinanceGlobalClient(enabled=True)
    frame = _fake_history_frame(["^GSPC", "AAPL"])
    with patch("yfinance.download", return_value=frame):
        out = client.get_quotes(symbols=["^GSPC", "AAPL"])
    assert out["ok"] is True
    assert out["provider_id"] == "yfinance_global"
    assert out["count"] == 2
    by_sym = {q["symbol"]: q for q in out["quotes"]}
    assert by_sym["AAPL"]["close"] == pytest.approx(102.5)
    assert by_sym["AAPL"]["change_pct"] == pytest.approx((102.5 - 101.0) / 101.0 * 100)


def test_get_global_bars_mocked() -> None:
    client = YFinanceGlobalClient(enabled=True)
    hist = _fake_history_frame(["AAPL"])
    ticker = MagicMock()
    ticker.history.return_value = hist
    with patch("yfinance.Ticker", return_value=ticker):
        out = client.get_daily_bars("苹果", limit=5)
    assert out["ok"] is True
    assert out["symbol"] == "AAPL"
    assert len(out["bars"]) == 2
    assert out["bars"][-1]["close"] == pytest.approx(102.5)


def test_service_and_mcp_global_tools() -> None:
    import asyncio

    import app.mcp.server as mcp_mod
    from app.mcp.server import create_mcp

    svc = AnalysisService(
        Settings.from_dict(
            {"data": {"provider": "mock", "global_enabled": True}}
        )
    )
    frame = _fake_history_frame(["^GSPC"])
    with patch("yfinance.download", return_value=frame):
        quotes = svc.global_quotes(symbols=["标普"])
    assert quotes["ok"] is True

    mcp_mod._svc = svc
    mcp = create_mcp()

    async def _run() -> None:
        tools = await mcp.list_tools()
        names = {t.name for t in tools}
        assert "global_quotes" in names
        assert "get_global_bars" in names
        assert "list_global_universe" in names
        uni = await mcp.call_tool("list_global_universe", {"region": "us"})
        assert uni is not None

    asyncio.run(_run())
