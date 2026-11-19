"""L7 factor IC / RankIC / long-short / lifecycle."""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any, Callable

from app.data.models import Bar
from app.data.provider import IDataProvider
from app.selection.factors import percentile_scores
from app.selection.factors.price import (
    liquidity_amount_20,
    max_drawdown_60,
    mom_20,
    mom_60,
    relative_strength_60,
    trend_ma_align,
    vol_20,
)
from app.selection.types import FactorHealth, Lifecycle

RawFn = Callable[[list[Bar], list[Bar] | None], float | None]


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 5 or n != len(ys):
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 5:
        return None

    def ranks(vals: list[float]) -> list[float]:
        order = sorted(range(n), key=lambda i: vals[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    return _pearson(ranks(xs), ranks(ys))


def _slice_to(bars: list[Bar], end: date) -> list[Bar]:
    return [b for b in bars if b.trade_date <= end]


def _fwd_return(bars: list[Bar], as_of: date, horizon: int = 20) -> float | None:
    # find index of as_of or last <= as_of
    idx = None
    for i, b in enumerate(bars):
        if b.trade_date == as_of:
            idx = i
            break
        if b.trade_date < as_of:
            idx = i
    if idx is None or idx + horizon >= len(bars):
        return None
    p0 = bars[idx].close
    p1 = bars[idx + horizon].close
    if p0 <= 0:
        return None
    return p1 / p0 - 1.0


PRICE_FACTOR_FNS: dict[str, tuple[RawFn, bool]] = {
    "trend_ma_adx": (lambda bars, _b: trend_ma_align(bars), True),
    "mom_20": (lambda bars, _b: mom_20(bars), True),
    "mom_60": (lambda bars, _b: mom_60(bars), True),
    "rel_str_60": (lambda bars, bench: relative_strength_60(bars, bench or []), True),
    "vol_20": (lambda bars, _b: vol_20(bars), False),
    "mdd_60": (lambda bars, _b: max_drawdown_60(bars), True),
    "liq_amt_20": (lambda bars, _b: liquidity_amount_20(bars), True),
}


def _sample_dates(bars_map: dict[str, list[Bar]], months: int, step: int = 21) -> list[date]:
    # Use intersection of last dates across names — take from densest series
    if not bars_map:
        return []
    ref = max(bars_map.values(), key=len)
    if not ref:
        return []
    end = ref[-1].trade_date
    start = end - timedelta(days=int(months * 30.5))
    dates = [b.trade_date for b in ref if start <= b.trade_date <= end]
    return dates[::step]


def validate_factor(
    factor_id: str,
    codes: list[str],
    provider: IDataProvider,
    *,
    bench_code: str = "sh510300",
    months: int = 12,
) -> FactorHealth:
    spec = PRICE_FACTOR_FNS.get(factor_id)
    if spec is None:
        return FactorHealth(
            factor_id=factor_id,
            lifecycle="watch",
            note="validation only implemented for Phase1 price factors in L7 v1",
            evidence_grade="D",
        )
    fn, hib = spec
    bars_map = {c: provider.get_daily_bars(c) for c in codes}
    bench = provider.get_daily_bars(bench_code)
    dates = _sample_dates(bars_map, months=months, step=21)
    ics: list[float] = []
    rank_ics: list[float] = []
    long_rets: list[float] = []
    short_rets: list[float] = []

    for d in dates:
        raws: dict[str, float | None] = {}
        fwds: dict[str, float | None] = {}
        for c, bars in bars_map.items():
            hist = _slice_to(bars, d)
            if len(hist) < 130:
                continue
            bhist = _slice_to(bench, d) if bench else []
            try:
                raws[c] = fn(hist, bhist if bhist else None)
            except Exception:
                raws[c] = None
            fwds[c] = _fwd_return(bars, d, 20)

        scores = percentile_scores(raws, higher_is_better=hib)
        xs: list[float] = []
        ys: list[float] = []
        scored: list[tuple[str, float, float]] = []
        for c, sc in scores.items():
            fr = fwds.get(c)
            if sc is None or fr is None:
                continue
            xs.append(sc)
            ys.append(fr)
            scored.append((c, sc, fr))
        ic = _pearson(xs, ys)
        ric = _spearman(xs, ys)
        if ic is not None:
            ics.append(ic)
        if ric is not None:
            rank_ics.append(ric)
        if len(scored) >= 10:
            scored.sort(key=lambda x: x[1])
            n = max(len(scored) // 5, 1)
            short = scored[:n]
            long = scored[-n:]
            long_rets.append(sum(x[2] for x in long) / len(long))
            short_rets.append(sum(x[2] for x in short) / len(short))

    ic_mean = sum(ics) / len(ics) if ics else None
    ric_mean = sum(rank_ics) / len(rank_ics) if rank_ics else None
    ic_std = (
        math.sqrt(sum((x - ic_mean) ** 2 for x in ics) / max(len(ics) - 1, 1))
        if ics and ic_mean is not None
        else None
    )
    icir = (ic_mean / ic_std) if ic_mean is not None and ic_std and ic_std > 1e-9 else None

    ls = [l - s for l, s in zip(long_rets, short_rets)] if long_rets and short_rets else []
    ls_mean = sum(ls) / len(ls) if ls else None
    # Approximate annualization from 20d horizon steps
    ann = ((1 + ls_mean) ** (252 / 20) - 1) if ls_mean is not None else None
    # crude MDD on cumulative ls
    mdd = None
    sharpe = None
    if ls:
        equity = 1.0
        peak = 1.0
        mdd_v = 0.0
        for r in ls:
            equity *= 1 + r
            peak = max(peak, equity)
            mdd_v = min(mdd_v, equity / peak - 1)
        mdd = mdd_v
        mu = sum(ls) / len(ls)
        sd = math.sqrt(sum((x - mu) ** 2 for x in ls) / max(len(ls) - 1, 1))
        sharpe = (mu / sd * math.sqrt(252 / 20)) if sd > 1e-9 else None

    # OOS: last 25% of IC samples
    oos_pass = None
    if len(rank_ics) >= 8:
        cut = max(len(rank_ics) * 3 // 4, 1)
        oos = rank_ics[cut:]
        oos_pass = (sum(oos) / len(oos)) > 0

    lifecycle: Lifecycle = "active"
    grade = "C"
    note = ""
    if ric_mean is None:
        lifecycle = "watch"
        grade = "D"
        note = "insufficient IC samples"
    elif ric_mean <= 0 and (icir is None or icir < 0.2):
        lifecycle = "demoted"
        grade = "D"
        note = "RankIC<=0 and weak ICIR"
    elif oos_pass and ric_mean > 0.02 and (icir or 0) > 0.3:
        lifecycle = "active"
        grade = "B"
        note = "positive RankIC with OOS pass"
    elif ric_mean > 0:
        lifecycle = "active"
        grade = "C"
        note = "positive in-sample RankIC"
    else:
        lifecycle = "watch"
        grade = "D"
        note = "weak / negative RankIC"

    # Simple regime split using market mom of bench
    regime: dict[str, Any] = {}
    if bench and len(bench) > 60:
        bm = mom_60(bench)
        if bm is not None:
            regime["bench_mom_60"] = bm
            regime["label"] = "uptrend" if bm > 0.05 else ("downtrend" if bm < -0.05 else "sideways")

    return FactorHealth(
        factor_id=factor_id,
        lifecycle=lifecycle,
        ic_1y=ic_mean if months <= 12 else None,
        rank_ic_1y=ric_mean if months <= 12 else None,
        icir_1y=icir if months <= 12 else None,
        ic_3y=ic_mean if months > 12 else None,
        rank_ic_3y=ric_mean if months > 12 else None,
        long_short_ann=ann,
        long_short_mdd=mdd,
        long_short_sharpe=sharpe,
        regime=regime,
        oos_pass=oos_pass,
        evidence_grade=grade,  # type: ignore[arg-type]
        note=note,
    )


def validate_price_factors(
    codes: list[str],
    provider: IDataProvider,
    *,
    months: int = 12,
) -> dict[str, FactorHealth]:
    out: dict[str, FactorHealth] = {}
    for fid in PRICE_FACTOR_FNS:
        out[fid] = validate_factor(fid, codes, provider, months=months)
    return out


def event_stats_for_factor(health: FactorHealth) -> dict[str, Any]:
    return {
        "ic_1y": health.ic_1y,
        "rank_ic_1y": health.rank_ic_1y,
        "icir_1y": health.icir_1y,
        "long_short_ann": health.long_short_ann,
        "long_short_mdd": health.long_short_mdd,
        "long_short_sharpe": health.long_short_sharpe,
        "oos_pass": health.oos_pass,
        "lifecycle": health.lifecycle,
        "note": health.note,
    }
