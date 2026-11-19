"""Static PNG + narrative meta for daily email「看图说话」."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.data.models import Bar
from app.research.indicators import rsi, sma

logger = logging.getLogger(__name__)

_LOOKBACK = 60


def _signal_of(row: dict[str, Any] | None) -> str:
    if not row:
        return "看跌"
    sig = str(row.get("current_signal") or "")
    if sig in {"做多", "看跌"}:
        return sig
    return "做多" if float(row.get("current_weight") or 0.0) > 0 else "看跌"


def _pct(level: float, close: float) -> float:
    if close == 0:
        return 0.0
    return (level - close) / close * 100.0


def _levels_from_bars(
    bars: list[Bar],
    snapshot: dict[str, Any],
) -> dict[str, float]:
    window = bars[-_LOOKBACK:] if len(bars) >= _LOOKBACK else bars
    close = float(snapshot.get("close") or window[-1].close)
    ma5 = float(snapshot.get("ma5") or close)
    ma20 = float(snapshot.get("ma20") or close)
    ma60 = float(snapshot.get("ma60") or close)

    support = min(b.low for b in window)
    # Bounce high: max high after the window low (or last 10 highs if low is last bar)
    low_i = min(range(len(window)), key=lambda i: window[i].low)
    after = window[low_i:]
    bounce = max(b.high for b in after) if after else window[-1].high

    return {
        "close": close,
        "ma5": ma5,
        "ma20": ma20,
        "ma60": ma60,
        "support": float(support),
        "bounce_high": float(bounce),
    }


def _build_callouts(levels: dict[str, float]) -> list[dict[str, str]]:
    c = levels["close"]
    rows = [
        ("①", levels["support"], "近期低点 / 硬支撑", "左侧底仓区；跌破则停止加仓"),
        ("②", levels["ma5"], "5日均线（短线成本）", "短线止跌台阶（L2）"),
        ("③", levels["bounce_high"], "近端反弹高点", "不过此线多为弱势反弹"),
        ("④", levels["ma20"], "20日均线（中期成本）", "右侧抬仓主门槛（R1）"),
        ("⑤", levels["ma60"], "60日均线（慢门禁）", "趋势修复区（R2）"),
        ("⑥", c, "现价", "当前站位"),
    ]
    out: list[dict[str, str]] = []
    for mark, price, role, meaning in rows:
        rel = _pct(price, c)
        if mark == "⑥":
            rel_txt = "—"
        elif rel > 0:
            rel_txt = f"上方 +{rel:.1f}%"
        else:
            rel_txt = f"下方 {abs(rel):.1f}%"
        out.append(
            {
                "mark": mark,
                "price": f"{price:.4f}".rstrip("0").rstrip("."),
                "role": role,
                "vs_close": rel_txt,
                "meaning": meaning,
            }
        )
    # Sort display top→bottom by price descending for sandwich table
    out_sorted = sorted(
        out,
        key=lambda r: float(r["price"]),
        reverse=True,
    )
    return out_sorted


def _build_tranches(
    levels: dict[str, float],
    decision: dict[str, Any],
    comparison: list[dict[str, Any]],
) -> list[dict[str, str]]:
    by_id = {str(r.get("strategy_id")): r for r in comparison}
    close = levels["close"]
    ma5, ma20, ma60 = levels["ma5"], levels["ma20"], levels["ma60"]
    support = levels["support"]
    bounce = levels["bounce_high"]
    target = float(decision.get("target_weight") or 0.0)
    tier = str(decision.get("tier") or "")
    target_pct = int(round(target * 100))

    ma20_sig = _signal_of(by_id.get("ma_20_60"))
    atr_sig = _signal_of(by_id.get("atr_breakout"))
    ma60_sig = _signal_of(by_id.get("ma_60_120"))
    adx_sig = _signal_of(by_id.get("adx_ma_trend"))

    def share(lo: float, hi: float) -> str:
        if target <= 0:
            return "暂不抬仓（目标仓≈0）"
        a, b = int(round(target_pct * lo)), int(round(target_pct * hi))
        return f"约目标仓 {int(lo*100)}%～{int(hi*100)}%（总资金约 {a}%～{b}%）"

    note = ""
    if tier == "防御" or target <= 0:
        note = "当前档位偏防御/目标仓≈0：以下台阶仅作观察条件，勿按风险开启打满。"

    l1_status = "可观察/试探" if close >= support else "支撑已失守"
    l2_status = "已满足" if close >= ma5 else "未满足"
    r1_ok = close >= ma20 or ma20_sig == "做多" or atr_sig == "做多"
    r1_status = "已满足" if r1_ok else "未满足"
    r2_ok = close >= ma60 and (ma60_sig == "做多" or adx_sig == "做多")
    r2_status = "已满足" if r2_ok else "未满足"

    rows = [
        {
            "batch": "L1 左侧底仓",
            "trigger": (
                f"价在支撑 {support:.4g} 上方、未有效跌破"
                f"（现价 {close:.4g} · {l1_status}）"
            ),
            "size": share(0.25, 0.35),
            "meaning": "试探性左侧；跌破支撑则停止加仓并降档",
        },
        {
            "batch": "L2 短线止跌",
            "trigger": (
                f"收盘站上 5日均线 {ma5:.4g}"
                f"（{l2_status}）"
            ),
            "size": share(0.15, 0.25) if target > 0 else "暂不抬仓（目标仓≈0）",
            "meaning": "确认短线止跌；累计仍建议 ≤ 目标仓一半",
        },
        {
            "batch": "R1 右侧抬仓",
            "trigger": (
                f"收盘站稳 20日均线 {ma20:.4g}（最好先过反弹高 {bounce:.4g}），"
                f"或 ma_20_60 / atr_breakout 翻做多（{r1_status}）"
            ),
            "size": (
                f"再抬至接近 vol_target≈{target_pct}%"
                if target > 0
                else "待目标仓打开后再抬"
            ),
            "meaning": "右侧机会窗口；此前不急于打满",
        },
        {
            "batch": "R2 趋势确认",
            "trigger": (
                f"站上 60日均线 {ma60:.4g}，且 ma_60_120 / adx_ma_trend "
                f"至少一道翻多（{r2_status}）"
            ),
            "size": "才讨论维持满研究仓或更高风险预算",
            "meaning": "慢门禁修复；否则仓位上限仍看 vol_target",
        },
    ]
    if note:
        rows.insert(
            0,
            {
                "batch": "说明",
                "trigger": note,
                "size": "—",
                "meaning": "买卖非对称：门禁翻空可快减，加仓等右侧台阶",
            },
        )
    return rows


def _conclusion(decision: dict[str, Any], regime: dict[str, Any]) -> str:
    tier = decision.get("tier")
    tw = float(decision.get("target_weight") or 0.0)
    trend = regime.get("trend")
    strength = regime.get("trend_strength")
    vol = regime.get("volatility")
    rationale = decision.get("rationale") or ""
    return (
        f"档位「{tier}」，研究目标仓位口径 ≈ {tw:.2f}。"
        f"市场状态：{trend}/{strength}，波动 {vol}。"
        f"{rationale}"
    )


def _configure_matplotlib() -> Any:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = [
        "Microsoft YaHei",
        "SimHei",
        "PingFang SC",
        "Noto Sans CJK SC",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False
    return plt


def _plot_price(
    plt: Any,
    bars: list[Bar],
    levels: dict[str, float],
    out_path: Path,
    title: str,
) -> None:
    window = bars[-_LOOKBACK:] if len(bars) >= _LOOKBACK else bars
    closes = [b.close for b in bars]
    ma5_all = sma(closes, 5)
    ma20_all = sma(closes, 20)
    start = len(bars) - len(window)
    xs = [b.trade_date.strftime("%m-%d") for b in window]
    y_close = [b.close for b in window]
    y_ma5 = [ma5_all[start + i] for i in range(len(window))]
    y_ma20 = [ma20_all[start + i] for i in range(len(window))]
    # Replace None with nan-friendly skip via list of floats
    def _num(v: float | None, fallback: float) -> float:
        return float(v) if v is not None else fallback

    y_ma5_f = [_num(v, y_close[i]) for i, v in enumerate(y_ma5)]
    y_ma20_f = [_num(v, y_close[i]) for i, v in enumerate(y_ma20)]

    fig, ax = plt.subplots(figsize=(7.2, 3.2), dpi=110)
    ax.plot(xs, y_close, color="#175cd3", linewidth=1.6, label="收盘价")
    ax.plot(xs, y_ma5_f, color="#b54708", linewidth=1.1, label="5日均线")
    ax.plot(xs, y_ma20_f, color="#667085", linewidth=1.1, label="20日均线")
    ref_specs = [
        (levels["close"], f"⑥现价 {levels['close']:.4g}", "#175cd3"),
        (levels["support"], f"①支撑 {levels['support']:.4g}", "#067647"),
        (levels["bounce_high"], f"③反弹高 {levels['bounce_high']:.4g}", "#b54708"),
        (levels["ma20"], f"④MA20 {levels['ma20']:.4g}", "#b54708"),
        (levels["ma60"], f"⑤MA60 {levels['ma60']:.4g}", "#b42318"),
    ]
    for val, lab, color in ref_specs:
        ax.axhline(val, color=color, linestyle="--", linewidth=0.8, alpha=0.85)
        ax.text(
            0.995,
            val,
            lab,
            transform=ax.get_yaxis_transform(),
            va="center",
            ha="right",
            fontsize=7,
            color=color,
            backgroundcolor="white",
        )
    step = max(1, len(xs) // 8)
    ax.set_xticks(range(0, len(xs), step))
    ax.set_xticklabels([xs[i] for i in range(0, len(xs), step)], fontsize=8)
    ax.set_title(title, fontsize=11)
    ax.set_ylabel("价格")
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(out_path, format="png")
    plt.close(fig)


def _plot_rsi(plt: Any, bars: list[Bar], out_path: Path, title: str) -> float | None:
    window = bars[-_LOOKBACK:] if len(bars) >= _LOOKBACK else bars
    closes = [b.close for b in bars]
    rsi_all = rsi(closes, 14)
    start = len(bars) - len(window)
    xs = [b.trade_date.strftime("%m-%d") for b in window]
    ys: list[float] = []
    last_r: float | None = None
    for i in range(len(window)):
        v = rsi_all[start + i]
        if v is None:
            ys.append(float("nan"))
        else:
            ys.append(float(v))
            last_r = float(v)

    fig, ax = plt.subplots(figsize=(7.2, 2.4), dpi=110)
    ax.plot(xs, ys, color="#175cd3", linewidth=1.4, label="RSI14")
    ax.axhline(70, color="#b42318", linestyle="--", linewidth=0.9, label="超买 70")
    ax.axhline(30, color="#067647", linestyle="--", linewidth=0.9, label="超卖 30")
    ax.axhline(50, color="#98a2b3", linestyle=":", linewidth=0.8)
    if last_r is not None:
        ax.axhline(last_r, color="#175cd3", linestyle=":", linewidth=0.8, alpha=0.7)
    step = max(1, len(xs) // 8)
    ax.set_xticks(range(0, len(xs), step))
    ax.set_xticklabels([xs[i] for i in range(0, len(xs), step)], fontsize=8)
    ax.set_ylim(15, 85)
    ax.set_title(title, fontsize=11)
    ax.set_ylabel("RSI")
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(out_path, format="png")
    plt.close(fig)
    return last_r


def generate_chart_talk(
    code: str,
    bars: list[Bar],
    *,
    regime: dict[str, Any],
    decision: dict[str, Any],
    comparison: list[dict[str, Any]],
    out_dir: Path,
) -> dict[str, Any]:
    """
    Write price/RSI PNGs and return narrative meta for email HTML.

    On failure raises; caller should catch and continue without charts.
    """
    code = code.lower().strip()
    if len(bars) < 30:
        raise ValueError(f"need >= 30 bars for chart_talk, got {len(bars)}")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    snapshot = dict(regime.get("snapshot") or {})
    if not snapshot:
        snapshot = {
            "close": bars[-1].close,
            "ma5": bars[-1].close,
            "ma20": bars[-1].close,
            "ma60": bars[-1].close,
        }
    levels = _levels_from_bars(bars, snapshot)
    callouts = _build_callouts(levels)
    tranches = _build_tranches(levels, decision, comparison)
    conclusion = _conclusion(decision, regime)

    price_name = f"{code}_price.png"
    rsi_name = f"{code}_rsi.png"
    price_path = out_dir / price_name
    rsi_path = out_dir / rsi_name
    price_cid = f"{code}_price"
    rsi_cid = f"{code}_rsi"

    plt = _configure_matplotlib()
    label = str(decision.get("label") or code)
    _plot_price(
        plt,
        bars,
        levels,
        price_path,
        f"图1 · 价格地势 · {label}",
    )
    rsi_now = _plot_rsi(
        plt,
        bars,
        rsi_path,
        f"图2 · 强弱温度 RSI14 · {label}",
    )

    if not price_path.is_file() or price_path.stat().st_size < 100:
        raise RuntimeError(f"price chart missing/empty: {price_path}")
    if not rsi_path.is_file() or rsi_path.stat().st_size < 100:
        raise RuntimeError(f"rsi chart missing/empty: {rsi_path}")

    return {
        "code": code,
        "conclusion": conclusion,
        "levels": levels,
        "callouts": callouts,
        "tranches": tranches,
        "rsi": rsi_now,
        "price_path": str(price_path),
        "rsi_path": str(rsi_path),
        "price_name": price_name,
        "rsi_name": rsi_name,
        "price_cid": price_cid,
        "rsi_cid": rsi_cid,
        "chart_paths": [str(price_path), str(rsi_path)],
    }


def collect_inline_images(
    sections: list[dict[str, Any]],
) -> list[tuple[Path, str]]:
    """Gather (path, cid) pairs for SMTP multipart/related."""
    out: list[tuple[Path, str]] = []
    for sec in sections:
        ct = sec.get("chart_talk") or {}
        for key_path, key_cid in (
            ("price_path", "price_cid"),
            ("rsi_path", "rsi_cid"),
        ):
            p = ct.get(key_path)
            cid = ct.get(key_cid)
            if p and cid and Path(p).is_file():
                out.append((Path(p), str(cid)))
    return out
