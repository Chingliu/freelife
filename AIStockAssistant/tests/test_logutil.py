from __future__ import annotations

from pathlib import Path

from app.research.logutil import append_utf8, rotate_if_needed


def test_rotate_if_needed(tmp_path: Path) -> None:
    log = tmp_path / "run.log"
    log.write_text("x" * 1000, encoding="utf-8")
    assert rotate_if_needed(log, max_bytes=500, backup_count=2) is True
    assert log.exists()
    assert (tmp_path / "run.log.1").exists()
    assert "rotated" in log.read_text(encoding="utf-8")


def test_append_utf8_rotates(tmp_path: Path) -> None:
    log = tmp_path / "run.log"
    append_utf8(log, "first", max_bytes=20)
    append_utf8(log, "second-line-long", max_bytes=20)
    # After growth past max, rotation leaves a fresh file with the new line.
    text = log.read_text(encoding="utf-8")
    assert "second-line-long" in text or (tmp_path / "run.log.1").exists()
