from __future__ import annotations

import json
import logging
from dataclasses import asdict

from app.ai.prompts import format_tool_answer
from app.config.settings import Settings, resolve_sqlite_path
from app.data.models import SyncResult
from app.data.registry import DEFAULT_REGISTRY
from app.data.tdx_sync import TdxLocalSyncAdapter
from app.data.yfinance_global import YFinanceGlobalClient
from app.journal.decisions import DecisionJournal
from app.portfolio.analysis import PortfolioAnalyzer, Position
from app.risk.rules import evaluate_backtest
from app.strategy.backtest import SimpleMaBacktester
from app.strategy.presets import (
    STRATEGY_DESCRIPTIONS,
    list_strategy_ids,
    rules_for_strategy,
)
from app.strategy.screener import StockScreener

logger = logging.getLogger(__name__)


class AnalysisService:
    """Facade used by CLI and MCP. Never imports Tdx parsers directly."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.load()
        self.provider = DEFAULT_REGISTRY.create(self.settings)
        self.sync = DEFAULT_REGISTRY.create_sync(self.settings, self.provider)
        self.global_market = YFinanceGlobalClient(
            enabled=self.settings.data.global_enabled
        )
        db = resolve_sqlite_path(self.settings)
        self.journal = DecisionJournal(db.parent / "decisions.db")

    def try_startup_refresh(self) -> SyncResult | None:
        """Optional EOD day refresh + watchlist minute sync + finance cache. Failures never block."""
        data = self.settings.data
        want_day = data.auto_download_on_start
        want_min = data.auto_sync_minute_on_start
        want_fin = data.auto_sync_finance_on_start
        if not want_day and not want_min and not want_fin:
            return None
        if not isinstance(self.sync, TdxLocalSyncAdapter):
            return None

        messages: list[str] = []
        ok = True
        as_of = self.provider.get_data_as_of()
        day_ok = False
        try:
            if want_day:
                day = self.sync.maybe_refresh_on_start()
                messages.append(day.message)
                ok = ok and day.ok
                day_ok = day.ok
                as_of = day.as_of or as_of
            if want_min:
                minute = self.sync.maybe_sync_minutes_on_start()
                messages.append(minute.message)
                ok = ok and minute.ok
                as_of = minute.as_of or as_of
            # Finance after day path when enabled (also ok if day was already fresh).
            if want_fin and (day_ok or not want_day):
                fin = self.sync.maybe_sync_finance_on_start()
                messages.append(fin.message)
                ok = ok and fin.ok
                as_of = fin.as_of or as_of
        except Exception as exc:  # noqa: BLE001
            logger.exception("startup refresh failed")
            return SyncResult(
                ok=False,
                message=f"startup refresh failed: {exc}",
                source=self.provider.provider_id,
            )

        result = SyncResult(
            ok=ok,
            message="; ".join(messages),
            as_of=as_of,
            source=self.provider.provider_id,
        )
        logger.info("startup refresh: %s", result.message)
        return result

    def sync_status(self) -> dict:
        as_of = self.provider.get_data_as_of()
        return {
            "provider_id": self.provider.provider_id,
            "as_of": as_of.isoformat() if as_of else None,
            "stock_count": len(self.provider.get_stock_list()),
            "global_enabled": self.settings.data.global_enabled,
            "global_provider_id": self.global_market.provider_id,
        }

    def list_global_universe(
        self, region: str | None = None, kind: str | None = None
    ) -> list[dict]:
        return self.global_market.list_universe(region=region, kind=kind)

    def global_quotes(
        self,
        symbols: list[str] | None = None,
        region: str | None = None,
        kind: str | None = None,
    ) -> dict:
        return self.global_market.get_quotes(
            symbols=symbols, region=region, kind=kind
        )

    def get_global_bars(self, code: str, limit: int = 30) -> dict:
        return self.global_market.get_daily_bars(code, limit=limit)

    def get_daily_bars(self, code: str, limit: int = 30) -> list[dict]:
        code = _normalize_code(code)
        bars = self.provider.get_daily_bars(code)[-limit:]
        return [
            {
                "date": b.trade_date.isoformat(),
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
            }
            for b in bars
        ]

    def screen_stocks(
        self,
        limit: int = 30,
        strategy: str = "ma_macd_rsi",
    ) -> list[dict]:
        rules = rules_for_strategy(strategy)
        screener = StockScreener(self.provider, rules)
        scan_n = max(limit * 3, 60)
        hits = screener.screen(limit=scan_n)
        return [
            {
                "code": h.code,
                "close": h.close,
                "as_of": h.as_of,
                "reasons": list(h.reasons),
                "strategy": strategy,
            }
            for h in hits[:limit]
        ]

    def recommend(self, code: str) -> dict:
        code = _normalize_code(code)
        bt = SimpleMaBacktester(self.provider).run(code)
        verdict = evaluate_backtest(bt, self.settings.targets)
        bars = self.provider.get_daily_bars(code)
        as_of = bars[-1].trade_date.isoformat() if bars else ""
        experimental = verdict.experimental_only
        action = "hold"
        if (
            not experimental
            and bt.annual_return >= self.settings.targets.annual_return_min
        ):
            action = "buy"
        decision = DecisionJournal.make(
            code=code,
            action=action,
            reasons=[bt.evidence, *verdict.messages],
            evidence=[bt.evidence],
            risks=list(verdict.messages),
            confidence=0.55 if experimental else 0.7,
            provider_id=self.provider.provider_id,
            as_of=as_of,
            experimental=experimental,
        )
        self.journal.add(decision)
        text = format_tool_answer(
            conclusion=f"{code} -> {action}",
            reasons=decision.reasons,
            risks=decision.risks,
            confidence=decision.confidence,
            provider_id=decision.provider_id,
            as_of=decision.as_of,
            experimental=experimental,
        )
        return {"decision": asdict(decision), "narrative": text}

    def analyze_stock(self, code: str, bars_limit: int = 20) -> dict:
        code = _normalize_code(code)
        bars = self.get_daily_bars(code, limit=bars_limit)
        rec = self.recommend(code)
        last = bars[-1] if bars else None
        return {
            "code": code,
            "last_bar": last,
            "bars": bars,
            "recommendation": rec,
            "provider_id": self.provider.provider_id,
        }

    def recommend_by_strategy(
        self,
        strategy: str = "ma_macd_rsi",
        scan_limit: int = 80,
        top_n: int = 10,
    ) -> dict:
        if strategy not in STRATEGY_DESCRIPTIONS:
            strategy = "ma_macd_rsi"
        # scan_limit drives universe size via screener.screen(limit=...)
        rules = rules_for_strategy(strategy)
        hits_raw = StockScreener(self.provider, rules).screen(limit=scan_limit)
        hits = [
            {
                "code": h.code,
                "close": h.close,
                "as_of": h.as_of,
                "reasons": list(h.reasons),
                "strategy": strategy,
            }
            for h in hits_raw[:top_n]
        ]
        enriched = []
        for hit in hits:
            bt = SimpleMaBacktester(self.provider).run(hit["code"])
            verdict = evaluate_backtest(bt, self.settings.targets)
            enriched.append(
                {
                    **hit,
                    "backtest": {
                        "annual_return": bt.annual_return,
                        "max_drawdown": bt.max_drawdown,
                        "trades": bt.trades,
                        "evidence": bt.evidence,
                    },
                    "experimental": verdict.experimental_only,
                    "risk_notes": list(verdict.messages),
                }
            )
        status = self.sync_status()
        return {
            "strategy": strategy,
            "strategy_description": STRATEGY_DESCRIPTIONS[strategy],
            "scan_limit": scan_limit,
            "as_of": status.get("as_of"),
            "provider_id": status.get("provider_id"),
            "candidates": enriched,
            "available_strategies": list_strategy_ids(),
            "note": (
                "Candidates marked experimental must not be phrased as firm "
                "recommendations."
            ),
        }

    def analyze_portfolio(self, positions: list[dict]) -> dict:
        pos = [
            Position(
                code=_normalize_code(p["code"]),
                shares=float(p["shares"]),
                cost=float(p["cost"]),
            )
            for p in positions
        ]
        report = PortfolioAnalyzer(self.provider, self.settings.targets).analyze(
            pos
        )
        return {
            "market_value": report.market_value,
            "cost_value": report.cost_value,
            "pnl_pct": report.pnl_pct,
            "annual_proxy": report.annual_proxy,
            "vs_target": report.vs_target,
            "lines": list(report.lines),
        }

    def daily_report(self, screen_limit: int = 20) -> str:
        status = self.sync_status()
        hits = self.screen_stocks(limit=screen_limit)
        payload = {"status": status, "hits": hits[:10]}
        return (
            "# Daily Report\n"
            f"provider={status['provider_id']} as_of={status['as_of']}\n"
            f"candidates={len(hits)}\n"
            f"```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```\n"
        )


def _normalize_code(code: str) -> str:
    c = code.strip().lower().replace(".", "")
    if c.startswith(("sh", "sz", "bj")):
        return c
    if c.isdigit() and len(c) == 6:
        if c.startswith(("5", "6", "9")):
            return f"sh{c}"
        if c.startswith(("0", "1", "2", "3")):
            return f"sz{c}"
        if c.startswith(("4", "8")):
            return f"bj{c}"
    return c
