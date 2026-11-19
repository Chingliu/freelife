"""Bounded append logs for daily playbook (prevent unbounded disk growth)."""

from __future__ import annotations

import os
from pathlib import Path

# Structured step log stays small; verbose spam is capped separately.
DEFAULT_RUN_LOG_MAX_BYTES = 2 * 1024 * 1024  # 2 MiB
DEFAULT_VERBOSE_LOG_MAX_BYTES = 5 * 1024 * 1024  # 5 MiB
DEFAULT_BACKUP_COUNT = 3


def rotate_if_needed(
    path: Path,
    *,
    max_bytes: int = DEFAULT_RUN_LOG_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
) -> bool:
    """
    If ``path`` exceeds ``max_bytes``, rotate to ``path.1`` .. ``path.N`` and
    truncate ``path``. Returns True when a rotation happened.
    """
    path = Path(path)
    if max_bytes <= 0 or backup_count < 0:
        return False
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        return False
    if size < max_bytes:
        return False

    for i in range(backup_count, 0, -1):
        src = path if i == 1 else Path(f"{path}.{i - 1}")
        dst = Path(f"{path}.{i}")
        if i == backup_count and dst.exists():
            try:
                dst.unlink()
            except OSError:
                pass
        if src.exists():
            try:
                os.replace(src, dst)
            except OSError:
                # Best-effort: if replace fails, still try to truncate primary.
                pass

    # Ensure a fresh primary log exists (replace may have moved it to .1).
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        fh.write(
            f"# rotated previous log exceeded {max_bytes} bytes; "
            f"kept {backup_count} backup(s)\n"
        )
    return True


def append_utf8(path: Path, line: str, *, max_bytes: int = DEFAULT_RUN_LOG_MAX_BYTES) -> None:
    """Append one line (UTF-8), rotating first if the file is too large."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rotate_if_needed(path, max_bytes=max_bytes)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line if line.endswith("\n") else line + "\n")
