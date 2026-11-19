# IDataProvider

可插件数据源契约（实现见 `AIStockAssistant/app/data/provider.py`）。

必选：
- `provider_id: str`
- `get_stock_list() -> list[StockInfo]`
- `get_daily_bars(code, start=None, end=None) -> list[Bar]`
- `get_finance(code) -> FinanceInfo | None`

扩展：
- `get_sectors() -> list[SectorInfo]`
- `get_data_as_of() -> date | None`

同步（可选 IDataSyncAdapter）：
- `sync() -> SyncResult`

默认实现：`tdx_local`；测试：`mock`；可扩展 `pytdx` / `akshare`。
