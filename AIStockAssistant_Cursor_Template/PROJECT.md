# PROJECT

目标：构建 AIStockAssistant — 数据源可插件化的 A 股决策辅助交易系统（默认通达信本地日频）。

原则：
- IDataProvider 可插拔；上层不写死通达信
- 日频 EOD，收盘后定时同步；分析不依赖 GUI 登录
- 买卖有依据：规则 + 回测 + 决策台账
- 目标年化 5%–10%；Cursor MCP 为 AI 入口

里程碑：
- M0 地基（接口/Mock）
- M1 通达信本地 + SQLite + EOD Sync
- M2 指标/选股/回测/台账/风控/持仓
- M3 Cursor MCP / Prompt / 自然语言
- M4 可选扩展（其它 Provider / Streamlit）
