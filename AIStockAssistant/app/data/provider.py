from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from app.data.models import Bar, FinanceInfo, SectorInfo, StockInfo, SyncResult


class IDataProvider(ABC):
    """Pluggable market-data contract. Upper layers must not import concrete sources."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_stock_list(self) -> list[StockInfo]:
        raise NotImplementedError

    @abstractmethod
    def get_daily_bars(
        self,
        code: str,
        start: date | None = None,
        end: date | None = None,
    ) -> list[Bar]:
        raise NotImplementedError

    @abstractmethod
    def get_finance(self, code: str) -> FinanceInfo | None:
        raise NotImplementedError

    def get_sectors(self) -> list[SectorInfo]:
        return []

    def get_data_as_of(self) -> date | None:
        return None


class IDataSyncAdapter(ABC):
    """Optional end-of-day sync for a provider."""

    @abstractmethod
    def sync(self) -> SyncResult:
        raise NotImplementedError
