"""Meta providers: ST/suspend, finance cache, capital flow, sectors."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.data.models import FinanceInfo
from app.data.provider import IDataProvider
from app.selection.meta.finance import (
    cache_row_has_fundamentals,
    finance_info_usable,
    finance_with_price,
    last_close_from_bars,
    load_finance_cache,
    resolve_finance,
)
from app.selection.universe import default_universe_dir


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, dict) else {}


class MetaStore:
    """File-backed optional metadata under data/universe/."""

    def __init__(self, universe_dir: Path | None = None, vipdoc: Path | None = None) -> None:
        self.root = Path(universe_dir) if universe_dir else default_universe_dir()
        self.vipdoc = Path(vipdoc) if vipdoc else None
        self._st = _load_json(self.root / "st_flags.json")
        self._suspend = _load_json(self.root / "suspend_flags.json")
        self._finance = _load_json(self.root / "finance_cache.json")
        self._finance_map = load_finance_cache(self.root / "finance_cache.json")
        self._flow = _load_json(self.root / "capital_flow.json")
        self._sectors = _load_json(self.root / "sectors.json")
        self._names = _load_json(self.root / "names.json")

    def reload_finance(self) -> None:
        self._finance = _load_json(self.root / "finance_cache.json")
        self._finance_map = load_finance_cache(self.root / "finance_cache.json")

    @property
    def finance_cache_path(self) -> Path:
        return self.root / "finance_cache.json"

    def finance_row(self, code: str) -> dict[str, Any] | None:
        items = self._finance.get("items") or {}
        raw = items.get(code.lower())
        return dict(raw) if isinstance(raw, dict) else None

    def status(self, *, universe_codes: list[str] | None = None) -> dict[str, Any]:
        items = self._finance.get("items") if isinstance(self._finance.get("items"), dict) else {}
        count = len(items) if isinstance(items, dict) else 0
        coverage = None
        covered = 0
        if universe_codes:
            for c in universe_codes:
                row = items.get(c.lower()) if isinstance(items, dict) else None
                if cache_row_has_fundamentals(row if isinstance(row, dict) else None):
                    covered += 1
            n = len(universe_codes)
            coverage = {
                "universe_n": n,
                "with_fundamentals": covered,
                "ratio": (covered / n) if n else 0.0,
            }
        return {
            "st_flags": bool(self._st.get("flags")),
            "suspend_flags": bool(self._suspend.get("flags")),
            "finance_cache": bool(items),
            "finance_cache_count": count,
            "finance_as_of": self._finance.get("as_of"),
            "finance_synced_at": self._finance.get("synced_at"),
            "finance_coverage": coverage,
            "capital_flow": bool(self._flow.get("items")),
            "sectors": bool(self._sectors.get("map")),
            "names": bool(self._names.get("map")),
            "gaps": self.gaps(universe_codes=universe_codes),
        }

    def gaps(self, *, universe_codes: list[str] | None = None) -> list[str]:
        gaps: list[str] = []
        if not self._st.get("flags"):
            gaps.append("ST flags unavailable (no st_flags.json)")
        if not self._suspend.get("flags"):
            gaps.append("suspend flags unavailable (no suspend_flags.json)")
        items = self._finance.get("items") if isinstance(self._finance.get("items"), dict) else {}
        if not items:
            gaps.append("finance_cache empty — value/quality need selection-sync-finance")
        elif universe_codes:
            covered = sum(
                1
                for c in universe_codes
                if cache_row_has_fundamentals(
                    items.get(c.lower()) if isinstance(items.get(c.lower()), dict) else None
                )
            )
            n = len(universe_codes)
            if covered == 0:
                gaps.append("finance_cache has items but 0% L1 coverage for eps/bps/roe/pe/pb")
            elif covered < n:
                gaps.append(
                    f"finance_cache partial coverage {covered}/{n} "
                    "(run selection-sync-finance to fill)"
                )
            with_cagr = sum(
                1
                for c in universe_codes
                if isinstance(items.get(c.lower()), dict)
                and items[c.lower()].get("profit_cagr") is not None
            )
            if with_cagr < n:
                gaps.append(
                    f"quality_cagr sparse {with_cagr}/{n} "
                    "(single get_finance_info cannot compute CAGR)"
                )
        if not self._flow.get("items"):
            gaps.append("capital_flow unavailable")
        if not self._sectors.get("map"):
            gaps.append("sector map unavailable — industry constraint uses 'unknown'")
        return gaps

    def has_st_flags(self) -> bool:
        return bool(self._st.get("flags"))

    def has_suspend_flags(self) -> bool:
        return bool(self._suspend.get("flags"))

    def is_st(self, code: str) -> bool | None:
        flags = self._st.get("flags") or {}
        if not flags:
            return None
        return bool(flags.get(code.lower()))

    def is_suspended(self, code: str) -> bool | None:
        flags = self._suspend.get("flags") or {}
        if not flags:
            return None
        return bool(flags.get(code.lower()))

    def name(self, code: str) -> str:
        m = self._names.get("map") or {}
        return str(m.get(code.lower()) or "")

    def sector(self, code: str) -> str:
        m = self._sectors.get("map") or {}
        return str(m.get(code.lower()) or "unknown")

    def finance(
        self,
        code: str,
        provider: IDataProvider | None = None,
        *,
        last_close: float | None = None,
        price_as_of: Any = None,
    ) -> FinanceInfo | None:
        c = code.lower()
        row = self.finance_row(c)
        if provider is None:
            if row is None and c not in self._finance_map:
                return None
            return finance_with_price(
                c,
                cache_row=row,
                fin=self._finance_map.get(c),
                last_close=last_close,
                price_as_of=price_as_of,
            )
        cache_rows = {
            k: dict(v)
            for k, v in (self._finance.get("items") or {}).items()
            if isinstance(v, dict)
        }
        return resolve_finance(
            code,
            provider=provider,
            cache=self._finance_map,
            cache_rows=cache_rows,
            vipdoc=self.vipdoc,
            last_close=last_close,
            price_as_of=price_as_of,
        )

    def needs_finance_fetch(self, code: str) -> bool:
        return not cache_row_has_fundamentals(self.finance_row(code))

    def capital_flow(self, code: str) -> dict[str, Any] | None:
        items = self._flow.get("items") or {}
        raw = items.get(code.lower())
        return dict(raw) if isinstance(raw, dict) else None

    def macro_scale(self) -> dict[str, Any]:
        """Optional macro gate from capital_flow.json or sectors.json extras."""
        for blob in (self._flow, self._sectors, self._finance):
            macro = blob.get("macro")
            if isinstance(macro, dict):
                return dict(macro)
        return {}


__all__ = [
    "MetaStore",
    "finance_info_usable",
    "finance_with_price",
    "last_close_from_bars",
]
