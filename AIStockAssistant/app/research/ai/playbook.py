from __future__ import annotations

from typing import Any

from app.research.backtest.evidence import grade_decision
from app.research.data.etf_universe import etf_label, etf_name
from app.research.strategies import create_strategy

# Roles for layered decision (not equal votes).
_GATE_IDS = frozenset({"dual_momentum", "ma_60_120", "adx_ma_trend"})
_TIMING_IDS = frozenset({"rsrs_timing", "macd_cross", "atr_breakout"})
_OSC_IDS = frozenset(
    {
        "rsi_reversion",
        "bollinger_reversion",
        "kdj_cross",
        "rsi_divergence",
        "macd_divergence",
    }
)


def strategy_cn_name(strategy_id: str) -> str:
    try:
        return create_strategy(strategy_id).name
    except KeyError:
        return strategy_id


def format_strategy_id(strategy_id: str) -> str:
    name = strategy_cn_name(strategy_id)
    if name == strategy_id:
        return strategy_id
    return f"{strategy_id}（{name}）"


def _signal_of(row: dict[str, Any]) -> str:
    sig = str(row.get("current_signal") or "")
    if sig in {"做多", "看跌"}:
        return sig
    w = float(row.get("current_weight") or 0.0)
    return "做多" if w > 0 else "看跌"


def _row_by_id(comparison: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(r["strategy_id"]): r for r in comparison}


def decide_position(
    code: str,
    regime: dict[str, Any],
    comparison: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Derive one-symbol playbook tier from regime + ranked comparison.
    Follows workspace etf-research-platform layering (not full-table majority).
    Phase-2: gate/timing/osc roles enforced; demoted excluded from Top3;
    OOS/test + evidence grade gate 风险开启.
    """
    by_id = _row_by_id(comparison)
    all_long = sum(1 for r in comparison if _signal_of(r) == "做多")
    all_flat = sum(1 for r in comparison if _signal_of(r) == "看跌")

    preferred = list(regime.get("preferred_strategies") or [])
    avoid = set(regime.get("avoid_strategies") or [])
    trend = str(regime.get("trend") or "unknown")
    strength = str(regime.get("trend_strength") or "weak")
    volatility = str(regime.get("volatility") or "normal")

    pref_rows: list[dict[str, Any]] = []
    pref_long = 0
    for sid in preferred:
        row = by_id.get(sid)
        if not row:
            continue
        sig = _signal_of(row)
        pref_rows.append(
            {
                "strategy_id": sid,
                "label": format_strategy_id(sid),
                "current_signal": sig,
                "current_weight": float(row.get("current_weight") or 0.0),
                "in_avoid": sid in avoid,
                "lifecycle": row.get("lifecycle"),
                "evidence_grade": row.get("evidence_grade"),
            }
        )
        if sig == "做多" and sid not in avoid:
            pref_long += 1
    pref_n = len(pref_rows)
    pref_flat = pref_n - pref_long

    # Active (non-demoted) rows for Calmar#1 / Top3
    active = [
        r
        for r in comparison
        if str(r.get("lifecycle") or "active") != "demoted"
        and str(r.get("status") or "") != "demoted"
    ]
    if not active:
        active = list(comparison)

    calmar1 = active[0] if active else (comparison[0] if comparison else None)
    calmar1_id = str(calmar1["strategy_id"]) if calmar1 else ""
    calmar1_sig = _signal_of(calmar1) if calmar1 else "看跌"
    veto = bool(calmar1 and calmar1_sig == "看跌" and trend == "downtrend")

    top3 = active[:3]
    top3_long = sum(1 for r in top3 if _signal_of(r) == "做多")

    # Role votes
    def _role_long(ids: frozenset[str], *, osc_only_sideways: bool = False) -> dict[str, Any]:
        long_n = 0
        flat_n = 0
        used = 0
        for sid in ids:
            if osc_only_sideways and trend != "sideways":
                continue
            if osc_only_sideways and sid not in preferred:
                continue
            row = by_id.get(sid)
            if not row:
                continue
            if sid in avoid and osc_only_sideways:
                continue
            used += 1
            if _signal_of(row) == "做多":
                long_n += 1
            else:
                flat_n += 1
        return {"long": long_n, "flat": flat_n, "n": used}

    gate_votes = _role_long(_GATE_IDS)
    timing_votes = _role_long(_TIMING_IDS)
    osc_votes = _role_long(_OSC_IDS, osc_only_sideways=True)
    role_votes = {
        "gate": gate_votes,
        "timing": timing_votes,
        "osc": osc_votes,
    }

    gate_majority_flat = gate_votes["n"] > 0 and gate_votes["flat"] > gate_votes["long"]
    gate_veto = gate_majority_flat

    vt = by_id.get("vol_target")
    vt_w = float(vt.get("current_weight") or 0.0) if vt else 0.0

    pref_majority_flat = pref_n > 0 and pref_flat > pref_long
    pref_majority_long = pref_n > 0 and pref_long > pref_flat
    pref_split = pref_n > 0 and pref_long == pref_flat

    hard_down_high = trend == "downtrend" and strength == "strong" and volatility == "high"

    # OOS / grade gate for 风险开启
    calmar1_oos_pass = bool(calmar1 and calmar1.get("oos_pass"))
    decision_grade_order = {"A": 0, "B": 1, "C": 2, "D": 3}
    evid = grade_decision(comparison, preferred_ids=preferred)
    grade_ok_for_risk = decision_grade_order.get(evid, 3) <= 1  # A or B
    oos_blocks_risk = not (calmar1_oos_pass or grade_ok_for_risk)

    if pref_majority_flat or veto or gate_veto:
        tier = "防御"
        target = 0.0
        if gate_veto and not pref_majority_flat:
            tier = "观望"
            target = 0.0
        if veto and not pref_majority_flat and vt_w > 0:
            target = 0.0
    elif pref_split or (pref_majority_long and top3_long < 2):
        if pref_majority_long and top3_long == 1 and not veto and not gate_veto:
            tier = "试探"
            target = min(0.35, vt_w) if vt_w > 0 else 0.30
            if volatility == "high" or strength == "weak":
                target = min(target, 0.30)
        else:
            tier = "观望"
            target = 0.0
    elif (
        pref_majority_long
        and top3_long >= 2
        and not veto
        and not gate_veto
        and not hard_down_high
    ):
        if oos_blocks_risk:
            tier = "试探"
            target = min(0.35, vt_w) if vt_w > 0 else 0.30
        else:
            tier = "风险开启"
            target = vt_w if vt_w > 0 else 0.5
            if trend == "downtrend" and volatility == "high":
                target = min(target * 0.5, 0.25)
                tier = "试探"
    elif pref_majority_long:
        tier = "试探"
        target = min(0.35, vt_w) if vt_w > 0 else 0.30
    else:
        tier = "观望"
        target = 0.0

    if volatility == "high" and trend == "downtrend" and tier in {"试探", "风险开启"}:
        target = min(target, 0.25)
        if tier == "风险开启":
            tier = "试探"

    # Timing: when gate allows and preferred long, timing majority flat → cap at 试探
    if (
        not gate_veto
        and pref_majority_long
        and timing_votes["n"] > 0
        and timing_votes["flat"] > timing_votes["long"]
        and tier == "风险开启"
    ):
        tier = "试探"
        target = min(target, 0.35)

    rationale = (
        f"偏好集做多{pref_long}/{pref_n}；门禁做多{gate_votes['long']}/{gate_votes['n']}"
        f"{'（门禁否决）' if gate_veto else ''}；"
        f"Calmar#1 {format_strategy_id(calmar1_id) or 'n/a'}"
        f"={calmar1_sig}{'（否决加仓）' if veto else ''}；"
        f"Top3共振做多{top3_long}/3；vol_target={vt_w:.2f}；"
        f"证据等级={evid}；OOS#1={'pass' if calmar1_oos_pass else 'fail'}；"
        f"趋势={trend}/{strength} 波动={volatility} → {tier} 目标仓位≈{target:.2f}"
    )

    return {
        "code": code.lower(),
        "name": etf_name(code),
        "label": etf_label(code),
        "full_table_votes": {"做多": all_long, "看跌": all_flat},
        "preferred": pref_rows,
        "preferred_long": pref_long,
        "preferred_n": pref_n,
        "calmar1": {
            "strategy_id": calmar1_id,
            "label": format_strategy_id(calmar1_id) if calmar1_id else "",
            "current_signal": calmar1_sig,
            "veto": veto,
            "oos_pass": calmar1_oos_pass,
            "lifecycle": (calmar1 or {}).get("lifecycle") if calmar1 else None,
        },
        "top3_long": top3_long,
        "vol_target_weight": vt_w,
        "tier": tier,
        "target_weight": round(float(target), 4),
        "rationale": rationale,
        "role_votes": role_votes,
        "gate_veto": gate_veto,
        "evidence_grade": evid,
        "gate_ids": sorted(_GATE_IDS),
        "timing_ids": sorted(_TIMING_IDS),
        "osc_ids": sorted(_OSC_IDS),
    }


def render_symbol_playbook_markdown(
    *,
    code: str,
    as_of: str,
    provider_id: str,
    regime: dict[str, Any],
    comparison: list[dict[str, Any]],
    decision: dict[str, Any] | None = None,
) -> str:
    decision = decision or decide_position(code, regime, comparison)
    preferred_labels = [
        format_strategy_id(s) for s in (regime.get("preferred_strategies") or [])
    ]
    avoid_labels = [
        format_strategy_id(s) for s in (regime.get("avoid_strategies") or [])
    ]

    lines = [
        f"## {decision['label']}",
        f"provider={provider_id} as_of={as_of}",
        "",
        "### 市场状态",
        f"- 趋势: **{regime.get('trend')}** / 强度: {regime.get('trend_strength')}",
        f"- 波动: {regime.get('volatility')} / RSI: {regime.get('rsi_state')}",
        f"- 更适配: {', '.join(preferred_labels) or '—'}",
        f"- 宜回避: {', '.join(avoid_labels) or '—'}",
        f"- 候选集: {', '.join(format_strategy_id(s) for s in (regime.get('candidate_set') or [])) or '—'}",
    ]
    if regime.get("evidence"):
        lines.append(f"- 判定依据: {'; '.join(regime['evidence'])}")
    lines.extend(
        [
            "",
            "### 全策略当前信号表",
            "| Strategy | Signal | Weight | Ann | MDD | Sharpe | Calmar | "
            "OOS_Calmar | Life | Grade | Trades |",
            "|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|",
        ]
    )
    for row in comparison:
        sid = str(row["strategy_id"])
        oos_c = ((row.get("oos") or {}).get("test") or {}).get("calmar")
        oos_s = f"{oos_c:.2f}" if oos_c is not None else "—"
        lines.append(
            "| {label} | {current_signal} | {current_weight:.2f} | "
            "{annual_return:.2%} | {max_drawdown:.2%} | "
            "{sharpe:.2f} | {calmar:.2f} | {oos} | {life} | {grade} | {trades} |".format(
                label=format_strategy_id(sid),
                current_signal=row["current_signal"],
                current_weight=row["current_weight"],
                annual_return=row["annual_return"],
                max_drawdown=row["max_drawdown"],
                sharpe=row["sharpe"],
                calmar=row["calmar"],
                oos=oos_s,
                life=row.get("lifecycle") or row.get("status") or "—",
                grade=row.get("evidence_grade") or "—",
                trades=row["trades"],
            )
        )

    pref_cells = "; ".join(
        f"{p['label']}={p['current_signal']}({p['current_weight']:.2f})"
        for p in decision["preferred"]
    ) or "—"
    c1 = decision["calmar1"]
    role = decision.get("role_votes") or {}
    gate = role.get("gate") or {}
    lines.extend(
        [
            "",
            "### 仓位决策表（本标的）",
            "| 字段 | 值 |",
            "|---|---|",
            f"| 标的 | {decision['label']} |",
            f"| 全表票数 | 做多 {decision['full_table_votes']['做多']} / "
            f"看跌 {decision['full_table_votes']['看跌']}（对照，非主依据） |",
            f"| 偏好集 | {pref_cells}；做多 {decision['preferred_long']}/"
            f"{decision['preferred_n']} |",
            f"| 门禁票 | 做多 {gate.get('long', 0)}/{gate.get('n', 0)}"
            f"{'；门禁否决' if decision.get('gate_veto') else ''} |",
            f"| Calmar#1 | {c1['label']}={c1['current_signal']}；"
            f"{'触发否决' if c1['veto'] else '未否决'}；"
            f"OOS={'pass' if c1.get('oos_pass') else 'fail'} |",
            f"| Top3 共振 | 做多 {decision['top3_long']}/3 |",
            f"| 证据等级 | **{decision.get('evidence_grade') or '—'}** |",
            f"| 档位 | **{decision['tier']}** |",
            f"| 建议目标仓位 | **{decision['target_weight']:.2f}**（研究观察口径） |",
            f"| 依据摘要 | {decision['rationale']} |",
            "",
            "### 策略对比要点",
        ]
    )
    if comparison:
        best = comparison[0]
        lines.extend(
            [
                f"- Calmar 第1: `{format_strategy_id(str(best['strategy_id']))}` "
                f"年化 {best['annual_return']:.2%} / MDD {best['max_drawdown']:.2%} / "
                f"Sharpe {best['sharpe']:.2f} / Calmar {best['calmar']:.2f}",
                f"- 失效观察: {'; '.join(best.get('failure_notes', []))}",
                f"- 参数建议: {'; '.join(best.get('param_suggestions', []))}",
            ]
        )
    lines.extend(
        [
            "",
            "### 风险点",
            "- 信号按收盘确认、次日开盘成交假设；隔夜缺口与流动性未建模",
            "- avoid 列表内做多不得作为开仓依据；全表多数票不作买卖开关",
            "- 研究观察仓位非正式投资建议 / 非自动交易指令",
            "",
            f"> provider_id={provider_id} as_of={as_of}；以上为研究平台自动分析。",
        ]
    )
    return "\n".join(lines)


def render_daily_playbook(
    *,
    provider_id: str,
    as_of: str | None,
    sections: list[dict[str, Any]],
    skipped: list[dict[str, str]] | None = None,
) -> str:
    skipped = skipped or []
    lines = [
        "# 每日 ETF 后市操作指南",
        f"provider={provider_id} as_of={as_of}",
        "",
        "> 研究观察口径，非正式投资建议。",
        "",
        "## 总览",
        "| 标的 | 档位 | 建议目标仓位 | 趋势 | 偏好做多 | Top3共振 |",
        "|---|---|---:|---|---:|---:|",
    ]
    for sec in sections:
        d = sec["decision"]
        r = sec["regime"]
        lines.append(
            f"| {d['label']} | {d['tier']} | {d['target_weight']:.2f} | "
            f"{r.get('trend')} | {d['preferred_long']}/{d['preferred_n']} | "
            f"{d['top3_long']}/3 |"
        )
    if skipped:
        lines.append("")
        lines.append("### 数据缺失 / 跳过")
        for s in skipped:
            lines.append(f"- {s.get('code')}: {s.get('reason')}")

    lines.append("")
    lines.append("---")
    lines.append("")
    for sec in sections:
        lines.append(sec["report_markdown"])
        lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def email_summary_text(sections: list[dict[str, Any]], as_of: str | None) -> str:
    rows = [
        f"ETF看图说话 as_of={as_of}",
        "",
        "标的 | 档位 | 建议仓位",
        "---- | ---- | --------",
    ]
    for sec in sections:
        d = sec["decision"]
        rows.append(
            f"{d['label']} | {d['tier']} | {d['target_weight']:.2f}"
        )
    rows.extend(
        [
            "",
            "以上为研究观察，非正式投资建议。手机请看邮件正文 HTML（含图表）；"
            "附件含 .html / .md / 图表 PNG。",
        ]
    )
    return "\n".join(rows)


def _esc(s: Any) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _tier_color(tier: str) -> str:
    return {
        "防御": "#b42318",
        "观望": "#b54708",
        "试探": "#175cd3",
        "风险开启": "#067647",
    }.get(tier, "#344054")


def _img_src(
    ct: dict[str, Any],
    *,
    kind: str,
    image_mode: str,
    as_of: str | None,
) -> str | None:
    """kind: price | rsi. image_mode: cid | relative."""
    if kind == "price":
        cid = ct.get("price_cid")
        name = ct.get("price_name")
        path = ct.get("price_path")
    else:
        cid = ct.get("rsi_cid")
        name = ct.get("rsi_name")
        path = ct.get("rsi_path")
    if image_mode == "cid":
        return f"cid:{cid}" if cid else None
    if name and as_of:
        day = str(as_of)[:10]
        return f"charts/{day}/{name}"
    return path


def _position_bar_html(target_weight: float) -> str:
    pct = max(0, min(100, int(round(float(target_weight) * 100))))
    cash = 100 - pct
    return (
        "<div style='margin:10px 0 6px'>"
        f"<div style='font-size:13px;color:#475467;margin-bottom:4px'>"
        f"图4 · 仓位怎么分：目标研究仓 ≈ {pct}% · 现金缓冲 ≈ {cash}%</div>"
        "<div style='width:100%;height:18px;background:#e4e7ec;border-radius:6px;"
        "overflow:hidden;display:flex'>"
        f"<div style='width:{pct}%;background:#f79009;height:100%'></div>"
        f"<div style='width:{cash}%;background:#d0d5dd;height:100%'></div>"
        "</div></div>"
    )


def email_body_html(
    sections: list[dict[str, Any]],
    as_of: str | None,
    *,
    provider_id: str = "",
    skipped: list[dict[str, str]] | None = None,
    image_mode: str = "relative",
) -> str:
    """Mobile-friendly HTML「看图说话」for QQ Mail / HarmonyOS."""
    skipped = skipped or []
    image_mode = "cid" if image_mode == "cid" else "relative"
    rows = []
    for sec in sections:
        d = sec["decision"]
        r = sec["regime"]
        color = _tier_color(str(d["tier"]))
        rows.append(
            "<tr>"
            f"<td style='padding:8px;border:1px solid #e4e7ec'>{_esc(d['label'])}</td>"
            f"<td style='padding:8px;border:1px solid #e4e7ec;color:{color};font-weight:700'>"
            f"{_esc(d['tier'])}</td>"
            f"<td style='padding:8px;border:1px solid #e4e7ec;text-align:right'>"
            f"{float(d['target_weight']):.2f}</td>"
            f"<td style='padding:8px;border:1px solid #e4e7ec'>{_esc(r.get('trend'))}</td>"
            f"<td style='padding:8px;border:1px solid #e4e7ec;text-align:right'>"
            f"{d['preferred_long']}/{d['preferred_n']}</td>"
            f"<td style='padding:8px;border:1px solid #e4e7ec;text-align:right'>"
            f"{d['top3_long']}/3</td>"
            "</tr>"
        )

    parts: list[str] = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>ETF看图说话 {_esc(as_of)}</title></head>",
        "<body style='margin:0;padding:16px;background:#f9fafb;"
        "font-family:-apple-system,BlinkMacSystemFont,\"PingFang SC\",\"Segoe UI\",sans-serif;"
        "color:#101828;font-size:15px;line-height:1.5'>",
        "<div style='max-width:720px;margin:0 auto;background:#fff;padding:16px 18px;"
        "border-radius:12px;border:1px solid #e4e7ec'>",
        "<h1 style='margin:0 0 8px;font-size:20px'>每日 ETF 看图说话指南</h1>",
        f"<p style='margin:0 0 12px;color:#667085;font-size:13px'>"
        f"provider={_esc(provider_id)} · as_of={_esc(as_of)}</p>",
        "<p style='margin:0 0 16px;padding:10px 12px;background:#f2f4f7;border-radius:8px;"
        "font-size:13px;color:#475467'>研究观察口径，非正式投资建议 / 非自动交易指令。"
        "正文含价格地势与 RSI 图（①②③圈点）；附件另附 HTML/Markdown/PNG。</p>",
        "<h2 style='margin:20px 0 10px;font-size:17px'>总览</h2>",
        "<table style='width:100%;border-collapse:collapse;font-size:13px'>",
        "<thead><tr style='background:#f2f4f7'>"
        "<th style='padding:8px;border:1px solid #e4e7ec;text-align:left'>标的</th>"
        "<th style='padding:8px;border:1px solid #e4e7ec;text-align:left'>档位</th>"
        "<th style='padding:8px;border:1px solid #e4e7ec;text-align:right'>建议仓位</th>"
        "<th style='padding:8px;border:1px solid #e4e7ec;text-align:left'>趋势</th>"
        "<th style='padding:8px;border:1px solid #e4e7ec;text-align:right'>偏好做多</th>"
        "<th style='padding:8px;border:1px solid #e4e7ec;text-align:right'>Top3</th>"
        "</tr></thead>",
        "<tbody>",
        *rows,
        "</tbody></table>",
    ]
    if skipped:
        parts.append("<h3 style='margin:18px 0 8px;font-size:15px'>数据缺失 / 跳过</h3><ul>")
        for s in skipped:
            parts.append(
                f"<li>{_esc(s.get('code'))}: {_esc(s.get('reason'))}</li>"
            )
        parts.append("</ul>")

    for sec in sections:
        d = sec["decision"]
        r = sec["regime"]
        c1 = d.get("calmar1") or {}
        color = _tier_color(str(d["tier"]))
        pref = d.get("preferred") or []
        pref_html = (
            "<br>".join(
                f"{_esc(p.get('label'))}={_esc(p.get('current_signal'))}"
                f"({float(p.get('current_weight') or 0):.2f})"
                for p in pref
            )
            or "—"
        )
        ct = sec.get("chart_talk") or {}
        conclusion = ct.get("conclusion") or d.get("rationale") or ""
        snap = r.get("snapshot") or {}
        close = snap.get("close")
        close_txt = f"{float(close):.4g}" if close is not None else "—"

        parts.extend(
            [
                "<hr style='border:none;border-top:1px solid #e4e7ec;margin:22px 0'>",
                f"<h2 style='margin:0 0 8px;font-size:17px'>{_esc(d['label'])}</h2>",
                f"<p style='margin:0 0 8px'><span style='display:inline-block;"
                f"padding:2px 10px;border-radius:999px;background:{color};color:#fff;"
                f"font-size:13px;font-weight:700'>{_esc(d['tier'])}</span>"
                f" · 目标仓 <b>{float(d['target_weight']):.2f}</b>"
                f" · 收盘 { _esc(close_txt) }</p>",
                f"<p style='margin:0 0 8px'>趋势 <b>{_esc(r.get('trend'))}</b> / "
                f"强度 {_esc(r.get('trend_strength'))} · 波动 {_esc(r.get('volatility'))} · "
                f"RSI {_esc(r.get('rsi_state'))}</p>",
                "<div style='margin:0 0 12px;padding:10px 12px;background:#fff8eb;"
                "border-radius:8px;border:1px solid #fecd89;font-size:13px'>"
                f"<b>一句话结论</b>：{_esc(conclusion)}</div>",
            ]
        )

        price_src = _img_src(ct, kind="price", image_mode=image_mode, as_of=as_of)
        if price_src:
            parts.append(
                "<p style='margin:12px 0 6px;font-size:14px;font-weight:600'>"
                "图1 · 价格地势（收盘 vs 5/20 日均线）</p>"
                f"<img src='{_esc(price_src)}' alt='price chart' "
                "style='max-width:100%;height:auto;border:1px solid #e4e7ec;"
                "border-radius:8px'/>"
            )
        elif sec.get("chart_error"):
            parts.append(
                f"<p style='color:#b54708;font-size:13px'>图1 未生成："
                f"{_esc(sec.get('chart_error'))}</p>"
            )

        callouts = ct.get("callouts") or []
        if callouts:
            parts.append(
                "<p style='margin:12px 0 6px;font-size:14px;font-weight:600'>"
                "均线台阶（白话圈点）</p>"
                "<table style='width:100%;border-collapse:collapse;font-size:12px'>"
                "<tr style='background:#f2f4f7'>"
                "<th style='padding:6px;border:1px solid #e4e7ec'>圈注</th>"
                "<th style='padding:6px;border:1px solid #e4e7ec;text-align:right'>价位</th>"
                "<th style='padding:6px;border:1px solid #e4e7ec;text-align:left'>角色</th>"
                "<th style='padding:6px;border:1px solid #e4e7ec;text-align:left'>相对现价</th>"
                "<th style='padding:6px;border:1px solid #e4e7ec;text-align:left'>含义</th>"
                "</tr>"
            )
            for row in callouts:
                parts.append(
                    "<tr>"
                    f"<td style='padding:6px;border:1px solid #e4e7ec'>"
                    f"{_esc(row.get('mark'))}</td>"
                    f"<td style='padding:6px;border:1px solid #e4e7ec;text-align:right'>"
                    f"{_esc(row.get('price'))}</td>"
                    f"<td style='padding:6px;border:1px solid #e4e7ec'>"
                    f"{_esc(row.get('role'))}</td>"
                    f"<td style='padding:6px;border:1px solid #e4e7ec'>"
                    f"{_esc(row.get('vs_close'))}</td>"
                    f"<td style='padding:6px;border:1px solid #e4e7ec'>"
                    f"{_esc(row.get('meaning'))}</td>"
                    "</tr>"
                )
            parts.append("</table>")

        rsi_src = _img_src(ct, kind="rsi", image_mode=image_mode, as_of=as_of)
        if rsi_src:
            rsi_now = ct.get("rsi")
            rsi_note = (
                f"（当前 ≈ {float(rsi_now):.1f}）" if rsi_now is not None else ""
            )
            parts.append(
                "<p style='margin:14px 0 6px;font-size:14px;font-weight:600'>"
                f"图2 · 强弱温度 RSI14{rsi_note}</p>"
                f"<img src='{_esc(rsi_src)}' alt='rsi chart' "
                "style='max-width:100%;height:auto;border:1px solid #e4e7ec;"
                "border-radius:8px'/>"
                "<p style='margin:4px 0 0;font-size:12px;color:#667085'>"
                "RSI=近两周涨跌力量对比；30 以下偏冷，70 以上偏热。</p>"
            )

        parts.append(_position_bar_html(float(d["target_weight"])))

        tranches = ct.get("tranches") or []
        if tranches:
            parts.append(
                "<p style='margin:14px 0 6px;font-size:14px;font-weight:600'>"
                "分批介入（L1→R2，研究观察）</p>"
                "<table style='width:100%;border-collapse:collapse;font-size:12px'>"
                "<tr style='background:#f2f4f7'>"
                "<th style='padding:6px;border:1px solid #e4e7ec;text-align:left'>批次</th>"
                "<th style='padding:6px;border:1px solid #e4e7ec;text-align:left'>触发条件</th>"
                "<th style='padding:6px;border:1px solid #e4e7ec;text-align:left'>仓位口径</th>"
                "<th style='padding:6px;border:1px solid #e4e7ec;text-align:left'>含义</th>"
                "</tr>"
            )
            for row in tranches:
                parts.append(
                    "<tr>"
                    f"<td style='padding:6px;border:1px solid #e4e7ec'>"
                    f"{_esc(row.get('batch'))}</td>"
                    f"<td style='padding:6px;border:1px solid #e4e7ec'>"
                    f"{_esc(row.get('trigger'))}</td>"
                    f"<td style='padding:6px;border:1px solid #e4e7ec'>"
                    f"{_esc(row.get('size'))}</td>"
                    f"<td style='padding:6px;border:1px solid #e4e7ec'>"
                    f"{_esc(row.get('meaning'))}</td>"
                    "</tr>"
                )
            parts.append("</table>")

        parts.extend(
            [
                "<p style='margin:14px 0 6px;font-size:14px;font-weight:600'>"
                "仓位决策表（缩圈→否决→共振→定仓）</p>",
                "<table style='width:100%;border-collapse:collapse;font-size:13px;margin:0 0 10px'>",
                "<tr><td style='padding:8px;border:1px solid #e4e7ec;width:28%;background:#f9fafb'>"
                "档位</td>"
                f"<td style='padding:8px;border:1px solid #e4e7ec;color:{color};font-weight:700'>"
                f"{_esc(d['tier'])}</td></tr>",
                "<tr><td style='padding:8px;border:1px solid #e4e7ec;background:#f9fafb'>"
                "建议目标仓位</td>"
                f"<td style='padding:8px;border:1px solid #e4e7ec'>"
                f"<b>{float(d['target_weight']):.2f}</b>（研究观察）</td></tr>",
                "<tr><td style='padding:8px;border:1px solid #e4e7ec;background:#f9fafb'>"
                "全表票数</td>"
                f"<td style='padding:8px;border:1px solid #e4e7ec'>做多 "
                f"{_esc((d.get('full_table_votes') or {}).get('做多'))} / 看跌 "
                f"{_esc((d.get('full_table_votes') or {}).get('看跌'))}"
                "（对照，非主依据）</td></tr>",
                "<tr><td style='padding:8px;border:1px solid #e4e7ec;background:#f9fafb'>"
                "偏好集</td>"
                f"<td style='padding:8px;border:1px solid #e4e7ec'>{pref_html}；做多 "
                f"{d['preferred_long']}/{d['preferred_n']}</td></tr>",
                "<tr><td style='padding:8px;border:1px solid #e4e7ec;background:#f9fafb'>"
                "Calmar#1</td>"
                f"<td style='padding:8px;border:1px solid #e4e7ec'>"
                f"{_esc(c1.get('label'))}={_esc(c1.get('current_signal'))}；"
                f"{'触发否决' if c1.get('veto') else '未否决'}</td></tr>",
                "<tr><td style='padding:8px;border:1px solid #e4e7ec;background:#f9fafb'>"
                "Top3 共振</td>"
                f"<td style='padding:8px;border:1px solid #e4e7ec'>做多 {d['top3_long']}/3</td></tr>",
                "<tr><td style='padding:8px;border:1px solid #e4e7ec;background:#f9fafb'>"
                "依据摘要</td>"
                f"<td style='padding:8px;border:1px solid #e4e7ec'>{_esc(d.get('rationale'))}</td></tr>",
                "</table>",
            ]
        )
        comparison = sec.get("comparison") or []
        if comparison:
            parts.append(
                "<p style='margin:12px 0 6px;font-size:14px;font-weight:600'>"
                "全策略当前信号（证据面板，非齐步表决）</p>"
            )
            parts.append(
                "<table style='width:100%;border-collapse:collapse;font-size:12px'>"
                "<tr style='background:#f2f4f7'>"
                "<th style='padding:6px;border:1px solid #e4e7ec;text-align:left'>策略</th>"
                "<th style='padding:6px;border:1px solid #e4e7ec'>信号</th>"
                "<th style='padding:6px;border:1px solid #e4e7ec;text-align:right'>仓位</th>"
                "<th style='padding:6px;border:1px solid #e4e7ec;text-align:right'>Calmar</th>"
                "</tr>"
            )
            for row in comparison:
                sid = str(row.get("strategy_id") or "")
                label = format_strategy_id(sid)
                parts.append(
                    "<tr>"
                    f"<td style='padding:6px;border:1px solid #e4e7ec'>{_esc(label)}</td>"
                    f"<td style='padding:6px;border:1px solid #e4e7ec;text-align:center'>"
                    f"{_esc(row.get('current_signal'))}</td>"
                    f"<td style='padding:6px;border:1px solid #e4e7ec;text-align:right'>"
                    f"{float(row.get('current_weight') or 0):.2f}</td>"
                    f"<td style='padding:6px;border:1px solid #e4e7ec;text-align:right'>"
                    f"{float(row.get('calmar') or 0):.2f}</td>"
                    "</tr>"
                )
            parts.append("</table>")

    parts.extend(
        [
            "<p style='margin:24px 0 0;font-size:12px;color:#98a2b3'>"
            "信号按收盘确认、次日开盘成交假设。本邮件由 AIStockAssistant 自动发送。</p>",
            "</div></body></html>",
        ]
    )
    return "\n".join(parts)
