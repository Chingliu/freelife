from __future__ import annotations

from datetime import date, timedelta

from app.data.models import Bar
from app.research.ai.analyst import analyze_bars_and_results
from app.research.ai.playbook import (
    render_daily_playbook,
    render_symbol_playbook_markdown,
)
from app.research.backtest.engine import BacktestEngine
from app.research.data.etf_universe import (
    BROAD_ETFS,
    QDII_ETFS,
    default_research_codes,
)
from app.research.strategies import create_strategy


def _bars(n: int = 400) -> list[Bar]:
    bars: list[Bar] = []
    px = 4.0
    start = date(2024, 1, 2)
    for i in range(n):
        px = max(1.0, px * (1.0 + 0.0008 + 0.01 * ((i % 20) - 10) / 100.0))
        bars.append(
            Bar(
                code="sh510300",
                trade_date=start + timedelta(days=i),
                open=px * 0.999,
                high=px * 1.01,
                low=px * 0.99,
                close=px,
                volume=1_000_000,
                amount=px * 1_000_000,
            )
        )
    return bars


def test_universe_defaults():
    assert len(BROAD_ETFS) == 7
    assert len(QDII_ETFS) == 5
    codes = default_research_codes()
    assert "sh588000" in codes
    assert "sz159915" in codes
    assert "sh510210" in codes
    assert "sh513100" in codes
    assert codes[:7] == [e.code for e in BROAD_ETFS]


def test_decide_position_has_required_fields():
    bars = _bars(500)
    engine = BacktestEngine(commission_bps=0.0, slippage_bps=0.0)
    results = [
        engine.run(create_strategy(sid), bars, code="sh510300")
        for sid in (
            "ma_20_60",
            "dual_momentum",
            "rsrs_timing",
            "vol_target",
            "rsi_reversion",
            "macd_cross",
        )
    ]
    analysis = analyze_bars_and_results(
        "sh510300",
        bars,
        results,
        provider_id="mock",
        as_of="2026-07-28",
    )
    d = analysis["decision"]
    assert d["tier"] in {"防御", "观望", "试探", "风险开启"}
    assert 0.0 <= d["target_weight"] <= 1.0
    assert "rationale" in d
    md = analysis["report_markdown"]
    assert "仓位决策表" in md
    assert "全策略当前信号表" in md


def test_render_daily_overview():
    decision = {
        "label": "sh510300（沪深300ETF）",
        "tier": "观望",
        "target_weight": 0.0,
        "preferred_long": 1,
        "preferred_n": 3,
        "top3_long": 1,
        "name": "沪深300ETF",
        "code": "sh510300",
        "full_table_votes": {"做多": 2, "看跌": 4},
        "preferred": [],
        "calmar1": {
            "strategy_id": "rsrs_timing",
            "label": "rsrs_timing（RSRS 择时）",
            "current_signal": "看跌",
            "veto": False,
        },
        "vol_target_weight": 0.0,
        "rationale": "test",
    }
    regime = {
        "trend": "sideways",
        "trend_strength": "weak",
        "volatility": "normal",
        "rsi_state": "neutral",
        "preferred_strategies": ["vol_target"],
        "avoid_strategies": [],
    }
    comparison = [
        {
            "rank": 1,
            "strategy_id": "vol_target",
            "current_signal": "做多",
            "current_weight": 0.4,
            "annual_return": 0.1,
            "max_drawdown": 0.1,
            "sharpe": 0.5,
            "calmar": 1.0,
            "trades": 10,
            "failure_notes": ["ok"],
            "param_suggestions": ["ok"],
        }
    ]
    section_md = render_symbol_playbook_markdown(
        code="sh510300",
        as_of="2026-07-28",
        provider_id="mock",
        regime=regime,
        comparison=comparison,
        decision=decision,
    )
    assert "仓位决策表" in section_md
    daily = render_daily_playbook(
        provider_id="mock",
        as_of="2026-07-28",
        sections=[
            {
                "decision": decision,
                "regime": regime,
                "report_markdown": section_md,
            }
        ],
        skipped=[{"code": "sh513999", "reason": "missing"}],
    )
    assert "总览" in daily
    assert "sh513999" in daily


def test_email_body_html_contains_overview():
    from app.research.ai.playbook import email_body_html

    decision = {
        "label": "sh510300（沪深300ETF）",
        "tier": "观望",
        "target_weight": 0.0,
        "preferred_long": 1,
        "preferred_n": 3,
        "top3_long": 1,
        "name": "沪深300ETF",
        "code": "sh510300",
        "full_table_votes": {"做多": 2, "看跌": 4},
        "preferred": [],
        "calmar1": {
            "strategy_id": "rsrs_timing",
            "label": "rsrs_timing（RSRS 择时）",
            "current_signal": "看跌",
            "veto": False,
        },
        "vol_target_weight": 0.0,
        "rationale": "test",
    }
    html = email_body_html(
        [
            {
                "decision": decision,
                "regime": {
                    "trend": "sideways",
                    "trend_strength": "weak",
                    "volatility": "normal",
                    "rsi_state": "neutral",
                    "snapshot": {"close": 4.0},
                },
                "comparison": [],
            }
        ],
        "2026-07-28",
        provider_id="mock",
    )
    assert "<table" in html
    assert "观望" in html
    assert "沪深300ETF" in html
    assert "看图说话" in html
