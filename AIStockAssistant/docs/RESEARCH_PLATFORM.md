# ETF 策略研究平台（Phase 1 + Phase 2 实验室）

## 目标

在通达信本地数据上，对宽基 ETF 做多策略独立回测、横向对比与市场状态日报；Phase 2 增加多窗口淘汰、样本外切分、跨 ETF 泛化、证据等级与可选 walk-forward。

## 目录

```
app/research/
  data/          # ETF 宇宙、日线/分钟线/成交量 Feed
  indicators/    # MA/EMA/MACD/RSI/KDJ/ATR/ADX/BB/RSRS/动量/波动率
  strategies/    # 14 个经典策略（含 RSI/MACD 常规顶底背离）
  backtest/      # 引擎、绩效、horizons / splits / evidence / walk_forward
  ai/            # 市场状态、失效分析、仓位 playbook、日报
  service.py     # ResearchService 门面
```

## CLI

```bash
python -m app.main research-status
python -m app.main research-strategies
python -m app.main research-backtest sh510300
python -m app.main research-backtest sh510050 --strategy ma_20_60
python -m app.main research-report
python -m app.main research-generalize ma_20_60
python -m app.main research-walk-forward sh510300 ma_20_60
```

## MCP 工具

- `research_data_status`
- `list_research_etfs` / `list_research_strategies`
- `research_backtest_etf` / `research_compare_strategies`
- `research_daily_report`（可选 `attach_cross_etf=true` 挂跨 ETF 分数）
- `research_generalize_strategy` — 同一策略跨宽基泛化
- `research_walk_forward` — 可选滚动样本外实验室（非日报默认路径）
- `get_minute_bars` / `sync_minute_bars`

## Phase 2：研究实验室口径

### 市场状态 (Regime)

- 二维状态：趋势 × 波动（再叠加强度 / RSI），**不是**互斥五分类
- 输出 `preferred_strategies` / `avoid_strategies` / `candidate_set` / `evidence`（判定依据）
- 全表策略仍回测保留为证据面板；候选集用于软过滤与 `rank_in_regime`

### 多窗口与淘汰 (lifecycle)

comparison 每行额外包含：

- `metrics_3y` / `metrics_5y` / `metrics_10y`（短历史标 `status=insufficient`，不得因缺数直接淘汰）
- `rolling_calmar_12m`（近 12 个月滚动 Calmar）
- `lifecycle`: `active` | `watch` | `demoted`
  - 近端滚动垫底且 3y Calmar≤0 → `watch`
  - 连续弱势滚动窗 → `demoted`（不进 Top3 共振 / 不当 Calmar#1）

### 样本外（L1）

- 默认 `holdout_last_years(n=1)`：历史段 / 校准段 / **样本外段（近 1 年）**
- **信号可全历史预热；绩效只统计各段内路径**
- 固定参数策略：历史段=画像，样本外段=可推荐依据
- comparison 行字段 `oos.{train,valid,test}`；`oos_pass` = test Calmar > 0
- 决策：无 OOS pass 且证据等级低于 B 时，**不允许升到「风险开启」**（至多试探）

### 跨 ETF 泛化

- `ResearchService.generalize_strategy` / MCP `research_generalize_strategy`
- 优先用各标的 OOS test Calmar；输出 `positive_calmar_ratio`、`median_calmar`、`pass_count`、`score`、`pass`
- 单 ETF 分析可通过 `attach_cross_etf` 或传入 `cross_etf_by_strategy` 挂 `cross_etf_score`

### 证据等级

| 等级 | 含义 |
|---|---|
| A | 样本外通过 + 跨 ETF 通过 |
| B | 单 ETF 多窗口稳健（且未 demoted） |
| C | 仅全样本历史回测 |
| D | 不足 / demoted / 无可用指标 |

挂在 `comparison[].evidence_grade` 与 `decision.evidence_grade`（偏好集保守下界）。  
**C/D 只能写实验性观察，不得「推荐买入」。**

### 组合决策（角色硬接线）

- 门禁（`dual_momentum` / `ma_60_120` / `adx_ma_trend`）多数看跌 → 强制观望/防御
- 震荡角色仅在 `sideways` 且位于 preferred 时计入
- 择时在门禁允许时主导；输出 `role_votes`

### Walk-forward（可选）

- `research_walk_forward` / `walk_forward_strategy`：滚动前向验证，**非日报默认路径**
- 固定参数策略用于时间稳定性检验；网格搜参见 `grid_search_walk_forward`

## 每日邮件「看图说话」

定时任务 `scripts/run_daily_etf_playbook.py`（或 `python -m app.main research-playbook`）在生成日报时：

1. 对每个成功标的用近端日线绘制 **价格地势** / **RSI** PNG（`matplotlib` Agg）
2. 落盘 `reports/daily/charts/{as_of}/`
3. 邮件 HTML 按「一图一事 + ①②③ 圈点 + 分批 L1→R2 + 决策/信号表」排版
4. SMTP 使用 `multipart/related` **CID 内嵌**图片；PNG 同时作为附件兜底

实现：`app/research/notify/chart_talk.py`、`email_smtp.py`、`playbook.email_body_html`。  
单标的出图失败不阻断整份日报/发信。

## 分钟线说明

读取 `vipdoc/{sh|sz}/minline/*.lc1` 与 `fzline/*.lc5`。

若目录为空（通达信未下载分钟数据），可自动/手动用 **pytdx** 同步：

- **MCP 启动自动同步**：`config.yaml` 中 `auto_sync_minute_on_start: true`（已默认开启），启动时同步观察列表 ETF 的 1m/5m
- **手动 CLI**：

```bash
python -m app.main research-sync-minute sh510210 --freq 1m
python -m app.main research-sync-minute sh510210 --freq 5m
python -m app.main research-minute sh510210 --limit 20
```

MCP：`sync_minute_bars` / `get_minute_bars(auto_sync=true)`。  
pytdx 单次约可拉近端数千根分钟 K，不是通达信全历史；日线研究不依赖分钟线。

## 回测约定

- 信号当日收盘确认，**次日开盘**成交
- 默认佣金 3bp + 滑点 2bp
- 输出：年化、最大回撤、夏普、Calmar、胜率、交易次数、持仓时间占比
- 每个策略额外输出 **当前信号**：`current_signal`（`做多` / `看跌`）与 `current_weight`（截至 `as_of` 收盘的目标仓位）
  - `做多`：目标仓位 > 0（含部分仓）
  - `看跌`：目标仓位 = 0（long-only 下表示空仓，不做空）
- 决策排序优先 **样本外 test Calmar**；`demoted` 策略不参与 Top3 / Calmar#1

## 常规顶底背离（`rsi_divergence` / `macd_divergence`）

- 仅 **Regular** 背离：底背离=价格更低低点 + 指标更高低点；顶背离=价格更高高点 + 指标更低高点
- 枢轴：收盘价左右各 5 根严格极值，确认滞后 5 根；指标取枢轴 bar 上的 RSI(14) 或 MACD DIF
- 开仓：底背离 → 满仓；平仓：顶背离或持仓 ≥ 60 交易日；顶背离在空仓时忽略（不做空）
- 震荡市 `preferred`；强上升市与均值回归一并 `avoid`；不写入 `compute_indicator_snapshot`
