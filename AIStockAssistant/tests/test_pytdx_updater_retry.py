from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.data.models import Bar
from app.data.pytdx_updater import (
    PytdxUpdateResult,
    _update_chunk,
    refresh_codes_via_pytdx,
)
from app.data.tdx_day_writer import append_day_bars, last_trade_date


def _write_day(path: Path, code: str, trade_date: date) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    bar = Bar(
        code=code,
        trade_date=trade_date,
        open=1.0,
        high=1.1,
        low=0.9,
        close=1.05,
        volume=1000.0,
        amount=1000.0,
    )
    append_day_bars(path, [bar], code=code)


def test_update_chunk_retries_then_succeeds(tmp_path: Path) -> None:
    path = tmp_path / "sh" / "lday" / "sh588000.day"
    _write_day(path, "sh588000", date(2026, 7, 23))
    api = MagicMock()
    calls = {"n": 0}

    def _fake_update(a, p, bar_count, *, target_as_of):  # noqa: ANN001
        assert target_as_of == date(2026, 7, 27)
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("transient")
        return 2

    with (
        patch("app.data.pytdx_updater._connect", return_value=api),
        patch("app.data.pytdx_updater._disconnect"),
        patch("app.data.pytdx_updater._update_one", side_effect=_fake_update),
        patch("app.data.pytdx_updater.time.sleep"),
    ):
        updated, appended, failed = _update_chunk(
            [path],
            (("127.0.0.1", 7709),),
            bar_count=10,
            target_as_of=date(2026, 7, 27),
            retries=2,
            retry_sleep=0,
        )
    assert updated == 1
    assert appended == 2
    assert failed == []
    assert calls["n"] == 3


def test_update_chunk_reconnects_between_retries(tmp_path: Path) -> None:
    path = tmp_path / "sh" / "lday" / "sh510300.day"
    _write_day(path, "sh510300", date(2026, 7, 23))
    connect_n = {"n": 0}

    def _connect(_hosts):  # noqa: ANN001
        connect_n["n"] += 1
        return MagicMock(name=f"api{connect_n['n']}")

    with (
        patch("app.data.pytdx_updater._connect", side_effect=_connect),
        patch("app.data.pytdx_updater._disconnect") as disc,
        patch(
            "app.data.pytdx_updater._update_one",
            side_effect=[RuntimeError("boom"), 1],
        ),
        patch("app.data.pytdx_updater.time.sleep"),
    ):
        updated, appended, failed = _update_chunk(
            [path],
            (("127.0.0.1", 7709),),
            bar_count=10,
            target_as_of=date(2026, 7, 27),
            retries=1,
            retry_sleep=0,
        )
    assert updated == 1
    assert appended == 1
    assert failed == []
    assert connect_n["n"] >= 2
    assert disc.called


def test_infer_vol_scale_prefers_unit_match(tmp_path: Path) -> None:
    from app.data.pytdx_updater import _infer_vol_scale

    path = tmp_path / "sh" / "lday" / "sh588000.day"
    _write_day(path, "sh588000", date(2026, 7, 23))
    # Overlap with same volume unit as local (scale=1).
    rows = [
        {
            "year": 2026,
            "month": 7,
            "day": 23,
            "open": 1.0,
            "high": 1.1,
            "low": 0.9,
            "close": 1.05,
            "vol": 1000.0,
            "amount": 1000.0,
        }
    ]
    assert _infer_vol_scale(path, "sh588000", rows) == 1.0


def test_pack_bar_clamps_uint32_volume() -> None:
    from app.data.tdx_day_writer import _pack_bar
    from app.data.tdx_day_reader import price_divisor

    bar = Bar(
        code="sh588000",
        trade_date=date(2026, 7, 24),
        open=1.0,
        high=1.0,
        low=1.0,
        close=1.0,
        volume=5_000_000_000.0,
        amount=1.0,
    )
    packed = _pack_bar(bar, price_divisor("sh588000"))
    assert len(packed) == 32


def test_refresh_codes_retries_lagging_vs_min_as_of(tmp_path: Path) -> None:
    vipdoc = tmp_path / "vipdoc"
    path = vipdoc / "sh" / "lday" / "sh588000.day"
    _write_day(path, "sh588000", date(2026, 7, 23))
    calls = {"n": 0}

    def _chunk(paths, hosts, bar_count, *, target_as_of, retries=2, retry_sleep=0.2):  # noqa: ANN001
        assert target_as_of == date(2026, 7, 27)
        calls["n"] += 1
        if calls["n"] == 1:
            # Silent no-op (empty HQ) — file still lagging.
            return 0, 0, []
        _write_day(path, "sh588000", date(2026, 7, 27))
        return 1, 1, []

    with patch("app.data.pytdx_updater._update_chunk", side_effect=_chunk):
        result = refresh_codes_via_pytdx(
            vipdoc,
            ["sh588000"],
            min_as_of=date(2026, 7, 27),
            target_as_of=date(2026, 7, 27),
        )
    assert isinstance(result, PytdxUpdateResult)
    assert result.ok
    assert result.errors == 0
    assert calls["n"] == 2
    assert last_trade_date(path) == date(2026, 7, 27)
