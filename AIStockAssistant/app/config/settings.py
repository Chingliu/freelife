from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml


@dataclass
class TdxSettings:
    root: str = r"D:\tdx"
    vipdoc: str = r"D:\tdx\vipdoc"
    exe: str = r"D:\tdx\TdxW.exe"


@dataclass
class DataSettings:
    provider: str = "mock"
    fallback: str | None = None
    tdx: TdxSettings = field(default_factory=TdxSettings)
    sqlite_path: str = "data/cache.db"
    eod_hour: int = 16
    eod_minute: int = 0
    hsjday_url: str = "https://data.tdx.com.cn/vipdoc/hsjday.zip"
    # MCP/service start: when local as_of is stale, refresh via pytdx then zip.
    # Failures never block startup.
    auto_download_on_start: bool = False
    pytdx_workers: int = 4
    pytdx_bar_count: int = 40
    # None = all local .day files; set for tests / partial refresh.
    pytdx_max_symbols: int | None = None
    # EU/US/APAC quotes via yfinance (separate from A-share tdx_local).
    global_enabled: bool = True
    # MCP start: sync watchlist ETF minute bars into vipdoc (pytdx).
    auto_sync_minute_on_start: bool = False
    minute_sync_codes: tuple[str, ...] = ()
    minute_sync_freqs: tuple[str, ...] = ("1m", "5m")
    minute_sync_bar_count: int = 800
    # After day-bar refresh: pytdx get_finance_info → finance_cache.json (selection Phase3).
    # sync_finance_with_day: when vipdoc .day is refreshed, also refresh finance (default on).
    sync_finance_with_day: bool = True
    # Standalone on MCP start even if day bars were already fresh.
    auto_sync_finance_on_start: bool = False
    finance_sync_workers: int = 4


@dataclass
class TargetSettings:
    annual_return_min: float = 0.05
    annual_return_max: float = 0.10
    max_drawdown: float = 0.15
    max_position_pct: float = 0.20
    max_total_exposure: float = 0.80


@dataclass
class EmailNotifySettings:
    enabled: bool = False
    smtp_host: str = "smtp.qq.com"
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    mail_to: str = ""
    use_ssl: bool = True


@dataclass
class NotifySettings:
    email: EmailNotifySettings = field(default_factory=EmailNotifySettings)


@dataclass
class Settings:
    data: DataSettings = field(default_factory=DataSettings)
    targets: TargetSettings = field(default_factory=TargetSettings)
    notify: NotifySettings = field(default_factory=NotifySettings)
    log_level: str = "INFO"

    @classmethod
    def load(cls, path: str | Path | None = None) -> Settings:
        here = Path(__file__).resolve().parents[2]
        # Base then overlays (later wins). Explicit --config applied last.
        layers = [
            here / "config.yaml",
            here.parent / "env.local.yaml",
            here / "env.local.yaml",
            Path.cwd() / "config.yaml",
            Path.cwd() / "env.local.yaml",
        ]
        if path:
            layers.append(Path(path))
        raw: dict[str, Any] = {}
        for candidate in layers:
            if not candidate.is_file():
                continue
            with candidate.open(encoding="utf-8") as fh:
                loaded = yaml.safe_load(fh) or {}
            if isinstance(loaded, dict):
                raw = _deep_merge(raw, loaded)
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Settings:
        data_raw = raw.get("data") or {}
        tdx_raw = data_raw.get("tdx") or {}
        targets_raw = raw.get("targets") or {}
        notify_raw = raw.get("notify") or {}
        email_raw = notify_raw.get("email") or {}
        tdx = TdxSettings(
            root=str(tdx_raw.get("root", TdxSettings.root)),
            vipdoc=str(tdx_raw.get("vipdoc", TdxSettings.vipdoc)),
            exe=str(tdx_raw.get("exe", TdxSettings.exe)),
        )
        data = DataSettings(
            provider=str(data_raw.get("provider", "mock")),
            fallback=data_raw.get("fallback"),
            tdx=tdx,
            sqlite_path=str(data_raw.get("sqlite_path", "data/cache.db")),
            eod_hour=int(data_raw.get("eod_hour", 16)),
            eod_minute=int(data_raw.get("eod_minute", 0)),
            hsjday_url=str(
                data_raw.get("hsjday_url", DataSettings.hsjday_url)
            ),
            auto_download_on_start=bool(
                data_raw.get(
                    "auto_download_on_start",
                    DataSettings.auto_download_on_start,
                )
            ),
            pytdx_workers=int(
                data_raw.get("pytdx_workers", DataSettings.pytdx_workers)
            ),
            pytdx_bar_count=int(
                data_raw.get("pytdx_bar_count", DataSettings.pytdx_bar_count)
            ),
            pytdx_max_symbols=(
                None
                if data_raw.get("pytdx_max_symbols", DataSettings.pytdx_max_symbols)
                is None
                else int(data_raw["pytdx_max_symbols"])
            ),
            global_enabled=bool(
                data_raw.get("global_enabled", DataSettings.global_enabled)
            ),
            auto_sync_minute_on_start=bool(
                data_raw.get(
                    "auto_sync_minute_on_start",
                    DataSettings.auto_sync_minute_on_start,
                )
            ),
            minute_sync_codes=_parse_str_tuple(
                data_raw.get("minute_sync_codes"),
                DataSettings.minute_sync_codes,
            ),
            minute_sync_freqs=_parse_str_tuple(
                data_raw.get("minute_sync_freqs"),
                DataSettings.minute_sync_freqs,
            ),
            minute_sync_bar_count=int(
                data_raw.get(
                    "minute_sync_bar_count",
                    DataSettings.minute_sync_bar_count,
                )
            ),
            auto_sync_finance_on_start=bool(
                data_raw.get(
                    "auto_sync_finance_on_start",
                    DataSettings.auto_sync_finance_on_start,
                )
            ),
            sync_finance_with_day=bool(
                data_raw.get(
                    "sync_finance_with_day",
                    DataSettings.sync_finance_with_day,
                )
            ),
            finance_sync_workers=int(
                data_raw.get(
                    "finance_sync_workers",
                    DataSettings.finance_sync_workers,
                )
            ),
        )
        targets = TargetSettings(
            annual_return_min=float(
                targets_raw.get("annual_return_min", 0.05)
            ),
            annual_return_max=float(
                targets_raw.get("annual_return_max", 0.10)
            ),
            max_drawdown=float(targets_raw.get("max_drawdown", 0.15)),
            max_position_pct=float(targets_raw.get("max_position_pct", 0.20)),
            max_total_exposure=float(
                targets_raw.get("max_total_exposure", 0.80)
            ),
        )
        email = EmailNotifySettings(
            enabled=bool(email_raw.get("enabled", False)),
            smtp_host=str(email_raw.get("smtp_host", EmailNotifySettings.smtp_host)),
            smtp_port=int(email_raw.get("smtp_port", 465)),
            smtp_user=str(email_raw.get("smtp_user", "")),
            smtp_password=str(email_raw.get("smtp_password", "")),
            mail_to=str(email_raw.get("mail_to", "")),
            use_ssl=bool(email_raw.get("use_ssl", True)),
        )
        return cls(
            data=data,
            targets=targets,
            notify=NotifySettings(email=email),
            log_level=str(raw.get("log_level", "INFO")),
        )


def _parse_str_tuple(value: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return tuple(default)
    if isinstance(value, str):
        parts = [p.strip() for p in value.split(",") if p.strip()]
        return tuple(parts) if parts else tuple(default)
    if isinstance(value, (list, tuple)):
        parts = [str(p).strip() for p in value if str(p).strip()]
        return tuple(parts) if parts else tuple(default)
    return tuple(default)


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in overlay.items():
        if (
            key in out
            and isinstance(out[key], dict)
            and isinstance(value, dict)
        ):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def resolve_sqlite_path(settings: Settings, base: Path | None = None) -> Path:
    base = base or Path(__file__).resolve().parents[2]
    path = Path(settings.data.sqlite_path)
    return path if path.is_absolute() else base / path
