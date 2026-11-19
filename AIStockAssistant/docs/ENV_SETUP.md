# AIStockAssistant — 环境搭建

目标：本机具备「通达信本地日线可读」+「Python 工程可跑」+「Cursor 能调到分析工具」。

## 必备软件

| 软件 | 用途 |
|------|------|
| Windows 10/11 | 通达信运行环境 |
| 通达信个人版 PC | 维护 `vipdoc`（分析本身不要求 GUI 登录） |
| Python 3.11 | 运行本工程 |
| uv 或 pip | 依赖管理 |
| Git | 版本管理 |
| Cursor | IDE + MCP 调用 |

## 通达信与数据

1. 安装通达信到例如 `D:\tdx`（本机已验证路径）。
2. **首次**准备历史日线（仍需一次全量包；日常不必开 GUI）：
   - 软件内「盘后数据下载」，或
   - 官网包：`https://data.tdx.com.cn/vipdoc/hsjday.zip` 解压到 `{tdx.root}/vipdoc`（浏览器下载；程序内 zip 可能被反爬拦截）
3. 目录验收：

```text
{tdx.root}/vipdoc/sh/lday/*.day
{tdx.root}/vipdoc/sz/lday/*.day
```

4. 分析读本地文件，**不需要**保持通达信登录。
5. 日常自动更新（可选）：`data.auto_download_on_start: true` 时，进程首次加载按**已收盘会话**同步日线：
   1. 用 `eod_hour`/`eod_minute`（默认 16:00）判断「上一完整交易日」；盘中不写当日未完成 K
   2. 本地缺该日 → pytdx 拉取并写盘（单日相对昨收跳变过大则拒写）
   3. 本地已有该日 → 再拉一份做交叉复核；一致则不写盘，不一致且 HQ 连续性格局合格则修复写盘
   4. **失败再**尝试官网 `hsjday.zip`（带 UA/校验；反爬 HTML 会被拒绝）
   5. 失败不阻塞 MCP 启动
6. 分钟线自动更新（可选）：`data.auto_sync_minute_on_start: true` 时，启动同步观察列表 ETF 的 `.lc1`/`.lc5`（`minute_sync_codes` / `minute_sync_freqs` / `minute_sync_bar_count` 可配；失败不阻塞启动）

也可手动：

```bash
python -m app.tools.sync_eod --download --force
python -m app.main research-sync-minute sh510210 --freq 1m
```

相关配置：`pytdx_workers`（默认 4）、`pytdx_bar_count`（默认 40）、`auto_sync_minute_on_start`。

## Python

```bash
cd AIStockAssistant
# 推荐使用 freelife 根目录已有 venv，或：
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

配置：复制或编辑仓库根/`env.local.yaml`，或设置环境变量 / `AIStockAssistant/config.yaml`：

```yaml
data:
  provider: tdx_local   # 或 mock
  auto_download_on_start: true
  auto_sync_minute_on_start: true
  pytdx_workers: 4
  pytdx_bar_count: 40
  tdx:
    root: "D:\\tdx"
    vipdoc: "D:\\tdx\\vipdoc"
```

## 验收

```bash
pytest -q
python -m app.tools.sync_eod --dry-run
# 价格缩放 / OHLC 冒烟（拦住 ETF 被放大 10 倍这类问题）
python -m app.tools.smoke_tdx
pytest -q -m smoke
```

合成用例（不依赖本机 vipdoc）在 `tests/test_smoke_tdx_prices.py`，每次 `pytest` 都会跑；
有通达信数据时再跑 `-m smoke` 或 `smoke_tdx`，用真实锚点（如 `sh510050`∈[1,10]）复核。

## 全球行情（同一 MCP，无需另开）

依赖：`yfinance`（见 `requirements.txt`）。配置 `data.global_enabled: true`（默认开）。

最小观察池：美欧亚太主要指数（`^GSPC`/`^IXIC`/`^DJI`/`^STOXX50E`/`^GDAXI`/`^FTSE`/`^N225`/`^HSI`）+ 大公司（AAPL/MSFT/NVDA/GOOGL/AMZN/META/TSLA/0700.HK/BABA）。

MCP 工具（与 A 股共用 `ai-stock-assistant`）：

- `list_global_universe` — 列出观察池（可按 `region`/`kind` 过滤）
- `global_quotes` — 最新价/涨跌（可 `symbols_csv=标普,AAPL`）
- `get_global_bars` — 日线 OHLCV

注意：Yahoo 可能限流或延迟；失败时工具返回 `ok=false`，勿编造行情。

## Cursor MCP（官方 SDK）

将 [`mcp.cursor.example.json`](mcp.cursor.example.json) 合并到 Cursor MCP 配置后重启（**不要**再配第二个全球行情 MCP）：

- 问个股：会调用 `analyze_stock` / `get_daily_bars`
- 按策略荐股：先 `list_strategies`，再 `recommend_by_strategy`
- 策略 id：`ma_macd_rsi`（默认）、`ma_trend`、`rsi_mid`
- 问美股/指数：`global_quotes` / `get_global_bars` / `list_global_universe`
