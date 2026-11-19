from __future__ import annotations

import logging
import time
from datetime import date
from pathlib import Path
from typing import Any

from app.config.settings import Settings
from app.data.provider import IDataProvider
from app.data.registry import DEFAULT_REGISTRY
from app.research.ai.analyst import analyze_bars_and_results
from app.research.ai.playbook import (
    email_body_html,
    email_summary_text,
    render_daily_playbook,
)
from app.research.backtest.engine import BacktestEngine
from app.research.backtest.horizons import enrich_result_horizons
from app.research.backtest.splits import holdout_last_years, oos_metrics_for_result
from app.research.backtest.walk_forward import walk_forward as run_walk_forward
from app.research.data.etf_universe import (
    BROAD_ETFS,
    default_broad_codes,
    default_research_codes,
    list_research_etfs,
)
from app.research.data.feed import ResearchDataFeed
from app.research.notify.chart_talk import (
    collect_inline_images,
    generate_chart_talk,
)
from app.research.notify.email_smtp import (
    EmailNotifyConfig,
    send_email_with_attachment,
)
from app.research.pipeline import PipelineRunLog
from app.research.strategies import (
    DEFAULT_STRATEGY_IDS,
    create_strategy,
    list_research_strategies,
)

logger = logging.getLogger(__name__)


class ResearchService:
    """ETF strategy research facade (Phase 1 + Phase 2 lab)."""

    def __init__(
        self,
        settings: Settings | None = None,
        provider: IDataProvider | None = None,
    ) -> None:
        self.settings = settings or Settings.load()
        self.provider = provider or DEFAULT_REGISTRY.create(self.settings)
        vipdoc = Path(self.settings.data.tdx.vipdoc)
        self.feed = ResearchDataFeed(self.provider, vipdoc=vipdoc)
        self.engine = BacktestEngine()
        self._cross_etf_cache: dict[str, dict[str, Any]] | None = None
        self._cross_etf_cache_as_of: str | None = None

    def data_status(self, codes: list[str] | None = None) -> dict[str, Any]:
        return self.feed.data_status(codes)

    def list_etfs(self) -> list[dict[str, str]]:
        return list_research_etfs()

    def list_strategies(self) -> list[dict[str, str]]:
        return list_research_strategies()

    def backtest_one(
        self,
        code: str,
        strategy_id: str,
        start: date | None = None,
        end: date | None = None,
    ) -> dict[str, Any]:
        bars = self.feed.daily_bars(code, start=start, end=end)
        strategy = create_strategy(strategy_id)
        result = self.engine.run(strategy, bars, code=code.lower())
        payload = result.to_dict()
        payload.update(enrich_result_horizons(result))
        if bars and result.equity_curve:
            bounds = holdout_last_years(bars, n=1.0)
            dates = [d for d, _ in result.equity_curve]
            equity = [e for _, e in result.equity_curve]
            payload["oos"] = oos_metrics_for_result(
                equity, dates, list(result.positions), list(result.trades), bounds
            )
        return payload

    def backtest_all(
        self,
        code: str,
        strategy_ids: list[str] | None = None,
        start: date | None = None,
        end: date | None = None,
        *,
        attach_cross_etf: bool = False,
        cross_etf_by_strategy: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        code = code.lower()
        bars = self.feed.daily_bars(code, start=start, end=end)
        if len(bars) < 60:
            raise ValueError(
                f"insufficient daily bars for {code}: got {len(bars)}, need >= 60"
            )
        ids = strategy_ids or list(DEFAULT_STRATEGY_IDS)
        results = []
        for sid in ids:
            strategy = create_strategy(sid)
            results.append(self.engine.run(strategy, bars, code=code))
        as_of = bars[-1].trade_date.isoformat() if bars else ""
        cross = cross_etf_by_strategy
        if cross is None and attach_cross_etf:
            cross = self.cross_etf_scores(strategy_ids=ids)
        analysis = analyze_bars_and_results(
            code,
            bars,
            results,
            provider_id=self.feed.provider_id,
            as_of=as_of,
            cross_etf_by_strategy=cross,
        )
        return analysis

    def compare_etfs(
        self,
        codes: list[str] | None = None,
        strategy_id: str = "ma_20_60",
    ) -> dict[str, Any]:
        codes = codes or [e.code for e in BROAD_ETFS]
        rows = []
        for code in codes:
            rows.append(self.backtest_one(code, strategy_id))
        rows.sort(
            key=lambda r: r.get("metrics", {}).get("calmar", -999), reverse=True
        )
        return {
            "strategy_id": strategy_id,
            "provider_id": self.feed.provider_id,
            "as_of": self.feed.as_of().isoformat() if self.feed.as_of() else None,
            "results": rows,
        }

    def generalize_strategy(
        self,
        strategy_id: str,
        codes: list[str] | None = None,
        *,
        max_mdd: float = 0.35,
        min_pass_ratio: float = 0.5,
    ) -> dict[str, Any]:
        """
        Cross-ETF generalization: same strategy on broad ETFs.
        Prefer sample-out (近1年) Calmar; pass = calmar>0 and MDD<max_mdd.
        """
        codes = codes or default_broad_codes()
        per_etf: list[dict[str, Any]] = []
        calmars: list[float] = []
        for code in codes:
            code = code.lower()
            try:
                bars = self.feed.daily_bars(code)
                if len(bars) < 60:
                    per_etf.append(
                        {
                            "code": code,
                            "status": "insufficient",
                            "pass": False,
                        }
                    )
                    continue
                strategy = create_strategy(strategy_id)
                result = self.engine.run(strategy, bars, code=code)
                bounds = holdout_last_years(bars, n=1.0)
                dates = [d for d, _ in result.equity_curve]
                equity = [e for _, e in result.equity_curve]
                oos = oos_metrics_for_result(
                    equity,
                    dates,
                    list(result.positions),
                    list(result.trades),
                    bounds,
                )
                test = oos.get("test") or {}
                cal = test.get("calmar")
                mdd = test.get("max_drawdown")
                if test.get("status") != "ok" or cal is None:
                    # fallback full-sample
                    cal = result.metrics.calmar
                    mdd = result.metrics.max_drawdown
                    src = "full"
                else:
                    src = "oos_test"
                ok = float(cal) > 0 and (mdd is None or float(mdd) < max_mdd)
                if cal is not None:
                    calmars.append(float(cal))
                per_etf.append(
                    {
                        "code": code,
                        "status": "ok",
                        "metric_source": src,
                        "calmar": round(float(cal), 3) if cal is not None else None,
                        "max_drawdown": round(float(mdd), 4) if mdd is not None else None,
                        "annual_return": test.get("annual_return")
                        if src == "oos_test"
                        else round(result.metrics.annual_return, 4),
                        "pass": ok,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                per_etf.append(
                    {
                        "code": code,
                        "status": "error",
                        "reason": f"{type(exc).__name__}: {exc}",
                        "pass": False,
                    }
                )

        evaluated = [r for r in per_etf if r.get("status") == "ok"]
        n = len(evaluated)
        pass_count = sum(1 for r in evaluated if r.get("pass"))
        pos_count = sum(
            1 for r in evaluated if r.get("calmar") is not None and float(r["calmar"]) > 0
        )
        median = (
            sorted(calmars)[len(calmars) // 2] if calmars else None
        )
        pass_ratio = pass_count / n if n else 0.0
        positive_calmar_ratio = pos_count / n if n else 0.0
        # dispersion: stdev of calmars / (|mean|+eps)
        disp = None
        if len(calmars) >= 2:
            mean = sum(calmars) / len(calmars)
            var = sum((c - mean) ** 2 for c in calmars) / len(calmars)
            disp = round((var ** 0.5) / (abs(mean) + 1e-6), 3)
        crossed = pass_ratio >= min_pass_ratio and (median is not None and median > 0)
        score = round(
            0.5 * positive_calmar_ratio
            + 0.3 * pass_ratio
            + 0.2 * (1.0 if median and median > 0 else 0.0),
            3,
        )
        return {
            "strategy_id": strategy_id,
            "provider_id": self.feed.provider_id,
            "as_of": self.feed.as_of().isoformat() if self.feed.as_of() else None,
            "codes": codes,
            "per_etf": per_etf,
            "pass_count": pass_count,
            "evaluated": n,
            "positive_calmar_ratio": round(positive_calmar_ratio, 3),
            "median_calmar": round(median, 3) if median is not None else None,
            "rank_dispersion": disp,
            "score": score,
            "pass": crossed,
            "max_mdd": max_mdd,
            "min_pass_ratio": min_pass_ratio,
        }

    def cross_etf_scores(
        self,
        strategy_ids: list[str] | None = None,
        codes: list[str] | None = None,
        *,
        use_cache: bool = True,
    ) -> dict[str, dict[str, Any]]:
        """Map strategy_id -> generalization summary (cached per as_of)."""
        as_of = self.feed.as_of().isoformat() if self.feed.as_of() else ""
        ids = strategy_ids or list(DEFAULT_STRATEGY_IDS)
        if (
            use_cache
            and self._cross_etf_cache is not None
            and self._cross_etf_cache_as_of == as_of
            and all(sid in self._cross_etf_cache for sid in ids)
        ):
            return {sid: self._cross_etf_cache[sid] for sid in ids}

        out: dict[str, dict[str, Any]] = {}
        for sid in ids:
            g = self.generalize_strategy(sid, codes=codes)
            out[sid] = {
                "score": g["score"],
                "pass": g["pass"],
                "positive_calmar_ratio": g["positive_calmar_ratio"],
                "median_calmar": g["median_calmar"],
                "pass_count": g["pass_count"],
                "evaluated": g["evaluated"],
            }
        self._cross_etf_cache = {
            **(self._cross_etf_cache or {}),
            **out,
        }
        self._cross_etf_cache_as_of = as_of
        return out

    def walk_forward_strategy(
        self,
        code: str,
        strategy_id: str,
        *,
        train_years: float = 3.0,
        test_years: float = 1.0,
        step_years: float = 1.0,
    ) -> dict[str, Any]:
        bars = self.feed.daily_bars(code)
        wf = run_walk_forward(
            lambda: create_strategy(strategy_id),
            bars,
            train_years=train_years,
            test_years=test_years,
            step_years=step_years,
            engine=self.engine,
            code=code.lower(),
        )
        wf["code"] = code.lower()
        wf["provider_id"] = self.feed.provider_id
        wf["as_of"] = bars[-1].trade_date.isoformat() if bars else None
        return wf

    def daily_research_report(
        self,
        codes: list[str] | None = None,
        *,
        chart_dir: str | Path | None = None,
        attach_cross_etf: bool = False,
    ) -> dict[str, Any]:
        codes = codes or default_research_codes()
        cross = None
        if attach_cross_etf:
            try:
                cross = self.cross_etf_scores()
            except Exception as exc:  # noqa: BLE001
                logger.warning("cross_etf_scores failed: %s", exc)
                cross = None
        sections: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []
        for code in codes:
            code = code.lower().strip()
            if not code:
                continue
            try:
                analysis = self.backtest_all(
                    code, cross_etf_by_strategy=cross
                )
            except Exception as exc:  # noqa: BLE001
                skipped.append({"code": code, "reason": f"{type(exc).__name__}: {exc}"})
                continue
            section: dict[str, Any] = {
                "code": code,
                "regime": analysis["regime"],
                "decision": analysis["decision"],
                "top3": analysis["comparison"][:3],
                "comparison": analysis["comparison"],
                "report_markdown": analysis["report_markdown"],
                "llm_prompt_daily": analysis["llm_prompt_daily"],
                "as_of": analysis.get("as_of"),
            }
            if chart_dir is not None:
                try:
                    bars = self.feed.daily_bars(code)
                    day = str(analysis.get("as_of") or "")[:10]
                    out = Path(chart_dir) / day if day else Path(chart_dir)
                    section["chart_talk"] = generate_chart_talk(
                        code,
                        bars,
                        regime=analysis["regime"],
                        decision=analysis["decision"],
                        comparison=analysis["comparison"],
                        out_dir=out,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "chart_talk failed for %s: %s", code, exc, exc_info=True
                    )
                    section["chart_error"] = f"{type(exc).__name__}: {exc}"
            sections.append(section)
        as_of = self.feed.as_of().isoformat() if self.feed.as_of() else None
        if sections and not as_of:
            as_of = sections[0].get("as_of")
        report_md = render_daily_playbook(
            provider_id=self.feed.provider_id,
            as_of=as_of,
            sections=sections,
            skipped=skipped,
        )
        return {
            "provider_id": self.feed.provider_id,
            "as_of": as_of,
            "data_status": self.data_status(codes),
            "sections": sections,
            "skipped": skipped,
            "codes_ok": [s["code"] for s in sections],
            "codes_skip": skipped,
            "report_markdown": report_md,
        }

    def email_config(self) -> EmailNotifyConfig:
        e = self.settings.notify.email
        return EmailNotifyConfig(
            enabled=e.enabled,
            smtp_host=e.smtp_host,
            smtp_port=e.smtp_port,
            smtp_user=e.smtp_user,
            smtp_password=e.smtp_password,
            mail_to=e.mail_to or e.smtp_user,
            use_ssl=e.use_ssl,
        )

    def send_notify_test(self) -> dict[str, Any]:
        cfg = self.email_config()
        cfg.enabled = True
        result = send_email_with_attachment(
            cfg,
            subject="ETF后市指南 SMTP 测试",
            body_text=(
                "这是 AIStockAssistant 研究平台的 SMTP 连通性测试邮件。\n"
                "若收到此信，说明授权码与 smtp.qq.com 配置正常。\n"
            ),
        )
        return {
            "ok": result.ok,
            "stage": result.stage,
            "error": result.error,
            "detail": result.detail,
        }

    def run_daily_playbook(
        self,
        *,
        codes: list[str] | None = None,
        out_dir: str | Path = "reports/daily",
        notify: bool = True,
        sync: bool = False,
        force_sync: bool = False,
        attach_cross_etf: bool = False,
    ) -> dict[str, Any]:
        """Sync(optional) → generate playbook → save → email; write diagnostics."""
        out_path = Path(out_dir)
        if not out_path.is_absolute():
            root = Path(__file__).resolve().parents[2]
            out_path = root / out_path
        run = PipelineRunLog(out_dir=out_path)

        sync_ok = True
        if sync:
            t0 = time.perf_counter()
            try:
                from app.data.tdx_sync import DataSyncJob

                adapter = DEFAULT_REGISTRY.create_sync(self.settings, self.provider)
                if hasattr(adapter, "download"):
                    adapter.download = True  # type: ignore[attr-defined]
                job = DataSyncJob(self.settings, self.provider, adapter)
                result = job.run(force=force_sync or True)
                sync_ok = bool(result.ok)
                run.as_of = result.as_of.isoformat() if result.as_of else None
                run.append(
                    "sync_eod",
                    ok=sync_ok,
                    error=None if sync_ok else result.message,
                    duration_ms=(time.perf_counter() - t0) * 1000.0,
                    detail={"message": result.message, "as_of": run.as_of},
                )
            except Exception as exc:  # noqa: BLE001
                sync_ok = False
                run.append(
                    "sync_eod",
                    ok=False,
                    error=f"{type(exc).__name__}: {exc}",
                    duration_ms=(time.perf_counter() - t0) * 1000.0,
                )
        else:
            run.append(
                "sync_eod",
                ok=True,
                detail={"skipped": True, "as_of": (
                    self.feed.as_of().isoformat() if self.feed.as_of() else None
                )},
            )

        t0 = time.perf_counter()
        report_ok = False
        report: dict[str, Any] = {}
        md_path: Path | None = None
        charts_root = out_path / "charts"
        try:
            report = self.daily_research_report(
                codes,
                chart_dir=charts_root,
                attach_cross_etf=attach_cross_etf,
            )
            run.as_of = report.get("as_of") or run.as_of
            day = (run.as_of or date.today().isoformat())[:10]
            # Avoid colliding with legacy daily files when evaluating in a subdir
            # that still shares the same as_of day name.
            md_path = out_path / f"{day}.md"
            md_path.write_text(report["report_markdown"], encoding="utf-8")
            # Disk HTML uses relative chart paths; email uses CID (built below).
            html_disk = email_body_html(
                report.get("sections", []),
                report.get("as_of") or day,
                provider_id=str(report.get("provider_id") or ""),
                skipped=list(report.get("codes_skip") or []),
                image_mode="relative",
            )
            html_path = out_path / f"{day}.html"
            html_path.write_text(html_disk, encoding="utf-8")
            json_path = out_path / f"{day}.json"
            slim = {
                "provider_id": report.get("provider_id"),
                "as_of": report.get("as_of"),
                "phase": "v2",
                "attach_cross_etf": attach_cross_etf,
                "codes_ok": report.get("codes_ok"),
                "codes_skip": report.get("codes_skip"),
                "decisions": [
                    {
                        "code": s["code"],
                        "decision": s["decision"],
                        "regime": {
                            k: s["regime"].get(k)
                            for k in (
                                "trend",
                                "trend_strength",
                                "volatility",
                                "rsi_state",
                                "preferred_strategies",
                                "avoid_strategies",
                                "candidate_set",
                            )
                        },
                        "top3": [
                            {
                                "strategy_id": r.get("strategy_id"),
                                "lifecycle": r.get("lifecycle"),
                                "evidence_grade": r.get("evidence_grade"),
                                "oos_pass": r.get("oos_pass"),
                                "calmar": r.get("calmar"),
                            }
                            for r in (s.get("top3") or [])
                        ],
                        "chart_error": s.get("chart_error"),
                        "has_charts": bool(s.get("chart_talk")),
                    }
                    for s in report.get("sections", [])
                ],
            }
            json_path.write_text(
                __import__("json").dumps(slim, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            report_ok = bool(report.get("sections"))
            n_charts = sum(1 for s in report.get("sections", []) if s.get("chart_talk"))
            run.append(
                "report_generate",
                ok=report_ok,
                error=None if report_ok else "no sections produced",
                duration_ms=(time.perf_counter() - t0) * 1000.0,
                detail={
                    "path": str(md_path),
                    "html_path": str(html_path),
                    "charts_dir": str(charts_root / day),
                    "charts_ok": n_charts,
                    "bytes": md_path.stat().st_size,
                    "codes_ok": report.get("codes_ok"),
                    "codes_skip": report.get("codes_skip"),
                },
            )
        except Exception as exc:  # noqa: BLE001
            run.append(
                "report_generate",
                ok=False,
                error=f"{type(exc).__name__}: {exc}",
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )

        email_ok = True
        if notify and report_ok and md_path is not None:
            t0 = time.perf_counter()
            cfg = self.email_config()
            tiers = ",".join(
                f"{s['decision']['name']}:{s['decision']['tier']}"
                for s in report.get("sections", [])[:6]
            )
            subject = f"ETF看图说话 {run.as_of} | {tiers}"
            body = email_summary_text(report.get("sections", []), run.as_of)
            html_path = out_path / f"{(run.as_of or date.today().isoformat())[:10]}.html"
            html_body = email_body_html(
                report.get("sections", []),
                run.as_of,
                provider_id=str(report.get("provider_id") or ""),
                skipped=list(report.get("codes_skip") or []),
                image_mode="cid",
            )
            inline = collect_inline_images(report.get("sections", []))
            extra: list[tuple[Path, str]] = []
            if html_path.is_file():
                extra.append((html_path, html_path.name))
            # PNG fallback attachments (some clients strip CID)
            for path, cid in inline:
                extra.append((path, path.name))
            result = send_email_with_attachment(
                cfg,
                subject=subject[:180],
                body_text=body,
                body_html=html_body,
                attachment_path=md_path,
                attachment_name=md_path.name,
                extra_attachments=extra,
                inline_images=inline,
            )
            email_ok = result.ok
            run.append(
                "email_send",
                ok=result.ok,
                error=result.error,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
                detail={
                    "stage": result.stage,
                    **(result.detail or {}),
                },
            )
        elif notify and not report_ok:
            email_ok = False
            run.append(
                "email_send",
                ok=False,
                error="skipped: report not generated",
                detail={"stage": "skip"},
            )
        else:
            run.append(
                "email_send",
                ok=True,
                detail={"skipped": True, "reason": "notify disabled"},
            )

        status = run.finish(
            report_ok=report_ok, sync_ok=sync_ok, email_ok=email_ok
        )
        return {
            "status": status,
            "report_path": str(md_path) if md_path else None,
            "exit_code": status["exit_code"],
            "report": {
                "as_of": report.get("as_of"),
                "codes_ok": report.get("codes_ok"),
                "codes_skip": report.get("codes_skip"),
            }
            if report
            else {},
        }

    def get_minute_bars(
        self,
        code: str,
        freq: str = "1m",
        limit: int = 100,
        *,
        auto_sync: bool = True,
        max_bars: int = 2400,
    ) -> dict:
        """Read local minute bars; optionally pytdx-sync into vipdoc when missing."""
        code = code.lower()
        bars = self.feed.minute_bars(code, freq=freq)
        sync_note = None
        if not bars and auto_sync and self.feed.vipdoc is not None:
            from app.data.pytdx_minute_updater import sync_minute_to_vipdoc

            result = sync_minute_to_vipdoc(
                self.feed.vipdoc,
                code,
                freq=freq,
                max_bars=max_bars,
                replace=True,
            )
            sync_note = result.message
            if result.ok:
                bars = self.feed.minute_bars(code, freq=freq)

        tail = bars[-limit:] if limit > 0 else bars
        note = None
        if not bars:
            note = sync_note or (
                "本地 vipdoc minline/fzline 无数据，且 pytdx 同步失败；日线研究不受影响"
            )
        elif sync_note:
            note = sync_note
        return {
            "code": code,
            "freq": freq,
            "count": len(bars),
            "available": len(bars) > 0,
            "note": note,
            "bars": [
                {
                    "time": b.trade_time.isoformat(sep=" "),
                    "open": b.open,
                    "high": b.high,
                    "low": b.low,
                    "close": b.close,
                    "volume": b.volume,
                    "amount": b.amount,
                }
                for b in tail
            ],
        }

    def sync_minute(
        self,
        code: str,
        freq: str = "1m",
        max_bars: int = 2400,
        replace: bool = True,
    ) -> dict:
        if self.feed.vipdoc is None:
            return {"ok": False, "message": "vipdoc not configured"}
        from app.data.pytdx_minute_updater import sync_minute_to_vipdoc

        result = sync_minute_to_vipdoc(
            self.feed.vipdoc,
            code,
            freq=freq,
            max_bars=max_bars,
            replace=replace,
        )
        return {
            "ok": result.ok,
            "message": result.message,
            "code": result.code,
            "freq": result.freq,
            "bars_written": result.bars_written,
            "path": result.path,
            "available": self.feed.minute_available(result.code or code, freq),
        }
