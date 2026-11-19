from __future__ import annotations

from pathlib import Path

import pytest

from app.config.settings import Settings
from app.data.cache import SqliteCache
from app.data.registry import DEFAULT_REGISTRY
from app.data.tdx_day_reader import price_divisor, read_day_file


VIPDOC = Path(r"D:\tdx\vipdoc")


def test_price_divisor_by_instrument() -> None:
    assert price_divisor("sh600000") == 100.0
    assert price_divisor("sz000001") == 100.0
    assert price_divisor("sh000001") == 100.0
    assert price_divisor("sz399001") == 100.0
    assert price_divisor("bj920000") == 100.0
    # equity / bond ETFs and LOFs
    assert price_divisor("sh510050") == 1000.0
    assert price_divisor("sh511010") == 1000.0
    assert price_divisor("sz159915") == 1000.0
    assert price_divisor("sz161725") == 1000.0
    assert price_divisor("sh204001") == 1000.0
    # convertible bonds
    assert price_divisor("sh110059") == 10000.0
    assert price_divisor("sz127045") == 10000.0


@pytest.mark.skipif(not VIPDOC.exists(), reason="tdx vipdoc not present")
def test_tdx_local_read_sample() -> None:
    s = Settings.from_dict(
        {
            "data": {
                "provider": "tdx_local",
                "tdx": {"vipdoc": str(VIPDOC)},
            }
        }
    )
    p = DEFAULT_REGISTRY.create(s)
    assert p.provider_id == "tdx_local"
    bars = p.get_daily_bars("sh600000")
    assert len(bars) > 100
    assert bars[-1].close > 0
    as_of = p.get_data_as_of()
    assert as_of is not None


@pytest.mark.skipif(not VIPDOC.exists(), reason="tdx vipdoc not present")
def test_day_reader_matches_provider(tmp_path: Path) -> None:
    path = VIPDOC / "sh" / "lday" / "sh600000.day"
    bars = read_day_file(path)
    assert bars[-1].trade_date.isoformat() >= "2020-01-01"
    cache = SqliteCache(tmp_path / "c.db")
    n = cache.upsert_bars(bars[-10:], "tdx_local")
    assert n == 10
    loaded = cache.load_bars("sh600000")
    assert len(loaded) == 10


@pytest.mark.skipif(
    not (VIPDOC / "sh" / "lday" / "sh510050.day").exists(),
    reason="sh510050.day not present",
)
def test_etf_price_not_inflated_10x() -> None:
    bars = read_day_file(VIPDOC / "sh" / "lday" / "sh510050.day")
    assert bars
    close = bars[-1].close
    # 上证50ETF trades around a few yuan, never tens of yuan.
    assert 1.0 < close < 10.0
    stock = read_day_file(VIPDOC / "sh" / "lday" / "sh600000.day")
    assert stock[-1].close > 1.0
