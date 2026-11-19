# AIStockAssistant

数据源可插件化的 A 股决策辅助交易系统（默认通达信本地日频）。

## 快速开始

```bash
cd AIStockAssistant
# 使用上级 venv 或新建
D:\freelife\.venv\Scripts\python.exe -m pip install -r requirements.txt
D:\freelife\.venv\Scripts\python.exe -m pytest -q
```

配置：`config.yaml` 或仓库旁 `env.local.yaml`。默认测试用 `mock`；本机通达信：

```yaml
data:
  provider: tdx_local
  auto_download_on_start: true   # 本地过期时优先 pytdx 增量，失败再 zip
  pytdx_workers: 4
  pytdx_bar_count: 40
  global_enabled: true           # 同一 MCP 内的全球指数/大公司
  tdx:
    vipdoc: "D:\\tdx\\vipdoc"
```

## CLI

```bash
python -m app.main status
python -m app.main bars sh600000
python -m app.main screen --limit 20
python -m app.main recommend sh600000
python -m app.main report
python -m app.main research-status
python -m app.main research-strategies
python -m app.main research-backtest sh510300
python -m app.main research-report --codes sh510050,sh510300
python -m app.main research-playbook --notify-test
python -m app.main research-playbook --sync
# preferred scheduler entry (no PowerShell Tee-Object):
#   .venv\Scripts\python.exe scripts\run_daily_etf_playbook.py
python -m app.tools.sync_eod --dry-run
python -m app.tools.sync_eod --download --force --ingest-limit 30
```

定时日报说明见 [`scripts/README_DAILY_PLAYBOOK.md`](scripts/README_DAILY_PLAYBOOK.md)。

## MCP（Cursor 官方协议）

1. 打开 Cursor Settings → MCP，把 [`docs/mcp.cursor.example.json`](docs/mcp.cursor.example.json) 里的 `ai-stock-assistant` 段合并进你的 MCP 配置。
2. 确保 `config.yaml` 中 `data.provider: tdx_local`（已默认）。
3. 重启 MCP / Cursor 后，在聊天里可直接问：
   - 「分析一下 sh600000 / 浦发银行 600000」
   - 「用 ma_macd_rsi 策略推荐几只股票」
   - 「有哪些选股策略？」

工具（官方 FastMCP，同一 MCP 进程）：

- A 股：`sync_status`、`list_strategies`、`get_daily_bars`、`analyze_stock`、`recommend`、`recommend_by_strategy`、`screen_stocks`、`analyze_portfolio`、`daily_report`
- 全球指数/大公司（Yahoo）：`list_global_universe`、`global_quotes`、`get_global_bars`
- ETF 研究平台（Phase 1+2）：`research_data_status`、`list_research_etfs`、`list_research_strategies`、`research_backtest_etf`、`research_compare_strategies`、`research_daily_report`、`research_generalize_strategy`、`research_walk_forward`、`get_minute_bars`

手动启动校验：

```bash
python -m app.mcp.server
```

## 架构

`Cursor → MCP/CLI → AnalysisService / ResearchService → IDataProvider → tdx_local|mock`

分析不依赖通达信 GUI 登录。开启 `auto_download_on_start` 后，MCP 首次加载若本地 `as_of` 过期，会优先用 pytdx 增量写回 `vipdoc`，失败再尝试官网 `hsjday.zip`。

开启 `auto_sync_minute_on_start` 后，同一启动流程还会用 pytdx 同步观察列表 ETF 的 1 分钟/5 分钟线到 `minline`/`fzline`（默认宽基，含 `sh510210`）；失败不阻断 MCP 启动。

全球行情（标普/纳指/日经/恒生及美股港股龙头等）走同一 MCP 的 `global_quotes`，数据源为 Yahoo Finance（可能延迟）；与 A 股 `tdx_local` 分离。详见 [docs/ENV_SETUP.md](docs/ENV_SETUP.md)。

### ETF 策略研究平台（Phase 1 + Phase 2）

模块：`app/research/`

| 层 | 能力 |
|----|------|
| 数据层 | 通达信日线 + 成交量；分钟线读取 `.lc1`/`.lc5`（本地无文件时返回空） |
| 指标层 | MA/EMA/MACD/RSI/KDJ/ATR/ADX/布林带/RSRS/动量/波动率 |
| 策略层 | 14 个独立策略（均线×3、动量、MACD 交叉、RSI 回归、布林、ATR、ADX、KDJ、RSRS、波动率目标、RSI/MACD 顶底背离） |
| 回测层 | 年化、最大回撤、夏普、Calmar；多窗口 3y/5y/10y、滚动 Calmar、lifecycle；L1 样本外 |
| AI 分析层 | Regime + 候选集、策略对比、证据等级 A–D、门禁角色仓位、跨 ETF 泛化、可选 walk-forward |
| 日报 | Markdown + LLM Prompt；邮件看图说话 |

## 里程碑

- M0 Provider 插件骨架
- M1 TdxLocal + SQLite + EOD sync
- M2 指标/选股/回测/台账/风控/持仓
- M3 MCP + Prompt + 日报
- Phase 1+2 ETF Research Platform（多策略研究/对比/日报 + 样本外/泛化/证据等级）
