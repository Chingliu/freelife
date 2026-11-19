#!/usr/bin/env python3
"""Daily ETF playbook entry for Windows Task Scheduler.

Prefer this over ``run_daily_etf_playbook.ps1``. The old PowerShell wrapper used
``$ErrorActionPreference=Stop`` + ``2>&1 | Tee-Object`` into ``run.log``, which
aborts the pipeline on the first stderr line (e.g. a Traceback prefix) and also
rewrote logs as UTF-16, ballooning disk use.

Exit codes: 0=ok, 1=report failed, 2=report ok but sync/email partial failure.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = "reports/daily"
DEFAULT_PYTHON = Path(r"D:\freelife\.venv\Scripts\python.exe")


def _ensure_root_on_path() -> None:
    os.chdir(ROOT)
    root_s = str(ROOT)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run daily ETF research playbook")
    p.add_argument("--out-dir", default=DEFAULT_OUT)
    p.add_argument("--codes", default="")
    p.add_argument("--skip-sync", action="store_true", help="do not run EOD sync")
    p.add_argument("--sync", action="store_true", help="force EOD sync (default)")
    p.add_argument("--no-notify", action="store_true")
    p.add_argument("--notify-test", action="store_true")
    p.add_argument(
        "--attach-cross-etf",
        action="store_true",
        help="precompute cross-ETF generalization scores (slower; Phase-2)",
    )
    p.add_argument(
        "--verbose-log-max-mb",
        type=float,
        default=5.0,
        help="rotating verbose.log max size per file (MiB)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    _ensure_root_on_path()

    from app.config.logging_config import setup_logging
    from app.config.settings import Settings
    from app.research.logutil import append_utf8
    from app.research.service import ResearchService

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    verbose_path = out_dir / "verbose.log"
    setup_logging(
        "INFO",
        file_path=verbose_path,
        max_bytes=int(args.verbose_log_max_mb * 1024 * 1024),
        backup_count=3,
    )

    run_log = out_dir / "run.log"
    stamp = datetime.now().isoformat(timespec="seconds")
    append_utf8(run_log, f"[{stamp}] py_runner start python={sys.executable} root={ROOT}")

    settings = Settings.load()
    rs = ResearchService(settings)

    if args.notify_test:
        out = rs.send_notify_test()
        append_utf8(
            run_log,
            f"[{datetime.now().isoformat(timespec='seconds')}] py_runner notify-test "
            f"ok={out.get('ok')} error={out.get('error')}",
        )
        return 0 if out.get("ok") else 2

    codes = [c.strip() for c in args.codes.split(",") if c.strip()]
    do_sync = not args.skip_sync  # default: sync (matches former .ps1)
    do_notify = (not args.no_notify) and settings.notify.email.enabled

    append_utf8(
        run_log,
        f"[{datetime.now().isoformat(timespec='seconds')}] py_runner cmdline "
        f"sync={do_sync} notify={do_notify} out_dir={out_dir}",
    )

    result = rs.run_daily_playbook(
        codes=codes or None,
        out_dir=out_dir,
        notify=do_notify,
        sync=do_sync,
        force_sync=do_sync,
        attach_cross_etf=bool(args.attach_cross_etf),
    )
    code = int(result.get("exit_code", 1))
    append_utf8(
        run_log,
        f"[{datetime.now().isoformat(timespec='seconds')}] py_runner finish exit={code} "
        f"report={result.get('report_path')}",
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
