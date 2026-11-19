"""Rich in-memory provider for selection unit tests."""

from __future__ import annotations

from datetime import date, timedelta

from app.data.models import Bar, FinanceInfo, SectorInfo, StockInfo
from app.data.provider import IDataProvider


class SelectionMockProvider(IDataProvider):
    """~20 names, 400 trading days, distinct momentum profiles."""

    def __init__(self, n_days: int = 400) -> None:
        self._stocks = [
            StockInfo(code="sh600519", name="贵州茅台", market="sh"),
            StockInfo(code="sz300750", name="宁德时代", market="sz"),
            StockInfo(code="sh600036", name="招商银行", market="sh"),
            StockInfo(code="sz000858", name="五粮液", market="sz"),
            StockInfo(code="sz002594", name="比亚迪", market="sz"),
            StockInfo(code="sh601318", name="中国平安", market="sh"),
            StockInfo(code="sz000333", name="美的集团", market="sz"),
            StockInfo(code="sh600887", name="伊利股份", market="sh"),
            StockInfo(code="sz002415", name="海康威视", market="sz"),
            StockInfo(code="sh601012", name="隆基绿能", market="sh"),
            StockInfo(code="sz000001", name="平安银行", market="sz"),
            StockInfo(code="sh600030", name="中信证券", market="sh"),
            StockInfo(code="sz300014", name="亿纬锂能", market="sz"),
            StockInfo(code="sz002230", name="科大讯飞", market="sz"),
            StockInfo(code="sh600900", name="长江电力", market="sh"),
            StockInfo(code="sh510300", name="沪深300ETF", market="sh"),
        ]
        # Drift / vol profiles by code
        profiles = {
            "sh600519": (0.0012, 0.008, 1800.0),
            "sz300750": (0.0018, 0.018, 220.0),
            "sh600036": (0.0006, 0.010, 40.0),
            "sz000858": (0.0010, 0.012, 160.0),
            "sz002594": (0.0015, 0.016, 280.0),
            "sh601318": (0.0004, 0.011, 50.0),
            "sz000333": (0.0008, 0.012, 70.0),
            "sh600887": (0.0005, 0.009, 30.0),
            "sz002415": (0.0003, 0.014, 35.0),
            "sh601012": (-0.0002, 0.020, 25.0),
            "sz000001": (0.0004, 0.012, 12.0),
            "sh600030": (0.0007, 0.015, 28.0),
            "sz300014": (0.0011, 0.019, 55.0),
            "sz002230": (0.0009, 0.017, 48.0),
            "sh600900": (0.0003, 0.006, 25.0),
            "sh510300": (0.0005, 0.010, 4.0),
        }
        base = date(2024, 1, 2)
        self._bars: dict[str, list[Bar]] = {}
        for stock in self._stocks:
            drift, vol, px = profiles[stock.code]
            bars: list[Bar] = []
            d = base
            i = 0
            while len(bars) < n_days:
                if d.weekday() < 5:
                    # deterministic pseudo-vol
                    shock = ((i % 7) - 3) * vol * 0.4 + drift
                    px = max(1.0, px * (1.0 + shock))
                    amt = px * (2_000_000 + (i % 50) * 50_000) * (10 if stock.code != "sh510300" else 1)
                    bars.append(
                        Bar(
                            code=stock.code,
                            trade_date=d,
                            open=px * 0.995,
                            high=px * 1.01,
                            low=px * 0.99,
                            close=round(px, 2),
                            volume=amt / px,
                            amount=amt,
                        )
                    )
                    i += 1
                d += timedelta(days=1)
            self._bars[stock.code] = bars

        self._finance = {
            "sh600519": FinanceInfo("sh600519", pe=28, pb=9.5, roe=0.30, extras={"profit_cagr": 0.12}),
            "sz300750": FinanceInfo("sz300750", pe=22, pb=4.0, roe=0.18, extras={"profit_cagr": 0.20}),
            "sh600036": FinanceInfo("sh600036", pe=7.5, pb=1.0, roe=0.16, extras={"profit_cagr": 0.08}),
            "sz000858": FinanceInfo("sz000858", pe=18, pb=4.5, roe=0.22, extras={"profit_cagr": 0.10}),
        }

    @property
    def provider_id(self) -> str:
        return "selection_mock"

    def get_stock_list(self) -> list[StockInfo]:
        return list(self._stocks)

    def get_daily_bars(
        self,
        code: str,
        start: date | None = None,
        end: date | None = None,
    ) -> list[Bar]:
        bars = self._bars.get(code.lower(), [])
        return [
            b
            for b in bars
            if (start is None or b.trade_date >= start)
            and (end is None or b.trade_date <= end)
        ]

    def get_finance(self, code: str) -> FinanceInfo | None:
        return self._finance.get(code.lower())

    def get_sectors(self) -> list[SectorInfo]:
        return [SectorInfo(name="mock", codes=tuple(s.code for s in self._stocks))]

    def get_data_as_of(self) -> date | None:
        return self._bars["sh600519"][-1].trade_date
