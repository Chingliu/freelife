from __future__ import annotations

from datetime import date, timedelta

from app.data.models import Bar, FinanceInfo, SectorInfo, StockInfo, SyncResult
from app.data.provider import IDataProvider, IDataSyncAdapter


class MockProvider(IDataProvider):
    """Deterministic in-memory provider for unit tests."""

    def __init__(self) -> None:
        self._stocks = [
            StockInfo(code="sh600000", name="浦发银行", market="sh"),
            StockInfo(code="sz000001", name="平安银行", market="sz"),
            StockInfo(code="sh000001", name="上证指数", market="sh"),
        ]
        base = date(2024, 1, 2)
        self._bars: dict[str, list[Bar]] = {}
        for stock in self._stocks:
            bars: list[Bar] = []
            price = 10.0
            for i in range(60):
                d = base + timedelta(days=i)
                if d.weekday() >= 5:
                    continue
                price = round(price * (1.0 + (0.01 if i % 3 else -0.005)), 2)
                bars.append(
                    Bar(
                        code=stock.code,
                        trade_date=d,
                        open=price - 0.1,
                        high=price + 0.2,
                        low=price - 0.2,
                        close=price,
                        volume=1_000_000 + i * 1000,
                        amount=price * 1_000_000,
                    )
                )
            self._bars[stock.code] = bars

    @property
    def provider_id(self) -> str:
        return "mock"

    def get_stock_list(self) -> list[StockInfo]:
        return list(self._stocks)

    def get_daily_bars(
        self,
        code: str,
        start: date | None = None,
        end: date | None = None,
    ) -> list[Bar]:
        bars = self._bars.get(code, [])
        return [
            b
            for b in bars
            if (start is None or b.trade_date >= start)
            and (end is None or b.trade_date <= end)
        ]

    def get_finance(self, code: str) -> FinanceInfo | None:
        if code not in self._bars:
            return None
        return FinanceInfo(code=code, pe=8.5, pb=0.7, roe=0.12)

    def get_sectors(self) -> list[SectorInfo]:
        return [
            SectorInfo(name="银行", codes=("sh600000", "sz000001")),
        ]

    def get_data_as_of(self) -> date | None:
        latest: date | None = None
        for bars in self._bars.values():
            if bars:
                d = bars[-1].trade_date
                if latest is None or d > latest:
                    latest = d
        return latest


class MockSyncAdapter(IDataSyncAdapter):
    def __init__(self, provider: MockProvider) -> None:
        self._provider = provider

    def sync(self) -> SyncResult:
        as_of = self._provider.get_data_as_of()
        return SyncResult(
            ok=True,
            message="mock sync noop",
            as_of=as_of,
            source="mock",
        )
