# TEST PLAN

单元测试覆盖 Provider、缓存、指标、选股/回测、台账/风控、MCP 工具。

目标：核心路径 pytest 全绿；有通达信 vipdoc 时跑 tdx 集成用例。

```bash
cd AIStockAssistant
pytest -q
```
