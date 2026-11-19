from __future__ import annotations

import json
import logging
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

from app.config.settings import Settings, resolve_sqlite_path
from app.data.cache import SqliteCache
from app.data.models import SyncResult
from app.data.provider import IDataProvider, IDataSyncAdapter
from app.data.pytdx_updater import refresh_codes_via_pytdx, refresh_vipdoc_via_pytdx

logger = logging.getLogger(__name__)

# Keep defaults here to avoid importing research package from data layer.
_DEFAULT_MINUTE_CODES: tuple[str, ...] = (
    "sh510050",
    "sh510300",
    "sh510500",
    "sh512100",
    "sh588000",
    "sz159915",
    "sh510210",
)

_META_NAME = "_hsjday.meta.json"
_MIN_ZIP_BYTES = 1_000_000
_ZIP_MAGIC = b"PK\x03\x04"
_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.tdx.com.cn/",
    "Accept": "application/zip,application/octet-stream,*/*",
}


class TdxLocalSyncAdapter(IDataSyncAdapter):
    """
    EOD sync for tdx_local:
    1) Prefer pytdx incremental refresh of vipdoc .day files
    2) Fall back to official hsjday.zip when pytdx fails
    3) Ingest into SQLite
    """

    def __init__(
        self,
        settings: Settings,
        provider: IDataProvider,
        download: bool = False,
        ingest_limit: int | None = 50,
    ) -> None:
        self.settings = settings
        self.provider = provider
        self.download = download
        self.ingest_limit = ingest_limit

    def sync(self) -> SyncResult:
        vipdoc = Path(self.settings.data.tdx.vipdoc)
        refresh_msg = ""
        day_refreshed = False
        if self.download:
            refresh = self._refresh_vipdoc(vipdoc)
            if not refresh.ok:
                return refresh
            refresh_msg = refresh.message
            day_refreshed = True

        if not vipdoc.is_dir():
            return SyncResult(
                ok=False,
                message=f"vipdoc missing: {vipdoc}",
                source="tdx_local",
            )

        cache = SqliteCache(resolve_sqlite_path(self.settings))
        try:
            cache.ingest_provider(self.provider, limit=self.ingest_limit)
        except Exception as exc:  # noqa: BLE001
            logger.exception("ingest failed")
            return SyncResult(
                ok=False, message=f"ingest failed: {exc}", source="tdx_local"
            )

        as_of = self.provider.get_data_as_of()
        ok = as_of is not None
        base = f"synced as_of={as_of}" if ok else "synced but as_of unknown"
        msg = f"{refresh_msg}; {base}" if refresh_msg else base

        # Same cadence as K-line: after a successful day refresh, update finance_cache.
        if day_refreshed and self.settings.data.sync_finance_with_day:
            fin = self._sync_finance_cache()
            msg = f"{msg}; {fin.message}"
            # Day sync still counts as ok even if finance partially fails.
            if not fin.ok:
                logger.warning("finance sync after day refresh: %s", fin.message)

        return SyncResult(ok=ok, message=msg, as_of=as_of, source="tdx_local")

    def maybe_refresh_on_start(self) -> SyncResult:
        """Refresh when local as_of lags the settled session; else verify watchlist."""
        data = self.settings.data
        as_of = self.provider.get_data_as_of()
        if not freshness_ok(
            as_of, eod_hour=data.eod_hour, eod_minute=data.eod_minute
        ):
            self.download = True
            return self.sync()
        # Market sample is fresh, but individual symbols (e.g. research ETFs)
        # can still lag or hold a bad settled bar — verify/heal the watchlist.
        return self._heal_watchlist_days(as_of=as_of)

    def maybe_sync_minutes_on_start(self) -> SyncResult:
        """Sync watchlist ETF minute bars into vipdoc via pytdx. Never raises."""
        data = self.settings.data
        if not data.auto_sync_minute_on_start:
            return SyncResult(
                ok=True,
                message="minute sync skipped (disabled)",
                as_of=self.provider.get_data_as_of(),
                source="tdx_local",
            )
        vipdoc = Path(data.tdx.vipdoc)
        if not vipdoc.is_dir():
            return SyncResult(
                ok=False,
                message=f"minute sync skip: vipdoc missing {vipdoc}",
                source="tdx_local",
            )

        codes = data.minute_sync_codes or _DEFAULT_MINUTE_CODES
        freqs = data.minute_sync_freqs or ("1m", "5m")
        max_bars = max(1, min(int(data.minute_sync_bar_count), 8000))

        from app.data.pytdx_minute_updater import sync_minute_to_vipdoc

        ok_n = 0
        fail_n = 0
        wrote = 0
        details: list[str] = []
        for code in codes:
            for freq in freqs:
                try:
                    result = sync_minute_to_vipdoc(
                        vipdoc,
                        code,
                        freq=freq,
                        max_bars=max_bars,
                        replace=False,
                    )
                    if result.ok:
                        ok_n += 1
                        wrote += result.bars_written
                        details.append(
                            f"{result.code}:{freq}+{result.bars_written}"
                        )
                    else:
                        fail_n += 1
                        details.append(f"{code}:{freq}:fail")
                        logger.warning(
                            "startup minute sync failed %s %s: %s",
                            code,
                            freq,
                            result.message,
                        )
                except Exception as exc:  # noqa: BLE001
                    fail_n += 1
                    details.append(f"{code}:{freq}:err")
                    logger.warning(
                        "startup minute sync error %s %s: %s", code, freq, exc
                    )

        msg = (
            f"minute sync codes={len(codes)} freqs={list(freqs)} "
            f"ok={ok_n} fail={fail_n} bars_written={wrote}"
        )
        if details:
            msg = f"{msg} [{', '.join(details[:12])}"
            if len(details) > 12:
                msg += ", ...]"
            else:
                msg += "]"
        logger.info(msg)
        return SyncResult(
            ok=fail_n == 0 or ok_n > 0,
            message=msg,
            as_of=self.provider.get_data_as_of(),
            source="tdx_local",
        )

    def maybe_sync_finance_on_start(self) -> SyncResult:
        """Sync L1 universe finance_cache via pytdx get_finance_info. Never raises."""
        data = self.settings.data
        if not data.auto_sync_finance_on_start:
            return SyncResult(
                ok=True,
                message="finance sync skipped (disabled)",
                as_of=self.provider.get_data_as_of(),
                source="tdx_local",
            )
        return self._sync_finance_cache()

    def _sync_finance_cache(self) -> SyncResult:
        """Always attempt finance_cache refresh for L1 universe (no enable flag)."""
        try:
            from app.data.pytdx_finance import refresh_finance_cache
            from app.selection.universe import default_universe_dir, load_universe

            uni = load_universe(default_universe_dir())
            path = default_universe_dir() / "finance_cache.json"
            as_of = self.provider.get_data_as_of()
            result = refresh_finance_cache(
                list(uni.codes),
                path,
                workers=self.settings.data.finance_sync_workers,
                as_of=as_of,
            )
            return SyncResult(
                ok=result.ok,
                message=result.message,
                as_of=as_of,
                source="tdx_local",
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("finance sync failed")
            return SyncResult(
                ok=False,
                message=f"finance sync failed: {exc}",
                as_of=self.provider.get_data_as_of(),
                source="tdx_local",
            )

    def _watchlist_day_codes(self) -> tuple[str, ...]:
        codes = self.settings.data.minute_sync_codes or _DEFAULT_MINUTE_CODES
        return tuple(codes)

    def _heal_watchlist_days(self, as_of: date | None = None) -> SyncResult:
        """Verify/repair research/watchlist ETF .day files vs settled HQ."""
        vipdoc = Path(self.settings.data.tdx.vipdoc)
        data = self.settings.data
        if not vipdoc.is_dir():
            return SyncResult(
                ok=False,
                message=f"watchlist day heal skip: vipdoc missing {vipdoc}",
                as_of=as_of,
                source="tdx_local",
            )
        codes = self._watchlist_day_codes()
        from app.data.session_calendar import settled_as_of

        target = settled_as_of(eod_hour=data.eod_hour, eod_minute=data.eod_minute)
        py = refresh_codes_via_pytdx(
            vipdoc,
            codes,
            bar_count=data.pytdx_bar_count,
            min_as_of=min(as_of, target) if as_of is not None else target,
            target_as_of=target,
            eod_hour=data.eod_hour,
            eod_minute=data.eod_minute,
        )
        msg = (
            f"startup verify: local fresh; {py.message}"
            if as_of is not None
            else py.message
        )
        return SyncResult(
            ok=py.ok,
            message=msg,
            as_of=as_of or self.provider.get_data_as_of(),
            source="tdx_local",
        )

    def _refresh_vipdoc(self, vipdoc: Path) -> SyncResult:
        """Prefer pytdx settled incremental; fall back to hsjday.zip."""
        data = self.settings.data
        from app.data.session_calendar import settled_as_of

        target = settled_as_of(eod_hour=data.eod_hour, eod_minute=data.eod_minute)
        py = refresh_vipdoc_via_pytdx(
            vipdoc,
            workers=data.pytdx_workers,
            bar_count=data.pytdx_bar_count,
            max_symbols=data.pytdx_max_symbols,
            target_as_of=target,
            eod_hour=data.eod_hour,
            eod_minute=data.eod_minute,
        )
        # Always heal watchlist after a full sweep so research ETFs are not left
        # behind when a few symbols fail mid-batch.
        heal = refresh_codes_via_pytdx(
            vipdoc,
            self._watchlist_day_codes(),
            bar_count=data.pytdx_bar_count,
            min_as_of=target,
            target_as_of=target,
            eod_hour=data.eod_hour,
            eod_minute=data.eod_minute,
        )
        if py.ok:
            msg = py.message
            if heal.bars_appended or heal.errors:
                msg = f"{msg}; {heal.message}"
            return SyncResult(
                ok=True,
                message=msg,
                as_of=self.provider.get_data_as_of(),
                source="tdx_local",
            )

        logger.warning("pytdx refresh failed, trying zip: %s", py.message)
        try:
            self._download_hsjday(vipdoc)
            return SyncResult(
                ok=True,
                message=f"zip fallback ok (after {py.message})",
                as_of=self.provider.get_data_as_of(),
                source="tdx_local",
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("hsjday download failed")
            return SyncResult(
                ok=False,
                message=f"{py.message}; zip failed: {exc}",
                source="tdx_local",
            )

    def _download_hsjday(self, vipdoc: Path) -> None:
        vipdoc.mkdir(parents=True, exist_ok=True)
        zip_path = vipdoc.parent / "_hsjday.zip"
        url = self.settings.data.hsjday_url
        meta_path = _meta_path(vipdoc)
        logger.info("downloading %s -> %s", url, zip_path)
        headers = download_zip_validated(url, zip_path)
        with zipfile.ZipFile(zip_path, "r") as zf:
            bad = zf.testzip()
            if bad is not None:
                raise zipfile.BadZipFile(f"corrupt member: {bad}")
            zf.extractall(vipdoc)
        write_download_meta(meta_path, headers)
        logger.info("extracted hsjday into %s", vipdoc)


class DataSyncJob:
    def __init__(
        self,
        settings: Settings,
        provider: IDataProvider,
        adapter: IDataSyncAdapter | None,
    ) -> None:
        self.settings = settings
        self.provider = provider
        self.adapter = adapter

    def run(self, force: bool = False) -> SyncResult:
        if not force and not self._is_trading_day_window():
            return SyncResult(
                ok=True,
                message="skipped non-trading window",
                as_of=self.provider.get_data_as_of(),
                source=self.provider.provider_id,
            )
        if self.adapter is None:
            return SyncResult(
                ok=False,
                message="no sync adapter",
                source=self.provider.provider_id,
            )
        return self.adapter.sync()

    def _is_trading_day_window(self) -> bool:
        now = datetime.now()
        if now.weekday() >= 5:
            return False
        return True


def freshness_ok(
    as_of: date | None,
    today: date | None = None,
    *,
    now: datetime | None = None,
    eod_hour: int = 16,
    eod_minute: int = 0,
) -> bool:
    """True when local as_of covers the latest settled (EOD) session."""
    if as_of is None:
        return False
    from app.data.session_calendar import settled_as_of

    if today is not None and now is None:
        # Legacy tests pass calendar "today" without a clock — treat as post-EOD.
        now = datetime(today.year, today.month, today.day, eod_hour, eod_minute)
    target = settled_as_of(now, eod_hour=eod_hour, eod_minute=eod_minute)
    return as_of >= target


def _meta_path(vipdoc: Path) -> Path:
    return vipdoc.parent / _META_NAME


def _apply_headers(req: Request) -> None:
    for key, value in _HTTP_HEADERS.items():
        req.add_header(key, value)


def _headers_look_like_zip(headers: dict[str, str], content_type: str = "") -> bool:
    ctype = (content_type or headers.get("content_type") or "").lower()
    if "html" in ctype or "text/" in ctype:
        return False
    length_raw = headers.get("content_length") or ""
    if length_raw.isdigit() and int(length_raw) < _MIN_ZIP_BYTES:
        return False
    return True


def probe_remote_headers(url: str, timeout: float = 15.0) -> dict[str, str]:
    """HEAD/GET probe; rejects HTML/anti-bot responses as empty (inconclusive)."""
    for method in ("HEAD", "GET"):
        req = Request(url, method=method)
        _apply_headers(req)
        if method == "GET":
            req.add_header("Range", "bytes=0-3")
        try:
            with urlopen(req, timeout=timeout) as resp:  # noqa: S310
                ctype = str(resp.headers.get("Content-Type") or "")
                headers = {
                    "last_modified": str(resp.headers.get("Last-Modified") or ""),
                    "content_length": str(resp.headers.get("Content-Length") or ""),
                    "etag": str(resp.headers.get("ETag") or ""),
                    "content_type": ctype,
                }
                if method == "GET":
                    magic = resp.read(4)
                    if magic and magic != _ZIP_MAGIC:
                        return {}
                if not _headers_look_like_zip(headers, ctype):
                    return {}
                return headers
        except (URLError, HTTPError):
            if method == "GET":
                raise
    return {}


def remote_zip_newer(url: str, meta_path: Path) -> bool | None:
    """
    True if remote zip appears newer than last successful download.
    None if probe failed / inconclusive (including anti-bot HTML).
    """
    try:
        headers = probe_remote_headers(url)
    except Exception:  # noqa: BLE001
        return None
    if not any(headers.get(k) for k in ("etag", "last_modified", "content_length")):
        return None
    if not _headers_look_like_zip(headers):
        return None
    if not meta_path.is_file():
        return True
    try:
        prev = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    for key in ("etag", "last_modified", "content_length"):
        new = headers.get(key) or ""
        old = str(prev.get(key) or "")
        if new and old and new != old:
            return True
        if new and not old:
            return True
    if headers.get("etag") or headers.get("last_modified"):
        return False
    return None


def download_zip_validated(url: str, zip_path: Path, timeout: float = 120.0) -> dict[str, str]:
    """Download URL to zip_path; validate magic/size/zip integrity. Raises on failure."""
    req = Request(url)
    _apply_headers(req)
    tmp_path = zip_path.with_suffix(zip_path.suffix + ".part")
    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310
            ctype = str(resp.headers.get("Content-Type") or "")
            headers = {
                "last_modified": str(resp.headers.get("Last-Modified") or ""),
                "content_length": str(resp.headers.get("Content-Length") or ""),
                "etag": str(resp.headers.get("ETag") or ""),
                "content_type": ctype,
            }
            if "html" in ctype.lower() or "text/" in ctype.lower():
                raise zipfile.BadZipFile(f"remote returned non-zip content-type: {ctype}")
            with tmp_path.open("wb") as out:
                while True:
                    chunk = resp.read(1024 * 256)
                    if not chunk:
                        break
                    out.write(chunk)
        size = tmp_path.stat().st_size
        if size < _MIN_ZIP_BYTES:
            raise zipfile.BadZipFile(f"zip too small ({size} bytes); likely anti-bot HTML")
        with tmp_path.open("rb") as fh:
            magic = fh.read(4)
        if magic != _ZIP_MAGIC:
            raise zipfile.BadZipFile("file magic is not PK zip")
        with zipfile.ZipFile(tmp_path, "r") as zf:
            bad = zf.testzip()
            if bad is not None:
                raise zipfile.BadZipFile(f"corrupt member: {bad}")
        tmp_path.replace(zip_path)
        return headers
    except Exception:
        if tmp_path.is_file():
            tmp_path.unlink(missing_ok=True)
        if zip_path.is_file() and zip_path.stat().st_size < _MIN_ZIP_BYTES:
            zip_path.unlink(missing_ok=True)
        raise


def write_download_meta(meta_path: Path, headers: dict[str, str]) -> None:
    payload: dict[str, Any] = {
        "downloaded_at": datetime.now().isoformat(timespec="seconds"),
        **headers,
    }
    meta_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
