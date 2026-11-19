from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from app.data.models import Bar, MinuteBar
from app.data.provider import IDataProvider
from app.data.tdx_minute_reader import filter_minute_bars, read_minute_file
from app.data.tdx_minute_writer import minute_path_for
from app.research.data.etf_universe import RESEARCH_ETFS


class ResearchDataFeed:
    """Research-facing data access: daily via IDataProvider, minute via vipdoc."""

    def __init__(
        self,
        provider: IDataProvider,
        vipdoc: Path | None = None,
    ) -> None:
        self.provider = provider
        self.vipdoc = Path(vipdoc) if vipdoc else None

    @property
    def provider_id(self) -> str:
        return self.provider.provider_id

    def as_of(self) -> date | None:
        return self.provider.get_data_as_of()

    def daily_bars(
        self,
        code: str,
        start: date | None = None,
        end: date | None = None,
    ) -> list[Bar]:
        return self.provider.get_daily_bars(code, start=start, end=end)

    def volume_series(
        self,
        code: str,
        start: date | None = None,
        end: date | None = None,
    ) -> list[tuple[date, float, float]]:
        bars = self.daily_bars(code, start=start, end=end)
        return [(b.trade_date, b.volume, b.amount) for b in bars]

    def resolve_minute_path(self, code: str, freq: str = "1m") -> Path | None:
        if self.vipdoc is None:
            return None
        return minute_path_for(self.vipdoc, code, freq=freq)

    def _minute_path(self, code: str, freq: str = "1m") -> Path | None:
        path = self.resolve_minute_path(code, freq=freq)
        if path is None or not path.is_file() or path.stat().st_size <= 0:
            return None
        return path

    def minute_bars(
        self,
        code: str,
        freq: str = "1m",
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[MinuteBar]:
        path = self._minute_path(code, freq=freq)
        if path is None:
            return []
        bars = read_minute_file(path, code=code.lower())
        return filter_minute_bars(bars, start=start, end=end)

    def minute_available(self, code: str, freq: str = "1m") -> bool:
        path = self._minute_path(code, freq=freq)
        return path is not None

    def data_status(self, codes: list[str] | None = None) -> dict:
        codes = codes or [e.code for e in RESEARCH_ETFS]
        rows = []
        for code in codes:
            daily = self.daily_bars(code)
            rows.append(
                {
                    "code": code,
                    "daily_bars": len(daily),
                    "daily_as_of": daily[-1].trade_date.isoformat() if daily else None,
                    "minute_1m": self.minute_available(code, "1m"),
                    "minute_5m": self.minute_available(code, "5m"),
                    "last_volume": daily[-1].volume if daily else None,
                    "last_amount": daily[-1].amount if daily else None,
                }
            )
        return {
            "provider_id": self.provider_id,
            "as_of": self.as_of().isoformat() if self.as_of() else None,
            "vipdoc": str(self.vipdoc) if self.vipdoc else None,
            "instruments": rows,
        }
