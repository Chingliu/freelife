from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

from app.data.models import Bar
from app.data.pytdx_updater import _update_one
from app.data.tdx_day_reader import read_day_file
from app.data.tdx_day_writer import append_day_bars


def _bar(code: str, d: date, close: float, volume: float = 100_000_000.0) -> Bar:
    return Bar(
        code=code,
        trade_date=d,
        open=close,
        high=close + 0.01,
        low=close - 0.01,
        close=close,
        volume=volume,
        amount=close * volume,
    )


def _row(d: date, close: float, vol: float = 1_000_000.0) -> dict:
    return {
        "year": d.year,
        "month": d.month,
        "day": d.day,
        "open": close,
        "high": close + 0.01,
        "low": close - 0.01,
        "close": close,
        "vol": vol,
        "amount": close * vol * 100.0,
    }


def test_update_one_verify_ok_no_write(tmp_path: Path) -> None:
    code = "sh513500"
    path = tmp_path / "sh" / "lday" / f"{code}.day"
    # volumes already in share units (pytdx hands * 100)
    append_day_bars(
        path,
        [
            _bar(code, date(2026, 7, 23), 2.524, volume=127_549_000),
            _bar(code, date(2026, 7, 24), 2.506, volume=103_375_200),
            _bar(code, date(2026, 7, 27), 2.520, volume=114_222_200),
        ],
        code=code,
    )
    api = MagicMock()
    api.get_security_bars.return_value = [
        _row(date(2026, 7, 23), 2.524, vol=1_275_490),
        _row(date(2026, 7, 24), 2.506, vol=1_033_752),
        _row(date(2026, 7, 27), 2.520, vol=1_142_222),
    ]
    n = _update_one(api, path, bar_count=10, target_as_of=date(2026, 7, 27))
    assert n == 0


def test_update_one_repairs_corrupt_and_skips_today(tmp_path: Path) -> None:
    code = "sh513500"
    path = tmp_path / "sh" / "lday" / f"{code}.day"
    append_day_bars(
        path,
        [
            _bar(code, date(2026, 7, 23), 2.524),
            _bar(code, date(2026, 7, 24), 0.417),  # corrupt
            _bar(code, date(2026, 7, 27), 2.509, volume=35_588_900),  # incomplete
            _bar(code, date(2026, 7, 28), 2.495),  # unformed session at 10:00
        ],
        code=code,
    )
    api = MagicMock()
    api.get_security_bars.return_value = [
        _row(date(2026, 7, 23), 2.524, vol=1_275_490),
        _row(date(2026, 7, 24), 2.506, vol=1_033_752),
        _row(date(2026, 7, 27), 2.520, vol=1_142_222),
        _row(date(2026, 7, 28), 2.495, vol=449_686),  # must not be written
    ]
    n = _update_one(api, path, bar_count=10, target_as_of=date(2026, 7, 27))
    assert n >= 1
    bars = read_day_file(path, code=code)
    assert bars[-1].trade_date == date(2026, 7, 27)
    assert abs(bars[-2].close - 2.506) < 1e-6  # repaired
    assert abs(bars[-1].close - 2.520) < 1e-6
    assert all(b.trade_date <= date(2026, 7, 27) for b in bars)


def test_update_one_rejects_bad_hq_spike(tmp_path: Path) -> None:
    code = "sh513500"
    path = tmp_path / "sh" / "lday" / f"{code}.day"
    append_day_bars(
        path,
        [
            _bar(code, date(2026, 7, 23), 2.524, volume=127_549_000),
            _bar(code, date(2026, 7, 24), 2.506, volume=103_375_200),
        ],
        code=code,
    )
    api = MagicMock()
    api.get_security_bars.return_value = [
        _row(date(2026, 7, 23), 2.524, vol=1_275_490),
        _row(date(2026, 7, 24), 0.417, vol=887_664),  # bad HQ
    ]
    n = _update_one(api, path, bar_count=10, target_as_of=date(2026, 7, 24))
    assert n == 0
    bars = read_day_file(path, code=code)
    assert abs(bars[-1].close - 2.506) < 1e-6  # local kept
