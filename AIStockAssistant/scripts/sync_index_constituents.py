"""CLI helper: refresh index constituent JSON under data/universe."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.config.settings import Settings
from app.selection.universe.sync import sync_index_constituents


def main() -> int:
    settings = Settings.load()
    root = Path(__file__).resolve().parents[1] / "data" / "universe"
    out = sync_index_constituents(
        universe_dir=root,
        tdx_root=Path(settings.data.tdx.root),
        prefer_csindex=True,
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
