from __future__ import annotations

from app.config.settings import Settings
from app.data.mock_provider import MockProvider
from app.indicators.ma import sma
from app.indicators.macd_rsi import macd, rsi
from app.journal.decisions import DecisionJournal
from app.portfolio.analysis import PortfolioAnalyzer, Position
from app.risk.rules import evaluate_backtest, position_size_ok
from app.strategy.backtest import SimpleMaBacktester
from app.strategy.screener import StockScreener


def test_indicators() -> None:
    values = [float(i) for i in range(1, 40)]
    assert sma(values, 5)[-1] is not None
    assert macd(values)[-1].dif is not None
    assert rsi(values)[-1] is not None


def test_screener_and_backtest() -> None:
    p = MockProvider()
    hits = StockScreener(p).screen(limit=10)
    assert isinstance(hits, list)
    bt = SimpleMaBacktester(p).run("sh600000")
    assert bt.trades >= 0
    settings = Settings.from_dict({})
    verdict = evaluate_backtest(bt, settings.targets)
    assert verdict.allowed


def test_journal_and_portfolio(tmp_path) -> None:
    j = DecisionJournal(tmp_path / "d.db")
    d = DecisionJournal.make(
        code="sh600000",
        action="buy",
        reasons=["ma"],
        evidence=["bt"],
        risks=["mdd"],
        confidence=0.6,
        provider_id="mock",
        as_of="2024-01-02",
        experimental=True,
    )
    j.add(d)
    assert j.list(1)[0].code == "sh600000"
    p = MockProvider()
    report = PortfolioAnalyzer(p, Settings.from_dict({}).targets).analyze(
        [Position(code="sh600000", shares=100, cost=10.0)]
    )
    assert report.market_value > 0
    assert position_size_ok(0.1, 0.3, Settings.from_dict({}).targets).allowed
