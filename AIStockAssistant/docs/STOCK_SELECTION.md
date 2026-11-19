# 指数成分股七层选股引擎

与 ETF 策略研究平台（`app/research/`）平行：本引擎在上证50 / 沪深300 / 中证500 成分股上做横截面选股，输出 Top10 与可核对证据链。

口径：**研究观察，非正式投资建议**。`evidence_grade` 为 C/D 时强制实验性观察口吻。

## 与 ETF 平台的关系

| | ETF `research_*` | 选股 `selection_*` |
|---|---|---|
| 标的 | 宽基/QDII ETF | 指数成分股 |
| 问题 | 择时 / 仓位档位 | 横截面选 Top10 |
| 规则 | `etf-research-platform.mdc` | `stock-selection-platform.mdc` |

旧工具 `screen_stocks` / `recommend` **不能替代**本引擎。

## 目录

```
app/selection/
  universe/      # L1 成分股缓存
  filters/       # L2 过滤
  factors/       # L3 单因子 + 合成
  rank/          # L4 TopN
  explain/       # L5 结构化理由
  evidence/      # L6 证据链
  validation/    # L7 IC / lifecycle
  meta/          # ST/财务/资金/行业元数据
  service.py
  report.py
data/universe/   # sse50 / csi300 / csi500 JSON
```

## 七层契约

1. **L1 Universe** — 三指数并集去重，日频 `as_of`
2. **L2 Filters** — ST / 停牌 / 上市不足一年 / 低成交额 / 缺行情
3. **L3 Factors** — 八类 0–100 百分位分；仅 L7 `active` 因子加权
4. **L4 Rank** — Top10；同行业上限默认 3
5. **L5 Explain** — `reasons[]`（条件句+数值），禁止空话推荐
6. **L6 Evidence** — claim / source / verify_method / stats；`evidence_grade` A–D
7. **L7 Validation** — IC、RankIC、分层组合、regime 分桶、lifecycle

## 因子分期

| Phase | 因子 | 数据 |
|---|---|---|
| 1 | 趋势、动量、波动、风险、相对强弱、流动性 | 通达信日线 |
| 2 | （权重由 L7 决定） | 横截面 IC 管道 |
| 3 | 价值、质量 | `finance_cache.json`（eps/bps/roe）+ 本地收盘价现算 PE/PB |
| 4 | 资金、行业、宏观 | capital_flow / sectors / ETF regime |

缺数据：`status=unavailable`，不参与加权，报告「数据缺口」列出。

### Phase3 财务数据流

```text
日频同步:  pytdx get_finance_info → data/universe/finance_cache.json
           存 eps / bps / roe / updated_date（不编造 profit_cagr）
分析时:    本地 as_of 收盘价 + eps/bps → PE/PB → value_ep / value_bp
           ROE / 已有 seed 的 profit_cagr 直读 cache
跑批:      selection_run_daily 不实时打 pytdx
个股研报:  cache miss 时单票 get_finance_info 回退并写回 cache
```

- CLI：`python -m app.main selection-sync-finance`
- 配置：
  - `data.sync_finance_with_day`（默认 true）：**日线 vipdoc 刷新成功后**自动更新 `finance_cache`（与 K 线同节奏）
  - `data.auto_sync_finance_on_start`（默认 false）：日线已新鲜未刷新时，MCP 启动仍单独拉财务
  - `data.finance_sync_workers`
- `selection_data_status.meta` 含 `finance_cache_count` / `finance_coverage` / `finance_synced_at`
- `quality_cagr` 需多期利润，单次财务快照算不出；缺则 unavailable，勿叙事补全

## MCP

- `selection_data_status`
- `selection_universe`
- `selection_run_daily`
- `selection_stock_report`
- `selection_factor_validation`
- `selection_daily_report`

## CLI

```bash
python -m app.main selection-status
python -m app.main selection-universe
python -m app.main selection-run
python -m app.main selection-report sh600519
python -m app.main selection-validate
python -m app.main selection-sync-universe
python -m app.main selection-sync-finance
```

## L1 成分库同步与调样

本地 `data/universe/{sse50,csi300,csi500}.json` 是选股并集的权威缓存。

**同步优先级**（`selection-sync-universe` / `sync_index_constituents`）：

1. 通达信板块文件（若本机 `T0002/blocknew` 等有完整指数板块）
2. **中证指数官网**官方成分表 `*cons.xls`（`000016` / `000300` / `000905`）
3. 两者都失败则保留旧文件并标 `stale=true`（不会清空）

期望规模：上证50≈50、沪深300≈300、中证500≈500；三指数**并集去重**约 **800**（上证50⊂沪深300，300∩500≈空），不是 850。

**指数调样怎么办？**

| 事项 | 说明 |
|---|---|
| 谁调 | 中证指数公司（上证50 由上交所/中证体系发布，成分表同样走官网 cons） |
| 节奏 | 通常每年 **2 次定期调整**：约 5 月末 / 11 月末公告，**6 月中旬 / 12 月中旬收盘后生效**；另有临时调整 |
| 本地动作 | 生效日后（或公告日后想预演时）重新跑 `python -m app.main selection-sync-universe` |
| 效果 | 覆盖三个 JSON 的 `codes` / `as_of` / `source`；之后 `selection_run_daily` 自动用新并集 |
| 财务缓存 | 成分变多后建议再跑 `selection-sync-finance`，否则新票价值/质量因子易 unavailable |
| 研报口径 | 调出样本：不再进 L1，自然跌出 Top10；调入样本：次日同步后才参与横截面 |

检查是否同步成功：`selection_data_status` / `selection_universe` 看各指数 `count` 与 `source`（应为 `csindex_cons` 或 `tdx_block`，且 `stale=false`）。

## Qbot 借鉴

- **借**：因子→验证→入库；选股/择时/风控分层；文档化假设
- **不借**：整仓 GUI、实盘、把 LLM 当选股主引擎
- **本地强化**：L6 证据行 + L7 因子 lifecycle

## 证据等级（个股结论）

| 等级 | 含义 |
|---|---|
| A | 入选因子多数 OOS/IC 稳健 + 历史同类信号样本充足 |
| B | 主要因子 active 且近端 IC 方向一致 |
| C | 仅全样本/当期横截面分（Phase1 默认上限） |
| D | 关键因子 demoted / 数据严重不足 |
