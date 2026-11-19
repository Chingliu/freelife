from __future__ import annotations

import logging
import sqlite3
from datetime import date
from pathlib import Path

from app.data.models import Bar, StockInfo
from app.data.provider import IDataProvider

logger = logging.getLogger(__name__)


class SqliteCache:
    """Provider-agnostic SQLite bar cache."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS stocks (
                    code TEXT PRIMARY KEY,
                    name TEXT,
                    market TEXT
                );
                CREATE TABLE IF NOT EXISTS bars (
                    code TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    open REAL, high REAL, low REAL, close REAL,
                    volume REAL, amount REAL,
                    source TEXT,
                    PRIMARY KEY (code, trade_date)
                );
                """
            )

    def set_meta(self, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO meta(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def get_meta(self, key: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM meta WHERE key=?", (key,)
            ).fetchone()
            return None if row is None else str(row["value"])

    def upsert_stocks(self, stocks: list[StockInfo]) -> None:
        with self._connect() as conn:
            conn.executemany(
                "INSERT INTO stocks(code,name,market) VALUES(?,?,?) "
                "ON CONFLICT(code) DO UPDATE SET name=excluded.name, "
                "market=excluded.market",
                [(s.code, s.name, s.market) for s in stocks],
            )

    def upsert_bars(self, bars: list[Bar], source: str) -> int:
        if not bars:
            return 0
        with self._connect() as conn:
            conn.executemany(
                "INSERT INTO bars(code,trade_date,open,high,low,close,"
                "volume,amount,source) VALUES(?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(code,trade_date) DO UPDATE SET "
                "open=excluded.open, high=excluded.high, low=excluded.low, "
                "close=excluded.close, volume=excluded.volume, "
                "amount=excluded.amount, source=excluded.source",
                [
                    (
                        b.code,
                        b.trade_date.isoformat(),
                        b.open,
                        b.high,
                        b.low,
                        b.close,
                        b.volume,
                        b.amount,
                        source,
                    )
                    for b in bars
                ],
            )
        return len(bars)

    def load_bars(
        self,
        code: str,
        start: date | None = None,
        end: date | None = None,
    ) -> list[Bar]:
        sql = "SELECT * FROM bars WHERE code=?"
        params: list[object] = [code]
        if start:
            sql += " AND trade_date>=?"
            params.append(start.isoformat())
        if end:
            sql += " AND trade_date<=?"
            params.append(end.isoformat())
        sql += " ORDER BY trade_date"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            Bar(
                code=str(r["code"]),
                trade_date=date.fromisoformat(str(r["trade_date"])),
                open=float(r["open"]),
                high=float(r["high"]),
                low=float(r["low"]),
                close=float(r["close"]),
                volume=float(r["volume"]),
                amount=float(r["amount"] or 0),
            )
            for r in rows
        ]

    def ingest_provider(
        self,
        provider: IDataProvider,
        codes: list[str] | None = None,
        limit: int | None = None,
    ) -> int:
        stocks = provider.get_stock_list()
        self.upsert_stocks(stocks)
        targets = codes or [s.code for s in stocks]
        if limit is not None:
            targets = targets[:limit]
        total = 0
        for code in targets:
            bars = provider.get_daily_bars(code)
            total += self.upsert_bars(bars, provider.provider_id)
        as_of = provider.get_data_as_of()
        if as_of:
            self.set_meta("last_synced_trade_date", as_of.isoformat())
        self.set_meta("last_provider", provider.provider_id)
        logger.info("ingested bars=%s provider=%s", total, provider.provider_id)
        return total
