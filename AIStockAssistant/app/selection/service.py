"""SelectionService facade — seven-layer stock selection."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.config.settings import Settings
from app.data.provider import IDataProvider
from app.data.registry import DEFAULT_REGISTRY
from app.selection.factors.score import list_factor_catalog, score_universe_with_macro
from app.selection.filters import apply_filters, filter_config_dict
from app.selection.meta import MetaStore
from app.selection.rank import rank_top_n
from app.selection.report import build_daily_selection_report, build_stock_report
from app.selection.types import FactorHealth, FactorValue, RankedStock, StockScore
from app.selection.universe import default_universe_dir, load_universe
from app.selection.universe.sync import sync_index_constituents
from app.selection.validation import validate_price_factors

logger = logging.getLogger(__name__)


class SelectionService:
    def __init__(
        self,
        settings: Settings | None = None,
        provider: IDataProvider | None = None,
        universe_dir: Path | None = None,
    ) -> None:
        self.settings = settings or Settings.load()
        self.provider = provider or DEFAULT_REGISTRY.create(self.settings)
        self.universe_dir = Path(universe_dir) if universe_dir else default_universe_dir()
        self.meta = MetaStore(
            self.universe_dir,
            vipdoc=Path(self.settings.data.tdx.vipdoc),
        )
        self._health_cache: dict[str, FactorHealth] | None = None

    def data_status(self) -> dict[str, Any]:
        uni = load_universe(self.universe_dir)
        as_of = self.provider.get_data_as_of()
        sample = uni.codes[:5]
        bar_ready = sum(1 for c in sample if self.provider.get_daily_bars(c))
        meta_status = self.meta.status(universe_codes=uni.codes)
        return {
            "provider_id": self.provider.provider_id,
            "market_as_of": as_of.isoformat() if as_of else None,
            "universe": uni.to_dict(),
            "universe_dir": str(self.universe_dir),
            "sample_bars_ready": f"{bar_ready}/{len(sample)}" if sample else "0/0",
            "meta": meta_status,
            "filter_config": filter_config_dict(),
            "factor_catalog": list_factor_catalog(),
            "gaps": list(uni.gaps) + list(meta_status.get("gaps") or []),
        }

    def sync_finance(self) -> dict[str, Any]:
        """Batch pytdx get_finance_info for L1 universe → finance_cache.json."""
        from app.data.pytdx_finance import refresh_finance_cache

        uni = load_universe(self.universe_dir)
        as_of = self.provider.get_data_as_of()
        result = refresh_finance_cache(
            list(uni.codes),
            self.meta.finance_cache_path,
            workers=self.settings.data.finance_sync_workers,
            as_of=as_of,
        )
        self.meta.reload_finance()
        return {
            "ok": result.ok,
            "message": result.message,
            "codes_requested": result.codes_requested,
            "codes_ok": result.codes_ok,
            "codes_failed": result.codes_failed,
            "path": result.path,
            "provider_id": self.provider.provider_id,
            "as_of": as_of.isoformat() if as_of else None,
            "meta": self.meta.status(universe_codes=uni.codes),
        }

    def universe_snapshot(self) -> dict[str, Any]:
        uni = load_universe(self.universe_dir)
        filt = apply_filters(uni.codes, self.provider, self.meta, as_of=uni.as_of)
        return {
            "provider_id": self.provider.provider_id,
            "universe": uni.to_dict(),
            "filter": filt.to_dict(),
        }

    def sync_universe(self) -> dict[str, Any]:
        tdx_root = Path(self.settings.data.tdx.root)
        return sync_index_constituents(
            universe_dir=self.universe_dir,
            tdx_root=tdx_root if tdx_root.is_dir() else None,
            prefer_csindex=True,
        )

    def get_factor_health(
        self,
        *,
        refresh: bool = False,
        months: int = 12,
        max_codes: int = 80,
    ) -> dict[str, FactorHealth]:
        if self._health_cache is not None and not refresh:
            return self._health_cache
        uni = load_universe(self.universe_dir)
        filt = apply_filters(uni.codes, self.provider, self.meta, as_of=uni.as_of)
        codes = filt.kept[:max_codes] if len(filt.kept) >= 10 else uni.codes[:max_codes]
        logger.info("validating factors on %s codes", len(codes))
        self._health_cache = validate_price_factors(codes, self.provider, months=months)
        return self._health_cache

    def _as_of_str(self, uni_as_of: Any = None) -> str | None:
        as_of = self.provider.get_data_as_of()
        if as_of:
            return as_of.isoformat()
        if uni_as_of is not None:
            return uni_as_of.isoformat() if hasattr(uni_as_of, "isoformat") else str(uni_as_of)
        return None

    def run_daily(
        self,
        *,
        top_n: int = 10,
        max_per_sector: int = 3,
        with_validation: bool = False,
        validation_months: int = 12,
    ) -> dict[str, Any]:
        uni = load_universe(self.universe_dir)
        filt = apply_filters(uni.codes, self.provider, self.meta, as_of=uni.as_of)
        health = None
        if with_validation:
            health = self.get_factor_health(refresh=True, months=validation_months)

        scores, macro = score_universe_with_macro(
            filt.kept,
            self.provider,
            self.meta,
            health=health,
            index_membership=uni.by_index,
        )
        ranked = rank_top_n(scores, top_n=top_n, max_per_sector=max_per_sector)
        return {
            "provider_id": self.provider.provider_id,
            "as_of": self._as_of_str(uni.as_of),
            "universe": uni.to_dict(),
            "filter_audit": filt.to_dict(),
            "macro": macro,
            "scored_count": len(scores),
            "top10": [r.to_dict() for r in ranked],
            "factor_health": {k: v.to_dict() for k, v in (health or {}).items()},
            "data_gaps": list(uni.gaps)
            + list(filt.gaps)
            + list(self.meta.gaps(universe_codes=uni.codes)),
            "disclaimer": "研究观察，非正式投资建议。",
        }

    def stock_report(
        self,
        code: str,
        *,
        with_validation: bool = False,
    ) -> dict[str, Any]:
        code = code.lower()
        health_objs = self.get_factor_health() if with_validation else self._health_cache

        # Cache-miss fallback: single-ticket get_finance_info (not used in run_daily).
        finance_fetch: dict[str, Any] | None = None
        if self.meta.needs_finance_fetch(code):
            from app.data.pytdx_finance import fetch_finance_info, upsert_finance_cache_item

            mapped = fetch_finance_info(code)
            if mapped:
                upsert_finance_cache_item(self.meta.finance_cache_path, code, mapped)
                self.meta.reload_finance()
                finance_fetch = {"ok": True, "source": "pytdx.get_finance_info", "fields": list(mapped)}
            else:
                finance_fetch = {"ok": False, "source": "pytdx.get_finance_info"}

        uni = load_universe(self.universe_dir)
        filt = apply_filters(uni.codes, self.provider, self.meta, as_of=uni.as_of)
        pool = list(filt.kept)
        if code not in pool:
            pool = pool + [code]
        scores, _macro = score_universe_with_macro(
            pool,
            self.provider,
            self.meta,
            health=health_objs,
            index_membership=uni.by_index,
        )
        by_code = {s.code: s for s in scores}
        if code not in by_code:
            return {
                "ok": False,
                "error": f"no score for {code}",
                "provider_id": self.provider.provider_id,
            }

        ranked = rank_top_n(scores, top_n=10, max_per_sector=3)
        rank = next((r.rank for r in ranked if r.score.code == code), None)
        report = build_stock_report(
            by_code[code],
            self.provider,
            health=health_objs,
            rank=rank,
            provider_id=self.provider.provider_id,
            as_of=self._as_of_str(uni.as_of),
        )
        if finance_fetch is not None:
            report["finance_fetch"] = finance_fetch
        return report

    def factor_validation(
        self,
        factor_id: str = "",
        *,
        months: int = 12,
        refresh: bool = True,
    ) -> dict[str, Any]:
        health = self.get_factor_health(refresh=refresh, months=months)
        if factor_id.strip():
            fid = factor_id.strip()
            h = health.get(fid)
            if h is None:
                return {"ok": False, "error": f"unknown or unvalidated factor {fid}"}
            return {"ok": True, "factor": h.to_dict(), "provider_id": self.provider.provider_id}
        return {
            "ok": True,
            "factors": {k: v.to_dict() for k, v in health.items()},
            "provider_id": self.provider.provider_id,
        }

    def daily_report(
        self,
        *,
        top_n: int = 10,
        with_validation: bool = False,
        include_stock_reports: bool = True,
    ) -> dict[str, Any]:
        run = self.run_daily(top_n=top_n, with_validation=with_validation)
        health_objs = self._health_cache if with_validation else None
        reports: list[dict[str, Any]] = []
        if include_stock_reports:
            for row in run.get("top10") or []:
                reports.append(self.stock_report(row["code"], with_validation=False))

        ranked: list[RankedStock] = []
        for row in run.get("top10") or []:
            factors = {
                k: FactorValue(**v) for k, v in (row.get("factors") or {}).items()
            }
            ss = StockScore(
                code=row["code"],
                name=row.get("name") or "",
                composite=row.get("composite"),
                factors=factors,
                category_scores=row.get("category_scores") or {},
                sector=row.get("sector") or "unknown",
                indices=list(row.get("indices") or []),
            )
            ranked.append(RankedStock(rank=int(row.get("rank") or 0), score=ss))

        return build_daily_selection_report(
            ranked,
            filter_audit=run.get("filter_audit") or {},
            universe=run.get("universe") or {},
            health=health_objs,
            provider_id=run.get("provider_id") or self.provider.provider_id,
            as_of=run.get("as_of"),
            stock_reports=reports,
        )
