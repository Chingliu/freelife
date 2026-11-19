from __future__ import annotations

from typing import Any

from app.data.models import Bar
from app.research.backtest.evidence import grade_decision, grade_strategy_row
from app.research.backtest.horizons import assign_lifecycles, enrich_result_horizons
from app.research.backtest.splits import holdout_last_years, oos_metrics_for_result, oos_pass
from app.research.backtest.types import BacktestResult
from app.research.indicators import compute_indicator_snapshot


def classify_market_regime(snapshot: dict[str, float | None]) -> dict[str, Any]:
    ma5 = snapshot.get("ma5")
    ma20 = snapshot.get("ma20")
    ma60 = snapshot.get("ma60")
    adx = snapshot.get("adx14")
    vol = snapshot.get("vol20")
    rsi = snapshot.get("rsi14")

    trend = "unknown"
    evidence: list[str] = []
    if ma5 is not None and ma20 is not None and ma60 is not None:
        if ma5 > ma20 > ma60:
            trend = "uptrend"
            evidence.append(f"均线多头排列 ma5={ma5:.4f}>ma20={ma20:.4f}>ma60={ma60:.4f}")
        elif ma5 < ma20 < ma60:
            trend = "downtrend"
            evidence.append(f"均线空头排列 ma5={ma5:.4f}<ma20={ma20:.4f}<ma60={ma60:.4f}")
        else:
            trend = "sideways"
            evidence.append(
                f"均线纠结 ma5={ma5:.4f} ma20={ma20:.4f} ma60={ma60:.4f}（非严格多/空头）"
            )
    else:
        evidence.append("均线不足，趋势 unknown")

    strength = "weak"
    if adx is not None:
        if adx >= 30:
            strength = "strong"
        elif adx >= 20:
            strength = "moderate"
        evidence.append(f"ADX14={adx:.1f} → 强度 {strength}")

    vol_state = "normal"
    if vol is not None:
        if vol >= 0.30:
            vol_state = "high"
        elif vol <= 0.12:
            vol_state = "low"
        evidence.append(f"vol20={vol:.2%} → 波动 {vol_state}")

    rsi_state = "neutral"
    if rsi is not None:
        if rsi >= 70:
            rsi_state = "overbought"
        elif rsi <= 30:
            rsi_state = "oversold"
        evidence.append(f"RSI14={rsi:.1f} → {rsi_state}")

    preferred = []
    avoid = []
    if trend == "uptrend" and strength in {"moderate", "strong"}:
        preferred.extend(["ma_20_60", "ma_60_120", "adx_ma_trend", "dual_momentum"])
        avoid.extend(
            [
                "rsi_reversion",
                "bollinger_reversion",
                "rsi_divergence",
                "macd_divergence",
            ]
        )
    elif trend == "downtrend":
        preferred.extend(["dual_momentum", "vol_target", "rsrs_timing"])
        avoid.extend(["ma_5_20", "macd_cross", "kdj_cross"])
    else:
        preferred.extend(
            [
                "vol_target",
                "rsi_reversion",
                "bollinger_reversion",
                "rsi_divergence",
                "macd_divergence",
                "rsrs_timing",
            ]
        )
        avoid.extend(["ma_5_20", "atr_breakout"])

    if vol_state == "high":
        preferred = ["vol_target"] + [p for p in preferred if p != "vol_target"]
        avoid.append("ma_5_20")

    # Soft candidate set: preferred first; avoid excluded from candidates
    avoid_set = list(dict.fromkeys(avoid))
    preferred = list(dict.fromkeys(preferred))
    candidate_set = [p for p in preferred if p not in avoid_set]

    return {
        "trend": trend,
        "trend_strength": strength,
        "volatility": vol_state,
        "rsi_state": rsi_state,
        "preferred_strategies": preferred,
        "avoid_strategies": avoid_set,
        "candidate_set": candidate_set,
        "evidence": evidence,
        "snapshot": snapshot,
    }


def rank_results(
    results: list[BacktestResult],
    *,
    key: str = "calmar",
) -> list[BacktestResult]:
    def score(r: BacktestResult) -> float:
        m = r.metrics
        if key == "sharpe":
            return m.sharpe
        if key == "annual_return":
            return m.annual_return
        if key == "max_drawdown":
            return -m.max_drawdown
        return m.calmar

    return sorted(results, key=score, reverse=True)


def analyze_strategy_failure(result: BacktestResult) -> list[str]:
    m = result.metrics
    reasons: list[str] = []
    if m.trades < 5:
        reasons.append("交易次数过少，样本不足，结果不稳定")
    if m.max_drawdown > 0.25:
        reasons.append(
            f"最大回撤 {m.max_drawdown:.1%} 过高，策略在趋势反转或急跌中风控不足"
        )
    if m.sharpe < 0.3:
        reasons.append("夏普偏低，收益相对波动缺乏吸引力")
    if m.annual_return < 0.03 and m.max_drawdown > 0.15:
        reasons.append("收益薄且回撤大，风险收益比不佳")
    if m.time_in_market > 0.9 and m.max_drawdown > 0.2:
        reasons.append("几乎满仓持有，接近买入持有，择时贡献有限")
    if m.time_in_market < 0.15 and m.trades > 0:
        reasons.append("持仓时间过短，可能过度空仓错过趋势段")
    if m.win_rate < 0.4 and m.trades >= 10:
        reasons.append("胜率偏低，需依赖盈亏比；对宽基短线信号可能不适合")
    if result.strategy_id.startswith("ma_5_") and m.max_drawdown > 0.3:
        reasons.append("短周期均线在指数上噪声大，易在震荡市反复止损")
    if not reasons:
        reasons.append("未发现显著失效特征；可做参数敏感性与样本外验证")
    return reasons


def suggest_param_tweaks(result: BacktestResult) -> list[str]:
    sid = result.strategy_id
    m = result.metrics
    tips: list[str] = []
    if sid.startswith("ma_"):
        if m.max_drawdown > 0.25:
            tips.append("尝试更长均线（如 20/60、60/120）降低交易频率")
        if m.trades > 80:
            tips.append("交叉过于频繁，可加 ADX>20 过滤或改周线确认")
    if sid == "dual_momentum":
        tips.append("可测试 lookback=120/189/252，threshold=0~0.05")
        if m.time_in_market < 0.4:
            tips.append("空仓偏多时可降低 threshold 或缩短 lookback")
    if sid == "rsi_reversion":
        tips.append("宽基可试 oversold=25/35，overbought=65/75")
    if sid in {"rsi_divergence", "macd_divergence"}:
        tips.append("枢轴 left/right 可试 3~7；max_hold 可试 40/60/90")
        if m.trades < 5:
            tips.append("信号偏少时可略降 min_bars 或 min_osc_delta / min_osc_rel")
    if sid == "vol_target":
        tips.append("目标波动可试 8%/12%/15%，观察 Calmar 变化")
    if sid == "rsrs_timing":
        tips.append("buy_th 可试 0.5~1.0，sell_th 可试 -0.5~-1.0")
    if sid == "adx_ma_trend":
        tips.append("adx_min 可试 15/20/25；趋势市提高阈值减少假突破")
    if not tips:
        tips.append("做网格搜索核心参数，并用最近 1 年做样本外验证")
    return tips


def _decision_score(row: dict[str, Any]) -> float:
    """Prefer OOS test Calmar; demoted strategies sort last."""
    if str(row.get("lifecycle") or "") == "demoted":
        return float("-inf")
    oos = row.get("oos") or {}
    test = oos.get("test") or {}
    if test.get("status") == "ok" and test.get("calmar") is not None:
        return float(test["calmar"])
    return float(row.get("calmar") or 0.0)


def build_comparison_table(
    results: list[BacktestResult],
    *,
    bars: list[Bar] | None = None,
    regime: dict[str, Any] | None = None,
    cross_etf_by_strategy: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    regime = regime or {}
    preferred = set(regime.get("preferred_strategies") or [])
    avoid = set(regime.get("avoid_strategies") or [])
    candidates = set(regime.get("candidate_set") or preferred)
    cross_etf_by_strategy = cross_etf_by_strategy or {}

    bounds = holdout_last_years(bars, n=1.0) if bars else None

    rows: list[dict[str, Any]] = []
    for r in results:
        m = r.metrics
        horizons = enrich_result_horizons(r)
        oos: dict[str, Any] = {}
        if bounds is not None and r.equity_curve:
            dates = [d for d, _ in r.equity_curve]
            equity = [e for _, e in r.equity_curve]
            oos = oos_metrics_for_result(
                equity, dates, list(r.positions), list(r.trades), bounds
            )
        cross = cross_etf_by_strategy.get(r.strategy_id) or {}
        if cross:
            cross = {**cross, "pass": bool(cross.get("pass"))}

        sid = r.strategy_id
        if sid in avoid:
            regime_status = "avoided"
        elif sid in candidates or sid in preferred:
            regime_status = "candidate"
        else:
            regime_status = "neutral"

        rows.append(
            {
                "strategy_id": sid,
                "current_signal": r.current_signal,
                "current_weight": round(float(r.current_weight), 4),
                "annual_return": round(m.annual_return, 4),
                "max_drawdown": round(m.max_drawdown, 4),
                "sharpe": round(m.sharpe, 3),
                "calmar": round(m.calmar, 3),
                "win_rate": round(m.win_rate, 3),
                "trades": m.trades,
                "time_in_market": round(m.time_in_market, 3),
                "failure_notes": analyze_strategy_failure(r)[:2],
                "param_suggestions": suggest_param_tweaks(r)[:2],
                **horizons,
                "oos": oos,
                "oos_pass": oos_pass(oos.get("test") or {}) if oos else False,
                "cross_etf": cross or None,
                "cross_etf_score": cross.get("score") if cross else None,
                "regime_status": regime_status,
                "lifecycle": "active",
            }
        )

    assign_lifecycles(rows)

    # Decision ranking: OOS calmar, demoted last
    ranked = sorted(rows, key=_decision_score, reverse=True)
    for i, row in enumerate(ranked, 1):
        row["rank"] = i

    # Regime-candidate rank (soft filter — full table still kept)
    cand_rows = [
        r
        for r in ranked
        if r.get("regime_status") == "candidate"
        and str(r.get("lifecycle")) != "demoted"
    ]
    cand_sorted = sorted(
        cand_rows,
        key=lambda r: float(r.get("calmar") or 0.0),
        reverse=True,
    )
    cand_rank = {r["strategy_id"]: i for i, r in enumerate(cand_sorted, 1)}
    for row in ranked:
        row["rank_in_regime"] = cand_rank.get(row["strategy_id"])
        # Combined display status
        if row.get("regime_status") == "avoided":
            row["status"] = "avoided"
        elif row.get("lifecycle") == "demoted":
            row["status"] = "demoted"
        elif row.get("lifecycle") == "watch":
            row["status"] = "watch"
        else:
            row["status"] = "active"
        row["evidence_grade"] = grade_strategy_row(row)

    return ranked


def prompt_compare_strategies(payload_json: str) -> str:
    return (
        "你是量化策略研究员。以下是同一 ETF 上多策略回测结果（JSON）。"
        "请比较优劣，指出失效原因，给出参数优化建议，并明确当前是否适合开仓。"
        "只基于给定数据，不要编造行情。注意 evidence_grade 与 oos/test 样本外指标。\n"
        f"{payload_json}"
    )


def prompt_daily_research(payload_json: str) -> str:
    return (
        "请根据下列「市场状态 + 多策略回测摘要」写一份中文日报："
        "1) 市场状态判断 2) 今日更适配的策略 3) 应回避的策略 "
        "4) 风险点 5) 证据等级(A/B/C/D)与置信度。禁止空泛推荐。"
        "C/D 级只能写实验性观察。\n"
        f"{payload_json}"
    )


def render_markdown_report(
    *,
    code: str,
    as_of: str,
    provider_id: str,
    regime: dict[str, Any],
    comparison: list[dict[str, Any]],
) -> str:
    from app.research.ai.playbook import render_symbol_playbook_markdown

    return render_symbol_playbook_markdown(
        code=code,
        as_of=as_of,
        provider_id=provider_id,
        regime=regime,
        comparison=comparison,
    )


def analyze_bars_and_results(
    code: str,
    bars: list[Bar],
    results: list[BacktestResult],
    *,
    provider_id: str,
    as_of: str,
    cross_etf_by_strategy: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    from app.research.ai.playbook import decide_position

    snap = compute_indicator_snapshot(bars)
    regime = classify_market_regime(snap)
    comparison = build_comparison_table(
        results,
        bars=bars,
        regime=regime,
        cross_etf_by_strategy=cross_etf_by_strategy,
    )
    decision = decide_position(code, regime, comparison)
    decision["evidence_grade"] = grade_decision(
        comparison, preferred_ids=list(regime.get("preferred_strategies") or [])
    )
    report_md = render_markdown_report(
        code=code,
        as_of=as_of,
        provider_id=provider_id,
        regime=regime,
        comparison=comparison,
    )
    payload = {
        "code": code,
        "as_of": as_of,
        "provider_id": provider_id,
        "regime": regime,
        "comparison": comparison,
        "decision": decision,
    }
    return {
        "code": code,
        "as_of": as_of,
        "provider_id": provider_id,
        "regime": regime,
        "comparison": comparison,
        "decision": decision,
        "report_markdown": report_md,
        "llm_prompt_compare": prompt_compare_strategies(str(payload)),
        "llm_prompt_daily": prompt_daily_research(str(payload)),
        "results": [r.to_dict() for r in results],
    }
