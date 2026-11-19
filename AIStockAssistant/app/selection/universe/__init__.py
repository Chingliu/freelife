"""L1 index constituent universe loader."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from app.selection.types import UniverseSnapshot

INDEX_FILES = {
    "sse50": "sse50.json",
    "csi300": "csi300.json",
    "csi500": "csi500.json",
}


def default_universe_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "universe"


def _parse_as_of(raw: Any) -> date | None:
    if raw is None:
        return None
    if isinstance(raw, date):
        return raw
    text = str(raw).strip()
    if not text:
        return None
    return date.fromisoformat(text[:10])


def load_index_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "index": path.stem,
            "as_of": None,
            "source": "missing",
            "stale": True,
            "codes": [],
        }
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"invalid universe file: {path}")
    codes = data.get("codes") or []
    if not isinstance(codes, list):
        raise ValueError(f"codes must be list: {path}")
    return {
        "index": str(data.get("index") or path.stem),
        "as_of": _parse_as_of(data.get("as_of")),
        "source": str(data.get("source") or "file"),
        "stale": bool(data.get("stale", False)),
        "codes": [str(c).lower() for c in codes if str(c).strip()],
    }


def load_universe(universe_dir: Path | None = None) -> UniverseSnapshot:
    root = Path(universe_dir) if universe_dir else default_universe_dir()
    by_index: dict[str, list[str]] = {}
    gaps: list[str] = []
    as_ofs: list[date] = []
    sources: list[str] = []
    stale = False

    for key, fname in INDEX_FILES.items():
        path = root / fname
        payload = load_index_file(path)
        codes = list(dict.fromkeys(payload["codes"]))
        by_index[key] = codes
        if payload["source"] == "missing" or not codes:
            gaps.append(f"{key}: missing or empty ({path})")
            stale = True
        if payload.get("stale"):
            stale = True
        if payload.get("as_of"):
            as_ofs.append(payload["as_of"])
        sources.append(f"{key}:{payload.get('source')}")

    union: list[str] = []
    seen: set[str] = set()
    for codes in by_index.values():
        for c in codes:
            if c not in seen:
                seen.add(c)
                union.append(c)

    as_of = max(as_ofs) if as_ofs else None
    return UniverseSnapshot(
        as_of=as_of,
        source=";".join(sources) if sources else "empty",
        stale=stale,
        by_index=by_index,
        codes=union,
        gaps=gaps,
    )


def write_index_file(
    path: Path,
    *,
    index: str,
    codes: list[str],
    source: str,
    as_of: date | None = None,
    stale: bool = False,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "index": index,
        "as_of": (as_of or date.today()).isoformat(),
        "source": source,
        "stale": stale,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "codes": [c.lower() for c in codes],
    }
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
