"""Cross-sectional scoring engine (L3)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.data.models import Bar
from app.data.provider import IDataProvider
from app.selection.factors import percentile_scores
from app.selection.factors import fundamental as fund_f
from app.selection.factors import flow as flow_f
from app.selection.factors import price as price_f
from app.selection.factors.macro import macro_from_etf_regime, merge_macro
from app.selection.meta import MetaStore
from app.selection.types import FactorHealth, FactorValue, StockScore

FACTOR_META: list[tuple[str, str, str, bool, int]] = [
    ("trend_ma_adx", "趋势", "均线排列+ADX", True, 1),
    ("mom_20", "趋势", "20日动量", True, 1),
    ("mom_60", "动量", "60日动量", True, 1),
    ("rel_str_60", "动量", "相对沪深300超额60日", True, 1),
    ("vol_20", "波动", "20日实现波动率", False, 1),
    ("mdd_60", "风险", "60日最大回撤", True, 1),
    ("liq_amt_20", "资金", "20日均成交额", True, 1),
    ("value_ep", "价值", "盈利收益率1/PE", True, 3),
    ("value_bp", "价值", "账面市值比1/PB", True, 3),
    ("quality_roe", "质量", "ROE", True, 3),
    ("quality_cagr", "质量", "净利润CAGR", True, 3),
    ("flow_inflow_5d", "资金", "5日主力净流入", True, 4),
    ("flow_north_days", "资金", "北向连续流入天数", True, 4),
    ("sector_mom", "行业", "行业动量代理", True, 4),
]


def list_factor_catalog() -> list[dict[str, Any]]:
    return [
        {
            "factor_id": fid,
            "category": cat,
            "name_zh": name,
            "higher_is_better": hib,
            "phase": phase,
        }
        for fid, cat, name, hib, phase in FACTOR_META
    ]


def score_universe_with_macro(
    codes: list[str],
    provider: IDataProvider,
    meta: MetaStore,
    *,
    bench_code: str = "sh510300",
    health: dict[str, FactorHealth] | None = None,
    index_membership: dict[str, list[str]] | None = None,
) -> tuple[list[StockScore], dict[str, Any]]:
    bars_map: dict[str, list[Bar]] = {c: provider.get_daily_bars(c) for c in codes}
    bench = provider.get_daily_bars(bench_code) or []

    sector_moms: dict[str, list[float]] = defaultdict(list)
    for c in codes:
        sec = meta.sector(c)
        m = price_f.mom_20(bars_map[c])
        if m is not None and sec != "unknown":
            sector_moms[sec].append(m)
    sector_avg = {s: sum(vs) / len(vs) for s, vs in sector_moms.items() if vs}

    raw_by_factor: dict[str, dict[str, float | None]] = {fid: {} for fid, *_ in FACTOR_META}
    detail_by: dict[str, dict[str, str]] = defaultdict(dict)

    for c in codes:
        bars = bars_map[c]
        last_close = float(bars[-1].close) if bars else None
        price_as_of = bars[-1].trade_date if bars else None
        fin = meta.finance(
            c, provider, last_close=last_close, price_as_of=price_as_of
        )
        flow = meta.capital_flow(c)
        sec = meta.sector(c)

        raw_by_factor["trend_ma_adx"][c] = price_f.trend_ma_align(bars)
        detail_by[c]["trend_ma_adx"] = price_f.ma_stack_detail(bars)
        raw_by_factor["mom_20"][c] = price_f.mom_20(bars)
        raw_by_factor["mom_60"][c] = price_f.mom_60(bars)
        raw_by_factor["rel_str_60"][c] = (
            price_f.relative_strength_60(bars, bench) if bench else None
        )
        raw_by_factor["vol_20"][c] = price_f.vol_20(bars)
        raw_by_factor["mdd_60"][c] = price_f.max_drawdown_60(bars)
        raw_by_factor["liq_amt_20"][c] = price_f.liquidity_amount_20(bars)

        if fin is not None and (fin.pe is not None or fin.pb is not None or fin.roe is not None):
            raw_by_factor["value_ep"][c] = fund_f.value_ep(fin)
            raw_by_factor["value_bp"][c] = fund_f.value_bp(fin)
            raw_by_factor["quality_roe"][c] = fund_f.quality_roe(fin)
            raw_by_factor["quality_cagr"][c] = fund_f.quality_profit_cagr(fin)
        else:
            for fid in ("value_ep", "value_bp", "quality_roe", "quality_cagr"):
                raw_by_factor[fid][c] = None

        raw_by_factor["flow_inflow_5d"][c] = flow_f.flow_net_inflow_5d(flow)
        raw_by_factor["flow_north_days"][c] = flow_f.flow_northbound_days(flow)
        raw_by_factor["sector_mom"][c] = flow_f.sector_momentum_proxy(c, sec, sector_avg)

    scores_by_factor: dict[str, dict[str, float | None]] = {}
    for fid, _cat, _name, hib, _phase in FACTOR_META:
        scores_by_factor[fid] = percentile_scores(raw_by_factor[fid], higher_is_better=hib)

    file_macro = meta.macro_scale()
    etf_macro = macro_from_etf_regime(provider, code=bench_code)
    macro = merge_macro(file_macro, etf_macro)
    scale = flow_f.macro_scale(macro)

    out: list[StockScore] = []
    for c in codes:
        factors: dict[str, FactorValue] = {}
        cat_acc: dict[str, list[float]] = defaultdict(list)
        for fid, cat, name, hib, phase in FACTOR_META:
            raw = raw_by_factor[fid].get(c)
            sc = scores_by_factor[fid].get(c)
            status = "ok"
            detail = detail_by[c].get(fid, "")
            if health and fid in health and health[fid].lifecycle == "demoted":
                status = "demoted"
                sc = None
            elif raw is None:
                status = "unavailable"
                if phase >= 3 and not detail:
                    detail = f"phase{phase} data unavailable"
            fv = FactorValue(
                factor_id=fid,
                category=cat,
                name_zh=name,
                raw=raw,
                score=sc,
                status=status,  # type: ignore[arg-type]
                detail=detail,
                higher_is_better=hib,
            )
            factors[fid] = fv
            if status == "ok" and sc is not None:
                if not health or health.get(fid) is None or health[fid].lifecycle == "active":
                    cat_acc[cat].append(sc)

        cat_scores: dict[str, float | None] = {
            cat: None for cat in {m[1] for m in FACTOR_META}
        }
        for cat, vs in cat_acc.items():
            cat_scores[cat] = sum(vs) / len(vs) if vs else None

        usable = [v for v in cat_scores.values() if v is not None]
        composite = (sum(usable) / len(usable) * scale) if usable else None

        membership: list[str] = []
        if index_membership:
            for idx, members in index_membership.items():
                if c in members:
                    membership.append(idx)

        out.append(
            StockScore(
                code=c,
                name=meta.name(c),
                composite=composite,
                factors=factors,
                category_scores=cat_scores,
                sector=meta.sector(c),
                indices=membership,
            )
        )
    return out, macro


def score_universe(
    codes: list[str],
    provider: IDataProvider,
    meta: MetaStore,
    *,
    bench_code: str = "sh510300",
    health: dict[str, FactorHealth] | None = None,
    index_membership: dict[str, list[str]] | None = None,
) -> list[StockScore]:
    scores, _ = score_universe_with_macro(
        codes,
        provider,
        meta,
        bench_code=bench_code,
        health=health,
        index_membership=index_membership,
    )
    return scores
