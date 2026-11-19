from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.data.models import Bar
from app.data.mock_provider import MockProvider
from app.research.backtest.engine import BacktestEngine
from app.research.data.feed import ResearchDataFeed
from app.research.indicators import (
    adx,
    atr,
    bollinger,
    detect_regular_divergences,
    kdj,
    momentum,
    pivot_highs,
    pivot_lows,
    realized_volatility,
    rsrs,
    sma,
)
from app.research.service import ResearchService
from app.research.strategies import create_strategy, list_research_strategies
from app.research.strategies.divergence import _weights_from_events


def _synth_bars(n: int = 400, code: str = "sh510300") -> list[Bar]:
    bars: list[Bar] = []
    px = 4.0
    start = date(2024, 1, 2)
    for i in range(n):
        # gentle drift + oscillation
        px = max(1.0, px * (1.0 + 0.0008 + 0.01 * ((i % 20) - 10) / 100.0))
        high = px * 1.01
        low = px * 0.99
        bars.append(
            Bar(
                code=code,
                trade_date=start + timedelta(days=i),
                open=px * 0.999,
                high=high,
                low=low,
                close=px,
                volume=1_000_000 + i * 10,
                amount=px * 1_000_000,
            )
        )
    return bars


def test_indicators_smoke():
    closes = [float(i) for i in range(1, 101)]
    highs = [c * 1.01 for c in closes]
    lows = [c * 0.99 for c in closes]
    assert sma(closes, 5)[-1] is not None
    assert atr(highs, lows, closes, 14)[-1] is not None
    assert bollinger(closes, 20)[-1].mid is not None
    assert kdj(highs, lows, closes)[-1].k is not None
    adx_v, pdi, mdi = adx(highs, lows, closes, 14)
    assert adx_v[-1] is not None
    assert momentum(closes, 20)[-1] is not None
    assert realized_volatility(closes, 20)[-1] is not None
    # rsrs needs longer history for z-score
    long_c = [float(i) for i in range(1, 700)]
    long_h = [c * 1.01 for c in long_c]
    long_l = [c * 0.99 for c in long_c]
    z = rsrs(long_h, long_l, window=18, z_window=600)
    assert any(v is not None for v in z)


def test_all_strategies_backtest():
    bars = _synth_bars(500)
    engine = BacktestEngine(commission_bps=0.0, slippage_bps=0.0)
    ids = [s["id"] for s in list_research_strategies()]
    assert len(ids) >= 14
    assert "rsi_divergence" in ids
    assert "macd_divergence" in ids
    for sid in ids:
        result = engine.run(create_strategy(sid), bars, code="sh510300")
        m = result.metrics
        assert m.final_equity > 0
        assert 0 <= m.max_drawdown <= 1.5
        assert 0 <= m.time_in_market <= 1.0
        assert result.current_signal in {"做多", "看跌"}
        assert 0.0 <= result.current_weight <= 1.0
        payload = result.to_dict()
        assert payload["current_signal"] == result.current_signal
        assert "sharpe" in payload["metrics"]
        assert "calmar" in payload["metrics"]


def test_pivot_and_regular_bullish_divergence():
    # left=right=2; lows at idx 4 (price 5) and 12 (price 3); confirm at 14
    price = [
        10.0,
        9.0,
        8.0,
        7.0,
        5.0,
        7.0,
        8.0,
        9.0,
        10.0,
        9.0,
        8.0,
        7.0,
        3.0,
        7.0,
        8.0,
        9.0,
        10.0,
        10.0,
        10.0,
        10.0,
        10.0,
    ]
    osc = [50.0] * len(price)
    osc[4] = 30.0
    osc[12] = 40.0  # higher low on oscillator
    assert pivot_lows(price, 2, 2)[4] == 5.0
    assert pivot_lows(price, 2, 2)[12] == 3.0
    events = detect_regular_divergences(
        price,
        osc,
        left=2,
        right=2,
        min_bars=6,
        min_osc_delta=3.0,
    )
    assert events[14] == "bullish"
    weights = _weights_from_events(events, max_hold=60)
    assert weights[14] == 1.0
    assert weights[15] == 1.0


def test_regular_bearish_divergence_exits_long():
    price = [
        1.0,
        2.0,
        3.0,
        4.0,
        8.0,
        4.0,
        3.0,
        2.0,
        3.0,
        4.0,
        5.0,
        6.0,
        12.0,
        6.0,
        5.0,
        4.0,
        4.0,
        4.0,
        4.0,
        4.0,
        4.0,
    ]
    osc = [50.0] * len(price)
    osc[4] = 70.0
    osc[12] = 55.0  # lower high on oscillator
    assert pivot_highs(price, 2, 2)[4] == 8.0
    assert pivot_highs(price, 2, 2)[12] == 12.0
    # Force a long before bearish confirm via synthetic events path
    events = detect_regular_divergences(
        price,
        osc,
        left=2,
        right=2,
        min_bars=6,
        min_osc_delta=3.0,
    )
    assert events[14] == "bearish"
    # Pre-load long then apply events
    seeded = list(events)
    seeded[0] = "bullish"
    weights = _weights_from_events(seeded, max_hold=60)
    assert weights[0] == 1.0
    assert weights[13] == 1.0
    assert weights[14] == 0.0


def test_divergence_max_hold_exit():
    events: list[str | None] = [None] * 10
    events[0] = "bullish"
    weights = _weights_from_events(events, max_hold=5)
    assert weights[0] == 1.0
    assert weights[4] == 1.0
    assert weights[5] == 0.0


def test_rsi_macd_divergence_strategies_smoke():
    bars = _synth_bars(300)
    for sid in ("rsi_divergence", "macd_divergence"):
        s = create_strategy(sid)
        w = s.generate(bars)
        assert len(w) == len(bars)
        assert all(x in (0.0, 1.0) for x in w)


def test_comparison_table_includes_current_signal():
    from app.research.ai.analyst import build_comparison_table, render_markdown_report

    bars = _synth_bars(500)
    engine = BacktestEngine(commission_bps=0.0, slippage_bps=0.0)
    results = [
        engine.run(create_strategy(sid), bars, code="sh510300")
        for sid in ("ma_5_20", "macd_cross", "rsi_reversion")
    ]
    table = build_comparison_table(results)
    assert all("current_signal" in row for row in table)
    assert all(row["current_signal"] in {"做多", "看跌"} for row in table)
    md = render_markdown_report(
        code="sh510300",
        as_of="2026-07-27",
        provider_id="mock",
        regime={"trend": "sideways", "trend_strength": "weak", "volatility": "normal", "rsi_state": "neutral", "preferred_strategies": [], "avoid_strategies": []},
        comparison=table,
    )
    assert "Signal" in md
    assert "做多" in md or "看跌" in md


def test_research_service_with_mock(monkeypatch, tmp_path):
    # Patch Settings indirectly by injecting mock provider
    provider = MockProvider()
    # Ensure mock has enough bars for strategies — MockProvider usually has some
    bars = provider.get_daily_bars("sh600000")
    if len(bars) < 120:
        pytest.skip("mock bars too short")
    svc = ResearchService.__new__(ResearchService)
    svc.settings = None
    svc.provider = provider
    svc.feed = ResearchDataFeed(provider, vipdoc=tmp_path)
    svc.engine = BacktestEngine()
    out = svc.backtest_one("sh600000", "ma_5_20")
    assert out["strategy_id"] == "ma_5_20"
    assert "metrics" in out


def test_minute_writer_roundtrip(tmp_path):
    from datetime import datetime

    from app.data.models import MinuteBar
    from app.data.tdx_minute_reader import read_minute_file
    from app.data.tdx_minute_writer import write_minute_file

    path = tmp_path / "sh510300.lc1"
    bars = [
        MinuteBar(
            code="sh510300",
            trade_time=datetime(2026, 7, 27, 9, 31),
            open=4.7,
            high=4.71,
            low=4.69,
            close=4.70,
            volume=1000,
            amount=4700,
        ),
        MinuteBar(
            code="sh510300",
            trade_time=datetime(2026, 7, 27, 9, 32),
            open=4.70,
            high=4.72,
            low=4.70,
            close=4.71,
            volume=2000,
            amount=9420,
        ),
    ]
    assert write_minute_file(path, bars, replace=True) == 2
    back = read_minute_file(path, code="sh510300")
    assert len(back) == 2
    assert abs(back[0].close - 4.70) < 1e-5
    assert back[1].trade_time.minute == 32
    assert write_minute_file(path, bars, replace=False) == 0  # no newer
