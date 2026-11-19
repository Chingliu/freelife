from __future__ import annotations

from datetime import date, timedelta
from email.message import EmailMessage
from pathlib import Path

from app.data.models import Bar
from app.research.ai.playbook import email_body_html
from app.research.notify.chart_talk import (
    collect_inline_images,
    generate_chart_talk,
)
from app.research.notify.email_smtp import build_email_message


def _bars(n: int = 120, code: str = "sh510210") -> list[Bar]:
    bars: list[Bar] = []
    px = 1.0
    start = date(2025, 12, 1)
    for i in range(n):
        px = max(0.5, px * (1.0 + 0.001 * ((i % 17) - 8)))
        bars.append(
            Bar(
                code=code,
                trade_date=start + timedelta(days=i),
                open=px * 0.999,
                high=px * 1.01,
                low=px * 0.99,
                close=px,
                volume=1_000_000 + i * 1000,
                amount=px * 1_000_000,
            )
        )
    return bars


def _decision(code: str = "sh510210") -> dict:
    return {
        "code": code,
        "name": "上证综指ETF",
        "label": f"{code}（上证综指ETF）",
        "tier": "试探",
        "target_weight": 0.35,
        "preferred_long": 2,
        "preferred_n": 3,
        "top3_long": 2,
        "full_table_votes": {"做多": 5, "看跌": 9},
        "preferred": [
            {
                "strategy_id": "dual_momentum",
                "label": "dual_momentum（绝对动量择时）",
                "current_signal": "做多",
                "current_weight": 1.0,
            }
        ],
        "calmar1": {
            "strategy_id": "rsi_reversion",
            "label": "rsi_reversion（RSI 均值回归）",
            "current_signal": "做多",
            "veto": False,
        },
        "vol_target_weight": 0.35,
        "rationale": "单元测试依据摘要",
    }


def _regime(close: float) -> dict:
    return {
        "trend": "downtrend",
        "trend_strength": "strong",
        "volatility": "normal",
        "rsi_state": "neutral",
        "preferred_strategies": ["dual_momentum", "vol_target", "rsrs_timing"],
        "avoid_strategies": ["ma_5_20"],
        "snapshot": {
            "close": close,
            "ma5": close * 0.995,
            "ma20": close * 1.01,
            "ma60": close * 1.04,
            "rsi14": 42.0,
        },
    }


def test_generate_chart_talk_writes_pngs(tmp_path: Path) -> None:
    bars = _bars()
    close = bars[-1].close
    ct = generate_chart_talk(
        "sh510210",
        bars,
        regime=_regime(close),
        decision=_decision(),
        comparison=[
            {
                "strategy_id": "ma_20_60",
                "current_signal": "看跌",
                "current_weight": 0.0,
                "calmar": -0.1,
            },
            {
                "strategy_id": "atr_breakout",
                "current_signal": "看跌",
                "current_weight": 0.0,
                "calmar": -0.08,
            },
        ],
        out_dir=tmp_path,
    )
    price = Path(ct["price_path"])
    rsi_p = Path(ct["rsi_path"])
    assert price.is_file() and price.stat().st_size > 500
    assert rsi_p.is_file() and rsi_p.stat().st_size > 500
    assert ct["price_cid"] == "sh510210_price"
    assert ct["callouts"]
    assert any("L1" in t["batch"] for t in ct["tranches"])


def test_email_body_html_chart_talk_cid() -> None:
    decision = _decision("sh510300")
    ct = {
        "conclusion": "测试结论看图说话",
        "price_cid": "sh510300_price",
        "rsi_cid": "sh510300_rsi",
        "price_name": "sh510300_price.png",
        "rsi_name": "sh510300_rsi.png",
        "rsi": 44.5,
        "callouts": [
            {
                "mark": "①",
                "price": "0.95",
                "role": "支撑",
                "vs_close": "下方 2%",
                "meaning": "左侧",
            }
        ],
        "tranches": [
            {
                "batch": "L1 左侧底仓",
                "trigger": "支撑上方",
                "size": "约目标仓 25%",
                "meaning": "试探",
            }
        ],
    }
    html = email_body_html(
        [
            {
                "decision": decision,
                "regime": _regime(4.0),
                "comparison": [
                    {
                        "strategy_id": "dual_momentum",
                        "current_signal": "做多",
                        "current_weight": 1.0,
                        "calmar": 0.1,
                    }
                ],
                "chart_talk": ct,
            }
        ],
        "2026-07-31",
        provider_id="mock",
        image_mode="cid",
    )
    assert "看图说话" in html
    assert "图1" in html
    assert "分批介入" in html
    assert "cid:sh510300_price" in html
    assert "cid:sh510300_rsi" in html
    assert "测试结论看图说话" in html


def test_email_body_html_relative_paths() -> None:
    html = email_body_html(
        [
            {
                "decision": _decision("sh510300"),
                "regime": _regime(4.0),
                "comparison": [],
                "chart_talk": {
                    "price_cid": "sh510300_price",
                    "rsi_cid": "sh510300_rsi",
                    "price_name": "sh510300_price.png",
                    "rsi_name": "sh510300_rsi.png",
                    "callouts": [],
                    "tranches": [],
                    "conclusion": "x",
                },
            }
        ],
        "2026-07-31",
        provider_id="mock",
        image_mode="relative",
    )
    assert "charts/2026-07-31/sh510300_price.png" in html


def test_build_email_message_has_inline_png(tmp_path: Path) -> None:
    png = tmp_path / "sh510210_price.png"
    # minimal valid-ish PNG header bytes (matplotlib will make real ones;
    # for MIME we only need file bytes)
    png.write_bytes(
        b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    )
    html = "<html><body><img src='cid:sh510210_price'/></body></html>"
    msg = build_email_message(
        subject="test",
        mail_from="a@example.com",
        mail_to="b@example.com",
        body_text="plain",
        body_html=html,
        inline_images=[(png, "sh510210_price")],
    )
    assert isinstance(msg, EmailMessage)
    raw = msg.as_bytes()
    assert b"image/png" in raw
    assert b"sh510210_price" in raw
    assert getattr(msg, "_aistock_inline") == ["sh510210_price"]


def test_collect_inline_images(tmp_path: Path) -> None:
    p = tmp_path / "a_price.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    sections = [
        {
            "chart_talk": {
                "price_path": str(p),
                "price_cid": "a_price",
                "rsi_path": str(tmp_path / "missing.png"),
                "rsi_cid": "a_rsi",
            }
        }
    ]
    got = collect_inline_images(sections)
    assert len(got) == 1
    assert got[0][1] == "a_price"
