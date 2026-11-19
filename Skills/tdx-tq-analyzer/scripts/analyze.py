# -*- coding: utf-8 -*-
"""
Analyze raw TQ data (JSON from tq_fetch.py) into metrics + chart data.
Pure analysis, no TQ connection needed. Can run with any Python that has pandas/numpy.

Usage:
    python analyze.py <RAW_JSON> <METRICS_JSON> <CHART_JSON>
"""
import json
import sys

import pandas as pd
import numpy as np


def build_df(raw):
    frames = []
    for window in raw["windows"].values():
        cols = {}
        for f in ["Open", "High", "Low", "Close", "Volume", "Amount"]:
            cols[f] = pd.Series({k: float(v) for k, v in window.get(f, {}).items()}, dtype=float)
        x = pd.DataFrame(cols)
        x.index = pd.to_datetime(x.index)
        frames.append(x)
    df = pd.concat(frames)
    df = df[~df.index.duplicated(keep="last")].sort_index().dropna(subset=["Close", "Volume"])
    if len(df) < 2:
        raise ValueError(
            "TQ 未返回可用日线（只有快照）。常见原因：显式 field_list 导致空窗口、"
            "客户端盘后缓存未刷新。请确认 tq_fetch.py 使用 field_list=[] 并调用 refresh_cache 后重试。"
        )
    return df


def buycase(df, snap, mi, metrics, now):
    """Build a defensible 'buy basis' block.

    Design principles inherited from the Cursor rules, filtered for what TQ can
    actually support:
      - hard veto before any 'support' vote (no majority-vote decisions)
      - volume must be assessed; absent data -> '未评估', never invented
      - news / chip structure -> always '未评估' (TQ has no such fields)
      - evidence grade capped at C because this skill runs NO out-of-sample
        backtest; a negative-Sharpe strategy must never earn B (the flaw found
        in the Cursor platform's grade_strategy_row)
      - always emit trigger / stop / watchpoints triplet
    This is a research-observation framework, not a trade signal.
    """
    closes = df.Close
    ma5 = float(closes.tail(5).mean())
    ma20 = float(closes.tail(20).mean())
    ma60 = float(closes.tail(60).mean()) if len(closes) >= 60 else None

    # Support / resistance from actual bars only (never fabricated)
    w = df.tail(20)
    low20 = float(w.Low.min())
    high20 = float(w.High.max())
    support = low20 if low20 < now else (ma60 if ma60 and ma60 < now else None)
    resistance = high20 if high20 > now else None
    upside = (resistance - now) / now * 100 if resistance else None
    downside = (now - support) / now * 100 if support else None
    rr = upside / downside if (upside is not None and downside and downside > 0) else None

    # --- dimension assessments ---
    trend = "未评估"
    if ma60 is not None:
        if now > ma20 and now > ma60:
            trend = "支持"
        elif now < ma20 and now < ma60:
            trend = "不支持"
        else:
            trend = "中性"

    vol = metrics["volume"]
    money = metrics["moneyflow"]
    volume_state = "未评估"
    if vol["vr20"] and vol["updown_ratio"]:
        if vol["updown_ratio"] > 1.1 and vol["vr20"] >= 0.8:
            volume_state = "支持"
        elif (vol["vr20"] > 1.5 and now < ma20) or vol["updown_ratio"] < 0.8:
            volume_state = "不支持"
        else:
            volume_state = "中性"

    money_state = "未评估"
    if money["outside_ratio"]:
        if money["cmf20"] > 0.05 and money["outside_ratio"] > 0.5:
            money_state = "支持"
        elif money["cmf20"] < -0.05:
            money_state = "不支持"
        else:
            money_state = "中性"

    position = "无法评估"
    if support and resistance and rr is not None:
        if upside is not None and upside < 3 and rr < 1:
            position = "偏贵（贴近压力）"
        elif rr >= 1.5:
            position = "合理"
        else:
            position = "中性"

    # --- hard veto (no majority vote can override) ---
    vetoes = []
    if trend == "不支持" and money_state == "不支持":
        vetoes.append("趋势与中期资金同时不支持（价格位于 MA20/MA60 下方且 CMF20 < -0.05）")
    if position == "偏贵（贴近压力）" and volume_state == "不支持":
        vetoes.append("价格贴近近 20 日高点且量能结构不支持（放量滞涨/缩量）")
    if len(df) < 60:
        vetoes.append("可用日线不足 60 根，无法计算 MA60 与 20 日 CMF")

    supports = sum(1 for x in [trend, volume_state, money_state] if x == "支持")
    if vetoes:
        tier = "不成立（否决）"
    elif supports >= 3 and position == "合理":
        tier = "关注（可列入观察）"
    elif supports >= 2:
        tier = "试探（仅研究观察）"
    else:
        tier = "观望"

    # Evidence: NO OOS backtest in this skill -> cap at C. D when vetoed.
    grade = "D" if vetoes else "C"
    grade_basis = (
        "数据源单一（通达信 TQ），本技能不做样本外回测与跨标的验证；"
        "仅描述性量价统计，故证据等级上限为 C。"
        + (" 当前触发否决项，降为 D。" if vetoes else "")
    )

    # Triplet: all numbers from actual bars
    if support and resistance:
        trigger_txt = (
            f"收盘价重新站上 MA20（{ma20:.3f}）且 CMF20 转正；"
            f"或回踩支撑 {support:.3f} 附近（误差 ±1%）且量比回落至 0.8 以下企稳。"
        )
        stop_txt = (
            f"收盘跌破 {support:.3f} 且 CMF20 < -0.1 → 依据失效；"
            f"纯价格止损参考 {support * 0.98:.3f}（支撑下方 2%）。"
        )
    else:
        trigger_txt = "缺少可靠支撑/压力位，暂不设定价格触发；等待数据充分后重估。"
        stop_txt = "价格止损待补（无可靠支撑位）；逻辑止损：CMF20 持续 < -0.1。"

    cmf_watch = (
        f"CMF20 能否维持在 0.05 以上（当前 {money['cmf20']:+.3f}）"
        if money["cmf20"] > 0
        else f"CMF20 能否转正并维持 3 日以上（当前 {money['cmf20']:+.3f}）"
    )
    watch = [
        f"外盘占比是否持续 > 50%（当前 {money['outside_ratio']*100:.1f}%）",
        cmf_watch,
        f"量比（对 20 日均量）是否从 {vol['vr20']:.2f} 回到 0.8–1.5 常态区间",
        "消息面与份额变动（TQ 不提供，需外部数据源）",
    ]

    return {
        "tier": tier,
        "evidence_grade": grade,
        "evidence_basis": grade_basis,
        "gate_veto": vetoes,
        "dimensions": [
            {"name": "趋势位置", "state": trend,
             "basis": f"现价 {now:.3f} vs MA5 {ma5:.3f} / MA20 {ma20:.3f}"
                      + (f" / MA60 {ma60:.3f}" if ma60 else " / MA60 数据不足")},
            {"name": "量能确认", "state": volume_state,
             "basis": f"量比(20日) {vol['vr20']:.2f}，上涨/下跌日均量比 {vol['updown_ratio']:.2f}"},
            {"name": "资金确认", "state": money_state,
             "basis": f"CMF20 {money['cmf20']:+.3f}，外盘占比 {money['outside_ratio']*100:.1f}%"},
            {"name": "位置与风险回报", "state": position,
             "basis": (f"支撑 {support:.3f}，压力 {resistance:.3f}，"
                       f"上行 {upside:.1f}% / 下行 {downside:.1f}%，粗估 R:R≈{rr:.2f}"
                       "（以近 20 日高低点为代理，非精确目标）"
                       if (support and resistance and rr is not None)
                       else "无可靠支撑/压力位，未评估")},
            {"name": "消息面", "state": "未评估",
             "basis": "TQ 接口不提供新闻/公告检索；不得声称无利空"},
            {"name": "筹码结构", "state": "未评估",
             "basis": "TQ 无筹码分布字段；宽基 ETF 通常亦无个股筹码概念，不编造"},
        ],
        "levels": {
            "ma5": ma5, "ma20": ma20, "ma60": ma60,
            "support": support, "resistance": resistance,
            "upside_pct": upside, "downside_pct": downside, "rr": rr,
        },
        "triplet": {"trigger": trigger_txt, "stop": stop_txt, "watchpoints": watch},
        "disclaimer": "研究观察口径，非买入建议、非自动交易指令。",
    }


def analyze(raw):
    df = build_df(raw)
    snap = raw["snapshot"]
    mi = raw["more_info"]
    si = raw["stock_info"]

    inside = float(snap["Inside"])
    outside = float(snap["Outside"])
    vol_lots = float(snap["Volume"])
    amount_wan = float(snap["Amount"])

    df["v5"] = df.Volume.rolling(5).mean()
    df["v10"] = df.Volume.rolling(10).mean()
    df["v20"] = df.Volume.rolling(20).mean()
    df["v60"] = df.Volume.rolling(60).mean()
    df["vr5"] = df.Volume / df.v5
    df["vr20"] = df.Volume / df.v20
    df["chg"] = df.Close.pct_change() * 100
    # Chaikin Money Flow
    rng = (df.High - df.Low).replace(0, np.nan)
    df["MFV"] = ((df.Close - df.Low) - (df.High - df.Close)) / rng * df.Volume
    df["cmf20"] = df.MFV.rolling(20).sum() / df.Volume.rolling(20).sum()

    # last 20 full days (exclude today if it is still a live session)
    d20 = df.tail(21).iloc[:-1].copy()
    d20["dir"] = d20.Close.diff()
    upv = d20[d20["dir"] > 0].Volume.mean() / 1e8
    dnv = d20[d20["dir"] < 0].Volume.mean() / 1e8
    med60 = df.tail(60).Volume.median() / 1e8
    top = df.tail(60).nlargest(6, "Volume")

    # CMF20 intermediate values for plain-language explanation in report
    cmf_win = df.tail(20)
    cmf20_mfv_sum = float(cmf_win.MFV.sum())
    cmf20_vol_sum = float(cmf_win.Volume.sum())

    last = df.iloc[-1]
    prev = df.iloc[-2]

    def f(x, default=0.0):
        try:
            return float(x)
        except (TypeError, ValueError):
            return default

    metrics = {
        "code": raw.get("code"),
        "name": si.get("Name", ""),
        "as_of": str(df.index[-1].date()),
        "snapshot": {
            "now": f(snap.get("Now")), "lastclose": f(snap.get("LastClose")),
            "open": f(snap.get("Open")), "high": f(snap.get("Max")),
            "low": f(snap.get("Min")), "avg": f(snap.get("Average")),
            "iopv": f(snap.get("Jjjz")), "volume_lots": vol_lots,
            "amount_wan": amount_wan, "inside": inside, "outside": outside,
            "outside_ratio": outside / (inside + outside) if (inside + outside) else 0,
            "net_active_lots": outside - inside,
            "net_active_amt_wan": (outside - inside) / vol_lots * amount_wan if vol_lots else 0,
            "weibi": f(mi.get("Wtb")), "hqdate": mi.get("HqDate", ""),
            "turnover": f(mi.get("fHSL")), "size_yi": f(mi.get("Zsz")),
        },
        "performance": {
            "chg5": f(mi.get("ZAFPre5")), "chg20": f(mi.get("ZAFPre20")),
            "chg60": f(mi.get("ZAFPre60")), "chg_ytd": f(mi.get("ZAFYear")),
        },
        "volume": {
            "today_yi": float(last.Volume) / 1e8,
            "prev_yi": float(prev.Volume) / 1e8,
            "v5_yi": float(last.v5) / 1e8,
            "v20_yi": float(last.v20) / 1e8,
            "v60_yi": float(last.v60) / 1e8,
            "vr5": f(last.vr5), "vr20": f(last.vr20),
            "med60_yi": med60,
            "upv_yi": upv, "dnv_yi": dnv,
            "updown_ratio": upv / dnv if dnv else 0,
        },
        "moneyflow": {
            "cmf20": f(last.cmf20),
            "cmf20_mfv_sum": cmf20_mfv_sum,
            "cmf20_vol_sum": cmf20_vol_sum,
            "net_active_yi": (outside - inside) / vol_lots * amount_wan / 1e4 if vol_lots else 0,
            "outside_ratio": outside / (inside + outside) if (inside + outside) else 0,
        },
        "top_volume_days": [
            {"date": str(i.date()), "vol_yi": float(r.Volume) / 1e8,
             "chg": float(r.Close - r.Open) / float(r.Open) * 100 if r.Open else 0}
            for i, r in top.iterrows()
        ],
    }
    metrics["buycase"] = buycase(df, snap, mi, metrics, f(snap.get("Now")) or float(last.Close))

    # Chart data (last 60 bars)
    r = df.tail(60).copy()
    chart = {
        "dates": [i.strftime("%m-%d") for i in r.index],
        "ohlc": [[round(x.Open, 3), round(x.Close, 3), round(x.Low, 3), round(x.High, 3)]
                 for _, x in r.iterrows()],
        "vols": [round(x.Volume / 1e8, 3) for _, x in r.iterrows()],
        "ma5": [None if i < 4 else round(r.Close.iloc[i-4:i+1].mean(), 3) for i in range(len(r))],
        "ma20": [None if i < 19 else round(r.Close.iloc[i-19:i+1].mean(), 3) for i in range(len(r))],
        "vma10": [None if i < 9 else round(r.Volume.iloc[i-9:i+1].mean()/1e8, 3) for i in range(len(r))],
        # Full fetched daily history is retained for teaching and period aggregation.
        "full_dates": [i.strftime("%Y-%m-%d") for i in df.index],
        "full_ohlc": [[round(x.Open, 3), round(x.Close, 3), round(x.Low, 3), round(x.High, 3)]
                      for _, x in df.iterrows()],
        "full_vols": [round(x.Volume / 1e8, 4) for _, x in df.iterrows()],
        "inside": inside, "outside": outside,
    }
    return metrics, chart


def main():
    if len(sys.argv) < 4:
        print("Usage: python analyze.py <RAW_JSON> <METRICS_JSON> <CHART_JSON>")
        sys.exit(2)
    raw = json.load(open(sys.argv[1], encoding="utf-8"))
    metrics, chart = analyze(raw)
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)
    with open(sys.argv[3], "w", encoding="utf-8") as f:
        json.dump(chart, f, ensure_ascii=False)
    print("ANALYZE_OK")
    print("NAME", metrics["name"])
    print("AS_OF", metrics["as_of"])
    print("NOW", metrics["snapshot"]["now"])
    print("VR5", round(metrics["volume"]["vr5"], 2))
    print("CMF20", round(metrics["moneyflow"]["cmf20"], 3))
    bc = metrics["buycase"]
    print("BUY_TIER", bc["tier"], "GRADE", bc["evidence_grade"], "VETO", len(bc["gate_veto"]))


if __name__ == "__main__":
    main()
