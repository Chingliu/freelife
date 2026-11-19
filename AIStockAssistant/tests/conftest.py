from __future__ import annotations

from pathlib import Path

import pytest

from app.config.settings import Settings


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "smoke: end-to-end / local vipdoc sanity checks",
    )


@pytest.fixture(scope="session")
def vipdoc() -> Path:
    """Resolve vipdoc from config.yaml when present, else default Tdx path."""
    cfg = Path(__file__).resolve().parents[1] / "config.yaml"
    if cfg.is_file():
        settings = Settings.load(cfg)
        path = Path(settings.data.tdx.vipdoc)
    else:
        path = Path(r"D:\tdx\vipdoc")
    return path


@pytest.fixture(scope="session")
def require_vipdoc(vipdoc: Path) -> Path:
    if not vipdoc.is_dir():
        pytest.skip(f"tdx vipdoc not present: {vipdoc}")
    return vipdoc
