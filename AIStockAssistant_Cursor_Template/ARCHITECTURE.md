# ARCHITECTURE

分层：UI/Cursor → AI(MCP) → Service → IDataProvider → TdxLocal / Mock / (Pytdx|AKShare 可扩展)

要求：
- 依赖倒置、Provider 可插拔、禁止跨层调用
- AI 不直接访问 pytdx / 通达信文件
- 配置 `data.provider` + ProviderRegistry 切换数据源
- EOD：DataSyncJob → IDataSyncAdapter（按当前 provider）→ SQLite
