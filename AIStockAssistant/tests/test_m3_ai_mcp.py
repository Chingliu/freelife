from __future__ import annotations

import asyncio
import json

from app.ai.service import AnalysisService
from app.config.settings import Settings
from app.mcp.server import create_mcp, get_service


def test_analysis_service_mock() -> None:
    svc = AnalysisService(Settings.from_dict({"data": {"provider": "mock"}}))
    status = svc.sync_status()
    assert status["provider_id"] == "mock"
    bars = svc.get_daily_bars("sh600000", limit=5)
    assert len(bars) == 5
    report = svc.daily_report(screen_limit=5)
    assert "Daily Report" in report
    rec = svc.recommend("sh600000")
    assert "decision" in rec
    analyzed = svc.analyze_stock("600000")
    assert analyzed["code"] == "sh600000"
    by_strategy = svc.recommend_by_strategy("ma_trend", scan_limit=20, top_n=5)
    assert by_strategy["strategy"] == "ma_trend"
    assert "candidates" in by_strategy
    port = svc.analyze_portfolio(
        [{"code": "sh600000", "shares": 100, "cost": 10}]
    )
    assert "vs_target" in port


def test_official_mcp_lists_tools() -> None:
    # Force mock service for deterministic tool calls
    import app.mcp.server as mcp_mod

    mcp_mod._svc = AnalysisService(
        Settings.from_dict({"data": {"provider": "mock"}})
    )
    mcp = create_mcp()

    async def _run() -> None:
        tools = await mcp.list_tools()
        names = {t.name for t in tools}
        assert "analyze_stock" in names
        assert "recommend_by_strategy" in names
        assert "list_strategies" in names
        assert "get_daily_bars" in names
        assert "global_quotes" in names
        assert "get_global_bars" in names
        assert "list_global_universe" in names
        result = await mcp.call_tool("sync_status", {})
        # call_tool returns sequence of content blocks or similar
        assert result is not None

    asyncio.run(_run())
    assert get_service().provider.provider_id == "mock"
    json.dumps({"ok": True})
