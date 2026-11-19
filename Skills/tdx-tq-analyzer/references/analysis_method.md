# 量能与资金流分析方法论

## Principles

1. **Never judge from a single day.** One day's active buy/sell ratio is noise; only multi-day continuity changes a stage judgment.
2. **Separate signal horizons.** 当日内外盘 = short-term order flow; 20-day CMF = medium-term money flow. When they diverge, say so explicitly — do not let one override the other.
3. **Distinguish behavior types.** For broad-based ETFs, volume spikes often come from creation/redemption, index rebalancing, or market-maker hedging — not directional conviction. Check IOPV premium/discount and share count before calling a spike "smart money buying".
4. **Volume direction matters more than volume size.** Large volume on a down/stagnant day is distribution or disagreement, not accumulation.
5. **Cross-check with price context.** Always report 5/20/60-day and YTD returns alongside volume so the reader sees the trend the volume sits in.

## Metrics computed by analyze.py

| Metric | Definition | Reading |
|---|---|---|
| `vr5`, `vr20` | today's volume / 5-day or 20-day average volume | >1.5 放量; <0.7 缩量; remember to halve the interpretation for a live intraday session |
| `med60_yi` | 60-day median volume (亿股) | robust baseline vs. mean distorted by spikes |
| `updown_ratio` | avg volume on up days / avg volume on down days (last 20 full days) | >1 量能偏多; <1 量能偏空 |
| `cmf20` | 20-day Chaikin Money Flow = Σ(Close−Low − (High−Close))/(High−Low) × Vol / ΣVol | >0.05 中期净流入; <−0.05 中期净流出; between = neutral |
| `outside_ratio` | Outside / (Inside + Outside) from snapshot | >0.55 主动买盘占优; <0.45 主动卖盘占优 |
| `net_active_yi` | (Outside − Inside) / Volume × Amount, in 亿元 | estimated net active buy amount (statistical inference only) |

## Report structure (build_report.py)

- TL;DR conclusion box (volume level, recent peak-volume day, money-flow direction + CMF consistency, price context with IOPV premium)
- Snapshot KPIs (price, change, amount, volume, turnover, size)
- 60-day candlestick + volume chart with MA5/MA20 and 10-day volume MA (figure/table toggle)
- Volume structure bar chart
- Inside/outside pie chart
- Fixed investment disclaimer

A-share convention: **red = up, green = down** (already applied in the template).

## Interpretation template

When writing the user-facing summary, structure it as:

1. **量能水位** — today's volume vs 5/20-day average vs 60-day median; note intraday caveat if live.
2. **峰量方向** — describe the largest recent volume day and whether price rose or stalled on it.
3. **资金流** — today's outside ratio + net active amount, then 20-day CMF; explicitly call out if they diverge.
4. **价格背景** — 5/20/60-day and YTD returns, IOPV premium for ETFs.
5. **结论倾向** — e.g. "中期流出趋势中的短线回流，需后续 3–5 日确认" rather than a binary buy/sell call.

## Caveats to always state

- 内外盘 / CMF are statistical inferences from trade data, not actual institutional account flows.
- ETF creation/redemption data requires fund-company disclosure; not included here.
- During a live session the last daily bar is partial — volume ratios understate the full-day figure.
- Charts load ECharts from CDN; the HTML needs internet to render.
