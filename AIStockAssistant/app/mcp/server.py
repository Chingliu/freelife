"""Official MCP (FastMCP) server for Cursor.

Run: python -m app.mcp.server
Configure Cursor with docs/mcp.cursor.example.json
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from app.ai.prompts import SYSTEM_ANALYST
from app.ai.service import AnalysisService
from app.research.service import ResearchService
from app.selection.service import SelectionService
from app.strategy.presets import STRATEGY_DESCRIPTIONS, list_strategy_ids

_svc: AnalysisService | None = None
_research: ResearchService | None = None
_selection: SelectionService | None = None


def get_service() -> AnalysisService:
    global _svc
    if _svc is None:
        _svc = AnalysisService()
        _svc.try_startup_refresh()
    return _svc


def get_research() -> ResearchService:
    global _research
    if _research is None:
        # Reuse refreshed provider from analysis service
        svc = get_service()
        _research = ResearchService(settings=svc.settings, provider=svc.provider)
    return _research


def get_selection() -> SelectionService:
    global _selection
    if _selection is None:
        svc = get_service()
        _selection = SelectionService(settings=svc.settings, provider=svc.provider)
    return _selection


def create_mcp() -> FastMCP:
    mcp = FastMCP(
        name="ai-stock-assistant",
        instructions=(
            SYSTEM_ANALYST
            + "\n\n"
            + "You have tools to query local Tongdaxin A-share data and "
            + "global (EU/US/APAC) index/mega-cap quotes via Yahoo Finance. "
            + "A-shares: analyze_stock / get_daily_bars / recommend "
            + "(codes like sh600000 / sz000001). "
            + "Strategy picks: list_strategies then recommend_by_strategy. "
            + "Global markets: list_global_universe, global_quotes, get_global_bars "
            + "(symbols like ^GSPC, AAPL, 0700.HK). "
            + "ETF research platform: research_data_status, list_research_strategies, "
            + "research_backtest_etf, research_compare_strategies, "
            + "research_daily_report, get_minute_bars. "
            + "Index-constituent stock selection (SSE50/CSI300/CSI500 Top10): "
            + "selection_data_status, selection_universe, selection_run_daily, "
            + "selection_stock_report, selection_factor_validation, selection_daily_report. "
            + "Do not use screen_stocks/recommend to replace selection_*."
        ),
    )

    @mcp.tool()
    def sync_status() -> dict[str, Any]:
        """Check data provider id, latest trade date, and stock universe size."""
        return get_service().sync_status()

    @mcp.tool()
    def list_strategies() -> list[dict[str, str]]:
        """List available screening/recommendation strategy ids and descriptions."""
        return [
            {"id": sid, "description": STRATEGY_DESCRIPTIONS[sid]}
            for sid in list_strategy_ids()
        ]

    @mcp.tool()
    def get_daily_bars(code: str, limit: int = 30) -> list[dict[str, Any]]:
        """Get recent daily OHLCV bars for a stock code (e.g. sh600000, sz000001)."""
        return get_service().get_daily_bars(code, limit=limit)

    @mcp.tool()
    def analyze_stock(code: str, bars_limit: int = 20) -> dict[str, Any]:
        """
        Analyze one stock: latest bars summary + backtest-gated buy/hold/sell narrative.
        Use when the user asks about a specific ticker.
        """
        return get_service().analyze_stock(code, bars_limit=bars_limit)

    @mcp.tool()
    def recommend(code: str) -> dict[str, Any]:
        """Backtest-gated suggestion for one stock (buy/hold + evidence + risks)."""
        return get_service().recommend(code)

    @mcp.tool()
    def recommend_by_strategy(
        strategy: str = "ma_macd_rsi",
        scan_limit: int = 80,
        top_n: int = 10,
    ) -> dict[str, Any]:
        """
        Screen the universe with a named strategy and return top candidates
        with reasons. Strategies: ma_macd_rsi, ma_trend, rsi_mid.
        Use when the user asks for stock picks / recommendations by strategy.
        """
        return get_service().recommend_by_strategy(
            strategy=strategy, scan_limit=scan_limit, top_n=top_n
        )

    @mcp.tool()
    def screen_stocks(
        strategy: str = "ma_macd_rsi",
        limit: int = 40,
    ) -> list[dict[str, Any]]:
        """Rule-based stock screen; returns hits with hit reasons."""
        return get_service().screen_stocks(limit=limit, strategy=strategy)

    @mcp.tool()
    def analyze_portfolio(positions_json: str) -> dict[str, Any]:
        """
        Analyze holdings vs 5%-10% annual target.
        positions_json example:
        [{"code":"sh600000","shares":1000,"cost":9.5}]
        """
        positions = json.loads(positions_json)
        if not isinstance(positions, list):
            raise ValueError("positions_json must be a JSON list")
        return get_service().analyze_portfolio(positions)

    @mcp.tool()
    def daily_report(limit: int = 20) -> str:
        """Generate a markdown daily report with status and screen candidates."""
        return get_service().daily_report(screen_limit=limit)

    @mcp.tool()
    def list_global_universe(
        region: str = "",
        kind: str = "",
    ) -> list[dict[str, str]]:
        """
        List the built-in EU/US/APAC index & mega-cap watchlist.
        region: us|eu|apac (empty=all). kind: index|equity (empty=all).
        """
        return get_service().list_global_universe(
            region=region or None,
            kind=kind or None,
        )

    @mcp.tool()
    def global_quotes(
        symbols_csv: str = "",
        region: str = "",
        kind: str = "",
    ) -> dict[str, Any]:
        """
        Latest quotes for global indices/mega-caps (Yahoo Finance, may be delayed).
        symbols_csv: optional comma-separated Yahoo symbols or aliases
        (e.g. '^GSPC,AAPL,纳指'). Empty = full minimal universe.
        region/kind filter the default universe when symbols_csv is empty.
        """
        symbols = (
            [s.strip() for s in symbols_csv.split(",") if s.strip()]
            if symbols_csv.strip()
            else None
        )
        return get_service().global_quotes(
            symbols=symbols,
            region=region or None,
            kind=kind or None,
        )

    @mcp.tool()
    def get_global_bars(code: str, limit: int = 30) -> dict[str, Any]:
        """
        Recent daily OHLCV for a global symbol (e.g. ^GSPC, AAPL, 0700.HK, 标普).
        Separate from A-share get_daily_bars.
        """
        return get_service().get_global_bars(code, limit=limit)

    # ----- Phase-1 ETF research platform -----

    @mcp.tool()
    def research_data_status(codes_csv: str = "") -> dict[str, Any]:
        """Check ETF research data readiness (daily/minute/volume) for codes."""
        codes = (
            [c.strip() for c in codes_csv.split(",") if c.strip()]
            if codes_csv.strip()
            else None
        )
        return get_research().data_status(codes)

    @mcp.tool()
    def list_research_etfs() -> list[dict[str, str]]:
        """List built-in broad ETF universe for research."""
        return get_research().list_etfs()

    @mcp.tool()
    def list_research_strategies() -> list[dict[str, str]]:
        """List ETF research strategies (MA/MACD/RSI/RSRS/momentum/vol etc.)."""
        return get_research().list_strategies()

    @mcp.tool()
    def research_backtest_etf(
        code: str,
        strategy_id: str = "",
    ) -> dict[str, Any]:
        """
        Backtest one ETF. If strategy_id empty, run all research strategies
        and return comparison + market regime + AI analysis prompts.
        """
        rs = get_research()
        if strategy_id.strip():
            return rs.backtest_one(code, strategy_id.strip())
        return rs.backtest_all(code)

    @mcp.tool()
    def research_compare_strategies(code: str) -> dict[str, Any]:
        """Compare all research strategies on one ETF; includes failure notes."""
        return get_research().backtest_all(code)

    @mcp.tool()
    def research_daily_report(
        codes_csv: str = "",
        attach_cross_etf: bool = False,
    ) -> dict[str, Any]:
        """Daily market-state + strategy suggestion report for broad + QDII ETFs."""
        codes = [c.strip() for c in codes_csv.split(",") if c.strip()]
        return get_research().daily_research_report(
            codes or None, attach_cross_etf=attach_cross_etf
        )

    @mcp.tool()
    def research_generalize_strategy(
        strategy_id: str,
        codes_csv: str = "",
    ) -> dict[str, Any]:
        """
        Cross-ETF generalization for one strategy on broad ETFs.
        Returns per-ETF OOS metrics, pass_count, median_calmar, score, pass.
        """
        codes = [c.strip() for c in codes_csv.split(",") if c.strip()] or None
        return get_research().generalize_strategy(strategy_id, codes=codes)

    @mcp.tool()
    def research_walk_forward(
        code: str,
        strategy_id: str,
        train_years: float = 3.0,
        test_years: float = 1.0,
        step_years: float = 1.0,
    ) -> dict[str, Any]:
        """
        Optional walk-forward lab (not daily default). Rolling OOS folds for one
        strategy/ETF; fixed-param strategies validate temporal stability.
        """
        return get_research().walk_forward_strategy(
            code,
            strategy_id,
            train_years=train_years,
            test_years=test_years,
            step_years=step_years,
        )

    @mcp.tool()
    def get_minute_bars(
        code: str,
        freq: str = "1m",
        limit: int = 100,
        auto_sync: bool = True,
    ) -> dict[str, Any]:
        """
        Read Tongdaxin local minute bars (.lc1/.lc5).
        If local files are empty and auto_sync=true, fetch via pytdx into vipdoc.
        """
        return get_research().get_minute_bars(
            code, freq=freq, limit=limit, auto_sync=auto_sync
        )

    @mcp.tool()
    def sync_minute_bars(
        code: str,
        freq: str = "1m",
        max_bars: int = 2400,
    ) -> dict[str, Any]:
        """Download minute bars via pytdx and write into local vipdoc minline/fzline."""
        return get_research().sync_minute(code, freq=freq, max_bars=max_bars)

    # ----- Seven-layer index-constituent selection -----

    @mcp.tool()
    def selection_data_status() -> dict[str, Any]:
        """Check constituent universe, daily bars sample, and meta provider readiness."""
        return get_selection().data_status()

    @mcp.tool()
    def selection_universe() -> dict[str, Any]:
        """L1 pool snapshot plus L2 filter kept/rejected counts."""
        return get_selection().universe_snapshot()

    @mcp.tool()
    def selection_run_daily(
        top_n: int = 10,
        max_per_sector: int = 3,
        with_validation: bool = False,
    ) -> dict[str, Any]:
        """
        Run L1→L4: SSE50∪CSI300∪CSI500 → filters → multi-factor scores → TopN.
        with_validation=true runs L7 IC and applies demoted factor weights (slower).
        """
        return get_selection().run_daily(
            top_n=top_n,
            max_per_sector=max_per_sector,
            with_validation=with_validation,
        )

    @mcp.tool()
    def selection_stock_report(
        code: str,
        with_validation: bool = False,
    ) -> dict[str, Any]:
        """
        Full per-stock research report: reasons, evidence chain, risks,
        entry/stop/invalidate/observe. Research observation only.
        """
        return get_selection().stock_report(code, with_validation=with_validation)

    @mcp.tool()
    def selection_factor_validation(
        factor_id: str = "",
        months: int = 12,
    ) -> dict[str, Any]:
        """L7 factor health: IC / RankIC / long-short / lifecycle. Empty factor_id = all."""
        return get_selection().factor_validation(factor_id, months=months, refresh=True)

    @mcp.tool()
    def selection_daily_report(
        top_n: int = 10,
        with_validation: bool = False,
        include_stock_reports: bool = True,
    ) -> dict[str, Any]:
        """Daily TopN selection digest with optional per-stock L5/L6 reports."""
        return get_selection().daily_report(
            top_n=top_n,
            with_validation=with_validation,
            include_stock_reports=include_stock_reports,
        )

    return mcp


def main() -> None:
    create_mcp().run(transport="stdio")


if __name__ == "__main__":
    main()
