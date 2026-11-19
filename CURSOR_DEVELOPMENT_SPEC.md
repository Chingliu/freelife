# CURSOR_DEVELOPMENT_SPEC（对齐落地计划）

## 项目目标
数据源可插件化的 A 股决策辅助交易系统：通达信本地日频默认 + EOD 同步 + 规则/回测依据 + Cursor MCP。

## 技术栈
Python 3.11, uv/pip, pandas, numpy, pytdx(可选), pytest, ruff, black, mypy, SQLite, MCP

## 目录
```text
AIStockAssistant/
├── app/{ai,config,data,indicators,strategy,journal,risk,portfolio,mcp,tools}
├── tests/ docs/ data/
├── requirements.txt README.md
```

## 原则
1. IDataProvider 可插拔
2. AI 不直接访问数据源实现
3. 模块可单测；≤300 行/模块
4. 禁止跨层调用

## 里程碑 Sprint
见 AIStockAssistant_Cursor_Template/TASKS.md（M0–M3）
