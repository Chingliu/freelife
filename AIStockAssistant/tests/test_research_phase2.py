"""Phase-2 research lab: horizons, OOS, evidence, generalize, walk-forward."""

from __future__ import annotations

from datetime import date, timedelta

from app.data.models import Bar
from app.research.ai.analyst import analyze_bars_and_results, classify_market_regime
from app.research.ai.playbook import decide_position
from app.research.backtest.engine import BacktestEngine
from app.research.backtest.evidence import grade_strategy_row
from app.research.backtest.horizons import (
    assign_lifecycles,
    enrich_result_horizons,
    metrics_for_windows,
)
from app.research.backtest.splits import chronological_split, holdout_last_years, oos_pass
from app.research.backtest.walk_forward import walk_forward
from app.research.indicators import compute_indicator_snapshot
from app.research.strategies import create_strategy


def _bars(n: int = 800, code: str = "sh510300") -> list[Bar]:
    bars: list[Bar] = []
    px = 4.0
    start = date(2018, 1, 2)
    for i in range(n):
        px = max(1.0, px * (1.0 + 0.0005 + 0.008 * ((i % 25) - 12) / 100.0))
        bars.append(
            Bar(
                code=code,
                trade_date=start + timedelta(days=i),
                open=px * 0.999,
                high=px * 1.01,
                low=px * 0.99,
                close=px,
                volume=1_000_000 + i,
                amount=px * 1_000_000,
            )
        )
    return bars


def test_horizons_and_rolling():
    bars = _bars(900)
    engine = BacktestEngine(commission_bps=0.0, slippage_bps=0.0)
    result = engine.run(create_strategy("ma_20_60"), bars, code="sh510300")
    h = enrich_result_horizons(result)
    assert "metrics_3y" in h
    assert h["metrics_3y"]["status"] in {"ok", "insufficient"}
    # 900 calendar-ish days ~ 900 bars from 2018 → should have 3y
    assert h["rolling_calmar_12m"]["status"] in {"ok", "insufficient"}
    dates = [d for d, _ in result.equity_curve]
    equity = [e for _, e in result.equity_curve]
    windows = metrics_for_windows(
        equity, dates, list(result.positions), list(result.trades)
    )
    assert "3y" in windows


def test_short_history_insufficient_10y():
    bars = _bars(400)  # ~1y+
    engine = BacktestEngine(commission_bps=0.0, slippage_bps=0.0)
    result = engine.run(create_strategy("dual_momentum"), bars, code="sh588000")
    h = enrich_result_horizons(result)
    assert h["metrics_10y"]["status"] == "insufficient"


def test_oos_splits_and_analysis_fields():
    bars = _bars(600)
    engine = BacktestEngine(commission_bps=0.0, slippage_bps=0.0)
    ids = ["ma_20_60", "dual_momentum", "rsrs_timing", "vol_target", "rsi_reversion"]
    results = [engine.run(create_strategy(s), bars, code="sh510300") for s in ids]
    analysis = analyze_bars_and_results(
        "sh510300",
        bars,
        results,
        provider_id="mock",
        as_of=bars[-1].trade_date.isoformat(),
    )
    assert "candidate_set" in analysis["regime"]
    assert "evidence" in analysis["regime"]
    row = analysis["comparison"][0]
    assert "metrics_3y" in row
    assert "rolling_calmar_12m" in row
    assert "lifecycle" in row
    assert "oos" in row
    assert "evidence_grade" in row
    assert row["evidence_grade"] in {"A", "B", "C", "D"}
    d = analysis["decision"]
    assert "role_votes" in d
    assert "evidence_grade" in d
    assert "gate" in d["role_votes"]
    assert "证据等级" in analysis["report_markdown"]


def test_lifecycle_assign():
    rows = [
        {
            "strategy_id": "a",
            "rolling_calmar_12m": {
                "last": -1.0,
                "series_tail": [
                    {"calmar": -1},
                    {"calmar": -0.5},
                    {"calmar": -0.2},
                ],
            },
            "metrics_3y": {"status": "ok", "calmar": -0.1},
        },
        {
            "strategy_id": "b",
            "rolling_calmar_12m": {"last": 2.0, "series_tail": [{"calmar": 1}]},
            "metrics_3y": {"status": "ok", "calmar": 1.0},
        },
        {
            "strategy_id": "c",
            "rolling_calmar_12m": {"last": 0.5, "series_tail": [{"calmar": 0.4}]},
            "metrics_3y": {"status": "ok", "calmar": 0.2},
        },
    ]
    assign_lifecycles(rows)
    assert rows[0]["lifecycle"] in {"watch", "demoted"}
    assert rows[1]["lifecycle"] == "active"


def test_evidence_grade_with_cross():
    row = {
        "calmar": 1.0,
        "lifecycle": "active",
        "metrics_3y": {"status": "ok", "calmar": 0.5},
        "metrics_5y": {"status": "ok", "calmar": 0.4},
        "oos": {"test": {"status": "ok", "calmar": 0.3}},
        "cross_etf": {"pass": True, "score": 0.8},
    }
    assert grade_strategy_row(row) == "A"
    row2 = {**row, "cross_etf": None, "oos": {"test": {"status": "ok", "calmar": -0.1}}}
    assert grade_strategy_row(row2) in {"B", "C"}


def test_holdout_and_chrono_split():
    bars = _bars(500)
    b1 = holdout_last_years(bars, n=1.0)
    assert b1.test_end == bars[-1].trade_date
    assert b1.train_start == bars[0].trade_date
    b2 = chronological_split(bars)
    assert b2.train_end is not None
    assert b2.test_end == bars[-1].trade_date


def test_gate_veto_in_decision():
    # Build comparison where gates are flat and preferred longs
    comparison = [
        {
            "rank": 1,
            "strategy_id": "rsrs_timing",
            "current_signal": "做多",
            "current_weight": 1.0,
            "annual_return": 0.1,
            "max_drawdown": 0.1,
            "sharpe": 0.5,
            "calmar": 1.0,
            "trades": 10,
            "lifecycle": "active",
            "oos_pass": True,
            "oos": {"test": {"status": "ok", "calmar": 0.5}},
            "evidence_grade": "B",
            "metrics_3y": {"status": "ok", "calmar": 0.5},
            "metrics_5y": {"status": "ok", "calmar": 0.4},
        },
        {
            "rank": 2,
            "strategy_id": "macd_cross",
            "current_signal": "做多",
            "current_weight": 1.0,
            "calmar": 0.9,
            "annual_return": 0.1,
            "max_drawdown": 0.1,
            "sharpe": 0.4,
            "trades": 8,
            "lifecycle": "active",
            "oos_pass": True,
            "evidence_grade": "B",
            "metrics_3y": {"status": "ok", "calmar": 0.4},
            "metrics_5y": {"status": "insufficient"},
        },
        {
            "rank": 3,
            "strategy_id": "atr_breakout",
            "current_signal": "做多",
            "current_weight": 1.0,
            "calmar": 0.8,
            "annual_return": 0.1,
            "max_drawdown": 0.1,
            "sharpe": 0.4,
            "trades": 8,
            "lifecycle": "active",
            "oos_pass": True,
            "evidence_grade": "C",
            "metrics_3y": {"status": "ok", "calmar": 0.3},
            "metrics_5y": {"status": "insufficient"},
        },
        {
            "rank": 4,
            "strategy_id": "dual_momentum",
            "current_signal": "看跌",
            "current_weight": 0.0,
            "calmar": 0.2,
            "annual_return": 0.05,
            "max_drawdown": 0.1,
            "sharpe": 0.2,
            "trades": 5,
            "lifecycle": "active",
            "oos_pass": False,
            "evidence_grade": "C",
            "metrics_3y": {"status": "ok", "calmar": 0.1},
            "metrics_5y": {"status": "insufficient"},
        },
        {
            "rank": 5,
            "strategy_id": "ma_60_120",
            "current_signal": "看跌",
            "current_weight": 0.0,
            "calmar": 0.1,
            "annual_return": 0.02,
            "max_drawdown": 0.1,
            "sharpe": 0.1,
            "trades": 4,
            "lifecycle": "active",
            "oos_pass": False,
            "evidence_grade": "C",
            "metrics_3y": {"status": "ok", "calmar": 0.05},
            "metrics_5y": {"status": "insufficient"},
        },
        {
            "rank": 6,
            "strategy_id": "adx_ma_trend",
            "current_signal": "看跌",
            "current_weight": 0.0,
            "calmar": 0.05,
            "annual_return": 0.01,
            "max_drawdown": 0.1,
            "sharpe": 0.1,
            "trades": 3,
            "lifecycle": "active",
            "oos_pass": False,
            "evidence_grade": "C",
            "metrics_3y": {"status": "ok", "calmar": 0.02},
            "metrics_5y": {"status": "insufficient"},
        },
        {
            "rank": 7,
            "strategy_id": "vol_target",
            "current_signal": "做多",
            "current_weight": 0.6,
            "calmar": 0.7,
            "annual_return": 0.08,
            "max_drawdown": 0.1,
            "sharpe": 0.4,
            "trades": 20,
            "lifecycle": "active",
            "oos_pass": True,
            "evidence_grade": "B",
            "metrics_3y": {"status": "ok", "calmar": 0.4},
            "metrics_5y": {"status": "ok", "calmar": 0.3},
        },
    ]
    regime = {
        "trend": "uptrend",
        "trend_strength": "moderate",
        "volatility": "normal",
        "preferred_strategies": ["rsrs_timing", "macd_cross", "atr_breakout", "vol_target"],
        "avoid_strategies": [],
        "candidate_set": ["rsrs_timing", "macd_cross", "atr_breakout", "vol_target"],
    }
    d = decide_position("sh510300", regime, comparison)
    assert d["gate_veto"] is True
    assert d["tier"] in {"防御", "观望"}
    assert d["target_weight"] == 0.0


def test_walk_forward_smoke():
    bars = _bars(1000)
    wf = walk_forward(
        lambda: create_strategy("ma_20_60"),
        bars,
        train_years=2.0,
        test_years=0.5,
        step_years=1.0,
        engine=BacktestEngine(commission_bps=0.0, slippage_bps=0.0),
        code="sh510300",
    )
    assert "folds" in wf
    assert "summary" in wf
    assert wf["summary"]["fold_count"] >= 1


def test_oos_pass_helper():
    assert oos_pass({"status": "ok", "calmar": 0.1}) is True
    assert oos_pass({"status": "ok", "calmar": 0.0}) is False
    assert oos_pass({"status": "insufficient"}) is False


def test_regime_evidence_and_candidates():
    bars = _bars(200)
    snap = compute_indicator_snapshot(bars)
    regime = classify_market_regime(snap)
    assert "evidence" in regime
    assert isinstance(regime["evidence"], list)
    assert "candidate_set" in regime
