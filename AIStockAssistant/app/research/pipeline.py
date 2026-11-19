from __future__ import annotations

import json
import logging
import socket
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from app.research.logutil import DEFAULT_RUN_LOG_MAX_BYTES, append_utf8

logger = logging.getLogger(__name__)


@dataclass
class PipelineRunLog:
    """Collect step diagnostics for run.log + status.json."""

    out_dir: Path
    run_id: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    steps: dict[str, Any] = field(default_factory=dict)
    started_at: float = field(default_factory=time.perf_counter)
    as_of: str | None = None
    run_log_max_bytes: int = DEFAULT_RUN_LOG_MAX_BYTES

    def __post_init__(self) -> None:
        self.out_dir = Path(self.out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._log_path = self.out_dir / "run.log"
        self.append(
            "start",
            ok=True,
            detail={
                "run_id": self.run_id,
                "hostname": socket.gethostname(),
                "python": sys.executable,
                "out_dir": str(self.out_dir.resolve()),
            },
        )

    def append(
        self,
        step: str,
        *,
        ok: bool,
        error: str | None = None,
        duration_ms: float | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "ok": ok,
            "error": error,
            "duration_ms": duration_ms,
            "detail": detail or {},
        }
        self.steps[step] = payload
        ts = datetime.now().isoformat(timespec="seconds")
        line = f"[{ts}] step={step} ok={ok}"
        if duration_ms is not None:
            line += f" duration_ms={duration_ms:.0f}"
        if error:
            line += f" error={error}"
        if detail:
            # Never dump secrets; detail should already be scrubbed by callers.
            safe = {k: v for k, v in detail.items() if "password" not in k.lower()}
            line += f" detail={json.dumps(safe, ensure_ascii=False, default=str)}"
        append_utf8(self._log_path, line, max_bytes=self.run_log_max_bytes)
        if ok:
            logger.info("%s", line)
        else:
            logger.warning("%s", line)

    def finish(self, *, report_ok: bool, sync_ok: bool, email_ok: bool) -> dict[str, Any]:
        if not report_ok:
            overall = "failed"
            exit_code = 1
        elif sync_ok and email_ok:
            overall = "ok"
            exit_code = 0
        else:
            overall = "partial"
            exit_code = 2
        elapsed_ms = (time.perf_counter() - self.started_at) * 1000.0
        day = (self.as_of or datetime.now().date().isoformat())[:10]
        status = {
            "run_id": self.run_id,
            "overall": overall,
            "as_of": self.as_of,
            "steps": self.steps,
            "exit_code": exit_code,
            "elapsed_ms": round(elapsed_ms, 1),
        }
        self.append(
            "finish",
            ok=overall == "ok",
            duration_ms=elapsed_ms,
            detail={"overall": overall, "exit_code": exit_code},
        )
        status_path = self.out_dir / f"{day}.status.json"
        status_path.write_text(
            json.dumps(status, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        status["status_path"] = str(status_path)
        status["log_path"] = str(self._log_path)
        return status
