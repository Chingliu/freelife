from __future__ import annotations

import json
import zipfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.config.settings import Settings
from app.data.models import SyncResult
from app.data.pytdx_updater import PytdxUpdateResult
from app.data.tdx_sync import (
    TdxLocalSyncAdapter,
    download_zip_validated,
    freshness_ok,
    probe_remote_headers,
    remote_zip_newer,
    write_download_meta,
)


def test_freshness_helper() -> None:
    today = date(2026, 7, 23)
    # Calendar "today" without clock ⇒ treated as post-EOD on that day.
    assert freshness_ok(today, today)
    assert not freshness_ok(today - timedelta(days=1), today)  # post-EOD needs today
    assert not freshness_ok(today - timedelta(days=10), today)
    assert not freshness_ok(None, today)
    # Before EOD cutoff, previous weekday is enough.
    from datetime import datetime

    assert freshness_ok(
        today - timedelta(days=1),
        now=datetime(2026, 7, 23, 10, 0, 0),
        eod_hour=16,
        eod_minute=0,
    )


def test_remote_zip_newer_no_meta(tmp_path: Path) -> None:
    meta = tmp_path / "_hsjday.meta.json"
    with patch(
        "app.data.tdx_sync.probe_remote_headers",
        return_value={
            "last_modified": "Thu, 23 Jul 2026 10:00:00 GMT",
            "etag": "",
            "content_length": "5000000",
            "content_type": "application/zip",
        },
    ):
        assert remote_zip_newer("http://example/hsjday.zip", meta) is True


def test_remote_zip_newer_unchanged(tmp_path: Path) -> None:
    meta = tmp_path / "_hsjday.meta.json"
    headers = {
        "last_modified": "Thu, 23 Jul 2026 10:00:00 GMT",
        "etag": '"abc"',
        "content_length": "5000000",
        "content_type": "application/zip",
    }
    write_download_meta(meta, headers)
    with patch("app.data.tdx_sync.probe_remote_headers", return_value=headers):
        assert remote_zip_newer("http://example/hsjday.zip", meta) is False


def test_remote_zip_newer_changed(tmp_path: Path) -> None:
    meta = tmp_path / "_hsjday.meta.json"
    write_download_meta(
        meta,
        {
            "last_modified": "Wed, 22 Jul 2026 10:00:00 GMT",
            "etag": '"old"',
            "content_length": "5000000",
        },
    )
    with patch(
        "app.data.tdx_sync.probe_remote_headers",
        return_value={
            "last_modified": "Thu, 23 Jul 2026 10:00:00 GMT",
            "etag": '"new"',
            "content_length": "5000000",
            "content_type": "application/zip",
        },
    ):
        assert remote_zip_newer("http://example/hsjday.zip", meta) is True


def test_remote_zip_newer_rejects_tiny_or_html(tmp_path: Path) -> None:
    meta = tmp_path / "_hsjday.meta.json"
    with patch(
        "app.data.tdx_sync.probe_remote_headers",
        return_value={
            "last_modified": "",
            "etag": "",
            "content_length": "986",
            "content_type": "text/html",
        },
    ):
        assert remote_zip_newer("http://example/hsjday.zip", meta) is None


def test_maybe_refresh_skips_full_sync_when_fresh_but_heals_watchlist(
    tmp_path: Path,
) -> None:
    vipdoc = tmp_path / "vipdoc"
    vipdoc.mkdir()
    settings = Settings.from_dict(
        {
            "data": {
                "provider": "tdx_local",
                "auto_download_on_start": True,
                "minute_sync_codes": ["sh510300"],
                "tdx": {"vipdoc": str(vipdoc)},
            }
        }
    )
    provider = MagicMock()
    provider.provider_id = "tdx_local"
    provider.get_data_as_of.return_value = date.today()
    adapter = TdxLocalSyncAdapter(settings, provider, ingest_limit=1)
    heal = SyncResult(
        ok=True,
        message="startup verify: local fresh; pytdx watchlist ok",
        as_of=date.today(),
        source="tdx_local",
    )
    with (
        patch.object(adapter, "sync") as sync_mock,
        patch.object(adapter, "_heal_watchlist_days", return_value=heal) as heal_mock,
        patch("app.data.tdx_sync.freshness_ok", return_value=True),
    ):
        result = adapter.maybe_refresh_on_start()
    assert result.ok
    assert "fresh" in result.message
    assert adapter.download is False
    sync_mock.assert_not_called()
    heal_mock.assert_called_once()


def test_heal_watchlist_days_calls_refresh_codes(tmp_path: Path) -> None:
    vipdoc = tmp_path / "vipdoc"
    (vipdoc / "sh" / "lday").mkdir(parents=True)
    settings = Settings.from_dict(
        {
            "data": {
                "provider": "tdx_local",
                "minute_sync_codes": ["sh588000"],
                "pytdx_bar_count": 20,
                "tdx": {"vipdoc": str(vipdoc)},
            }
        }
    )
    provider = MagicMock()
    provider.provider_id = "tdx_local"
    provider.get_data_as_of.return_value = date(2026, 7, 27)
    adapter = TdxLocalSyncAdapter(settings, provider)
    with (
        patch(
            "app.data.session_calendar.settled_as_of",
            return_value=date(2026, 7, 27),
        ),
        patch(
            "app.data.tdx_sync.refresh_codes_via_pytdx",
            return_value=PytdxUpdateResult(
                ok=True,
                message="pytdx watchlist ok codes=1 updated=1 bars=2 errors=0",
                files_scanned=1,
                files_updated=1,
                bars_appended=2,
            ),
        ) as mock_heal,
    ):
        result = adapter._heal_watchlist_days(as_of=date(2026, 7, 27))
    assert result.ok
    assert "verify" in result.message
    mock_heal.assert_called_once()
    kwargs = mock_heal.call_args.kwargs
    assert kwargs["target_as_of"] == date(2026, 7, 27)
    assert kwargs["min_as_of"] == date(2026, 7, 27)
    assert mock_heal.call_args.args[1] == ("sh588000",)

def test_maybe_refresh_runs_when_stale(tmp_path: Path) -> None:
    vipdoc = tmp_path / "vipdoc"
    vipdoc.mkdir()
    settings = Settings.from_dict(
        {
            "data": {
                "provider": "tdx_local",
                "tdx": {"vipdoc": str(vipdoc)},
                "sqlite_path": str(tmp_path / "c.db"),
            }
        }
    )
    provider = MagicMock()
    provider.provider_id = "tdx_local"
    provider.get_data_as_of.return_value = date.today() - timedelta(days=10)
    provider.get_stock_list.return_value = []
    adapter = TdxLocalSyncAdapter(settings, provider, ingest_limit=0)
    with patch.object(
        adapter,
        "sync",
        return_value=SyncResult(ok=True, message="synced", source="tdx_local"),
    ) as sync_mock:
        result = adapter.maybe_refresh_on_start()
    assert result.ok
    assert adapter.download is True
    sync_mock.assert_called_once()


def test_refresh_prefers_pytdx_over_zip(tmp_path: Path) -> None:
    vipdoc = tmp_path / "vipdoc"
    vipdoc.mkdir()
    settings = Settings.from_dict(
        {
            "data": {
                "provider": "tdx_local",
                "tdx": {"vipdoc": str(vipdoc)},
                "sqlite_path": str(tmp_path / "c.db"),
            }
        }
    )
    provider = MagicMock()
    provider.provider_id = "tdx_local"
    provider.get_data_as_of.return_value = date.today() - timedelta(days=10)
    provider.get_stock_list.return_value = []
    adapter = TdxLocalSyncAdapter(settings, provider, download=True, ingest_limit=0)
    with (
        patch(
            "app.data.tdx_sync.refresh_vipdoc_via_pytdx",
            return_value=PytdxUpdateResult(
                ok=True, message="pytdx incremental ok", files_scanned=1, files_updated=1
            ),
        ) as py_mock,
        patch.object(adapter, "_download_hsjday") as zip_mock,
    ):
        result = adapter.sync()
    assert result.ok
    assert "pytdx" in result.message
    py_mock.assert_called_once()
    zip_mock.assert_not_called()


def test_refresh_falls_back_to_zip_when_pytdx_fails(tmp_path: Path) -> None:
    vipdoc = tmp_path / "vipdoc"
    vipdoc.mkdir()
    settings = Settings.from_dict(
        {
            "data": {
                "provider": "tdx_local",
                "tdx": {"vipdoc": str(vipdoc)},
                "sqlite_path": str(tmp_path / "c.db"),
            }
        }
    )
    provider = MagicMock()
    provider.provider_id = "tdx_local"
    provider.get_data_as_of.return_value = date.today() - timedelta(days=10)
    provider.get_stock_list.return_value = []
    adapter = TdxLocalSyncAdapter(settings, provider, download=True, ingest_limit=0)
    with (
        patch(
            "app.data.tdx_sync.refresh_vipdoc_via_pytdx",
            return_value=PytdxUpdateResult(ok=False, message="pytdx failed: boom"),
        ),
        patch.object(adapter, "_download_hsjday") as zip_mock,
    ):
        result = adapter.sync()
    assert result.ok
    assert "zip fallback" in result.message
    zip_mock.assert_called_once()


def test_download_zip_validated_rejects_html(tmp_path: Path) -> None:
    target = tmp_path / "x.zip"

    class _Resp:
        headers = {"Content-Type": "text/html", "Content-Length": "986"}

        def read(self, n: int = -1) -> bytes:
            return b"<script>EO_Bot_Ssid</script>"

        def __enter__(self) -> "_Resp":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    with patch("app.data.tdx_sync.urlopen", return_value=_Resp()):
        with pytest.raises(zipfile.BadZipFile):
            download_zip_validated("http://example/hsjday.zip", target)
    assert not target.exists()


def test_maybe_sync_minutes_disabled(tmp_path: Path) -> None:
    settings = Settings.from_dict(
        {
            "data": {
                "provider": "tdx_local",
                "auto_sync_minute_on_start": False,
                "tdx": {"vipdoc": str(tmp_path / "vipdoc")},
            }
        }
    )
    (tmp_path / "vipdoc").mkdir()
    provider = MagicMock()
    provider.provider_id = "tdx_local"
    provider.get_data_as_of.return_value = date.today()
    adapter = TdxLocalSyncAdapter(settings, provider)
    result = adapter.maybe_sync_minutes_on_start()
    assert result.ok
    assert "disabled" in result.message


def test_maybe_sync_minutes_calls_pytdx(tmp_path: Path) -> None:
    vipdoc = tmp_path / "vipdoc"
    vipdoc.mkdir()
    settings = Settings.from_dict(
        {
            "data": {
                "provider": "tdx_local",
                "auto_sync_minute_on_start": True,
                "minute_sync_codes": ["sh510210"],
                "minute_sync_freqs": ["1m"],
                "minute_sync_bar_count": 100,
                "tdx": {"vipdoc": str(vipdoc)},
            }
        }
    )
    provider = MagicMock()
    provider.provider_id = "tdx_local"
    provider.get_data_as_of.return_value = date.today()
    adapter = TdxLocalSyncAdapter(settings, provider)
    fake = MagicMock()
    fake.ok = True
    fake.code = "sh510210"
    fake.bars_written = 12
    fake.message = "ok"
    with patch(
        "app.data.pytdx_minute_updater.sync_minute_to_vipdoc",
        return_value=fake,
    ) as sync_mock:
        result = adapter.maybe_sync_minutes_on_start()
    assert result.ok
    assert "minute sync" in result.message
    assert "bars_written=12" in result.message
    sync_mock.assert_called_once()


def test_try_startup_refresh_runs_minute_even_if_day_fresh(tmp_path: Path) -> None:
    from app.ai.service import AnalysisService
    from app.data.tdx_sync import TdxLocalSyncAdapter as RealAdapter

    vipdoc = tmp_path / "vipdoc"
    vipdoc.mkdir()
    settings = Settings.from_dict(
        {
            "data": {
                "provider": "tdx_local",
                "auto_download_on_start": True,
                "auto_sync_minute_on_start": True,
                "minute_sync_codes": ["sh510210"],
                "minute_sync_freqs": ["1m"],
                "tdx": {"vipdoc": str(vipdoc)},
                "sqlite_path": str(tmp_path / "c.db"),
            }
        }
    )
    svc = AnalysisService(settings)
    svc.provider = MagicMock()
    svc.provider.provider_id = "tdx_local"
    svc.provider.get_data_as_of.return_value = date.today()
    day = SyncResult(ok=True, message="startup verify: local fresh", source="tdx_local")
    minute = SyncResult(ok=True, message="minute sync ok=1", source="tdx_local")

    class Stub(RealAdapter):
        def __init__(self) -> None:  # noqa: D107
            pass

    stub = Stub.__new__(Stub)
    stub.maybe_refresh_on_start = MagicMock(return_value=day)
    stub.maybe_sync_minutes_on_start = MagicMock(return_value=minute)
    svc.sync = stub
    result = svc.try_startup_refresh()
    assert result is not None
    assert "startup verify" in result.message
    assert "minute sync" in result.message
    stub.maybe_refresh_on_start.assert_called_once()
    stub.maybe_sync_minutes_on_start.assert_called_once()


def test_settings_auto_download_flag() -> None:
    s = Settings.from_dict({"data": {"auto_download_on_start": True}})
    assert s.data.auto_download_on_start is True
    assert Settings.from_dict({}).data.auto_download_on_start is False
    s2 = Settings.from_dict({"data": {"pytdx_workers": 8, "pytdx_bar_count": 20}})
    assert s2.data.pytdx_workers == 8
    assert s2.data.pytdx_bar_count == 20
    s3 = Settings.from_dict(
        {
            "data": {
                "auto_sync_minute_on_start": True,
                "minute_sync_codes": "sh510210,sh510300",
                "minute_sync_freqs": ["1m"],
            }
        }
    )
    assert s3.data.auto_sync_minute_on_start is True
    assert s3.data.minute_sync_codes == ("sh510210", "sh510300")
    assert s3.data.minute_sync_freqs == ("1m",)


def test_write_download_meta_roundtrip(tmp_path: Path) -> None:
    meta = tmp_path / "_hsjday.meta.json"
    write_download_meta(meta, {"etag": '"x"', "last_modified": "a", "content_length": "1"})
    data = json.loads(meta.read_text(encoding="utf-8"))
    assert data["etag"] == '"x"'
    assert "downloaded_at" in data


def test_probe_remote_headers_rejects_html_body() -> None:
    class _Resp:
        headers = {
            "Content-Type": "text/html",
            "Content-Length": "986",
            "Last-Modified": "",
            "ETag": "",
        }

        def read(self, n: int = -1) -> bytes:
            return b"<scr"

        def __enter__(self) -> "_Resp":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    with patch("app.data.tdx_sync.urlopen", return_value=_Resp()):
        assert probe_remote_headers("http://example/hsjday.zip") == {}
