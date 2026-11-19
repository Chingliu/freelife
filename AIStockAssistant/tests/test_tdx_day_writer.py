from __future__ import annotations

from datetime import date
from pathlib import Path

from app.data.models import Bar
from app.data.tdx_day_reader import read_day_file
from app.data.tdx_day_writer import append_day_bars, last_trade_date, upsert_day_bars


def _bar(code: str, d: date, close: float = 10.0, volume: float = 100000.0) -> Bar:
    return Bar(
        code=code,
        trade_date=d,
        open=close,
        high=close + 0.1,
        low=close - 0.1,
        close=close,
        volume=volume,
        amount=1_000_000.0,
    )


def test_append_and_read_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "sh" / "lday" / "sh600000.day"
    code = "sh600000"
    n1 = append_day_bars(
        path,
        [_bar(code, date(2026, 7, 21), 8.95), _bar(code, date(2026, 7, 22), 9.01)],
        code=code,
    )
    assert n1 == 2
    assert last_trade_date(path) == date(2026, 7, 22)

    n2 = append_day_bars(
        path,
        [
            _bar(code, date(2026, 7, 22), 9.01),  # duplicate date ignored
            _bar(code, date(2026, 7, 23), 9.05),
        ],
        code=code,
    )
    assert n2 == 1
    bars = read_day_file(path, code=code)
    assert [b.trade_date for b in bars] == [
        date(2026, 7, 21),
        date(2026, 7, 22),
        date(2026, 7, 23),
    ]
    assert abs(bars[-1].close - 9.05) < 1e-6
    assert bars[-1].volume == 100000.0


def test_upsert_rewrites_corrupt_and_incomplete_bars(tmp_path: Path) -> None:
    path = tmp_path / "sh" / "lday" / "sh510050.day"
    code = "sh510050"
    append_day_bars(
        path,
        [
            _bar(code, date(2026, 7, 23), 3.084, volume=585_833_130),
            _bar(code, date(2026, 7, 24), 1.744, volume=24_300),  # corrupt
            _bar(code, date(2026, 7, 27), 3.048, volume=195_991_300),  # incomplete
        ],
        code=code,
    )

    n = upsert_day_bars(
        path,
        [
            _bar(code, date(2026, 7, 24), 3.05, volume=952_270_700),
            _bar(code, date(2026, 7, 27), 3.054, volume=597_003_600),
        ],
        code=code,
    )
    assert n == 2
    bars = read_day_file(path, code=code)
    assert [b.trade_date for b in bars] == [
        date(2026, 7, 23),
        date(2026, 7, 24),
        date(2026, 7, 27),
    ]
    assert abs(bars[1].close - 3.05) < 1e-6
    assert bars[1].volume == 952_270_700
    assert abs(bars[2].close - 3.054) < 1e-6
    assert bars[2].volume == 597_003_600

    # Idempotent when HQ payload unchanged.
    assert (
        upsert_day_bars(
            path,
            [_bar(code, date(2026, 7, 27), 3.054, volume=597_003_600)],
            code=code,
        )
        == 0
    )


def test_upsert_appends_newer_dates(tmp_path: Path) -> None:
    path = tmp_path / "sh" / "lday" / "sh510050.day"
    code = "sh510050"
    append_day_bars(path, [_bar(code, date(2026, 7, 23), 3.084)], code=code)
    n = upsert_day_bars(
        path,
        [
            _bar(code, date(2026, 7, 23), 3.084),
            _bar(code, date(2026, 7, 24), 3.05),
        ],
        code=code,
    )
    assert n == 1
    assert last_trade_date(path) == date(2026, 7, 24)
