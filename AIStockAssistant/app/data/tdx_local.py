from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from app.data.models import Bar, FinanceInfo, SectorInfo, StockInfo
from app.data.provider import IDataProvider
from app.data.tdx_day_reader import filter_bars, read_day_file

logger = logging.getLogger(__name__)

MARKETS = ("sh", "sz", "bj")


class TdxLocalProvider(IDataProvider):
    """Read Tongdaxin local vipdoc .day files. Does not require GUI login."""

    def __init__(self, vipdoc: Path) -> None:
        self.vipdoc = Path(vipdoc)
        self._list_cache: list[StockInfo] | None = None

    @property
    def provider_id(self) -> str:
        return "tdx_local"

    def get_stock_list(self) -> list[StockInfo]:
        if self._list_cache is not None:
            return list(self._list_cache)
        stocks: list[StockInfo] = []
        for market in MARKETS:
            lday = self.vipdoc / market / "lday"
            if not lday.is_dir():
                continue
            for path in sorted(lday.glob("*.day")):
                code = path.stem.lower()
                stocks.append(StockInfo(code=code, name="", market=market))
        self._list_cache = stocks
        logger.info("tdx stock list size=%s", len(stocks))
        return list(stocks)

    def _day_path(self, code: str) -> Path | None:
        code = code.lower()
        market = code[:2] if code[:2] in MARKETS else None
        if market:
            path = self.vipdoc / market / "lday" / f"{code}.day"
            return path if path.is_file() else None
        for m in MARKETS:
            path = self.vipdoc / m / "lday" / f"{m}{code}.day"
            if path.is_file():
                return path
            path2 = self.vipdoc / m / "lday" / f"{code}.day"
            if path2.is_file():
                return path2
        return None

    def get_daily_bars(
        self,
        code: str,
        start: date | None = None,
        end: date | None = None,
    ) -> list[Bar]:
        path = self._day_path(code)
        if path is None:
            return []
        bars = read_day_file(path)
        return filter_bars(bars, start, end)

    def get_finance(self, code: str) -> FinanceInfo | None:
        # Financial binary packs live under vipdoc/cw; optional and often empty.
        cw = self.vipdoc / "cw"
        if not cw.is_dir() or not any(cw.iterdir()):
            return FinanceInfo(code=code.lower(), extras={"note": "cw empty"})
        return FinanceInfo(code=code.lower(), extras={"cw_present": True})

    def get_sectors(self) -> list[SectorInfo]:
        # Minimal: expose markets as pseudo-sectors for v1.
        result: list[SectorInfo] = []
        for market in MARKETS:
            codes = tuple(
                s.code for s in self.get_stock_list() if s.market == market
            )
            if codes:
                result.append(SectorInfo(name=market, codes=codes[:50]))
        return result

    def get_data_as_of(self) -> date | None:
        # Sample a few liquid names for freshness.
        samples = ("sh000001", "sz399001", "sh600000", "sz000001")
        latest: date | None = None
        for code in samples:
            bars = self.get_daily_bars(code)
            if bars:
                d = bars[-1].trade_date
                if latest is None or d > latest:
                    latest = d
        return latest
