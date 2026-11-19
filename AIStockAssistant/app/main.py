from __future__ import annotations

import argparse
import json

from app.ai.service import AnalysisService
from app.config.logging_config import setup_logging
from app.config.settings import Settings
from app.research.data.etf_universe import default_research_codes
from app.research.service import ResearchService
from app.selection.service import SelectionService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AIStockAssistant CLI")
    parser.add_argument("--config", default=None)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status")
    p_bars = sub.add_parser("bars")
    p_bars.add_argument("code")
    p_screen = sub.add_parser("screen")
    p_screen.add_argument("--limit", type=int, default=20)
    p_rec = sub.add_parser("recommend")
    p_rec.add_argument("code")
    sub.add_parser("report")

    # Phase-1 research platform
    sub.add_parser("research-status")
    sub.add_parser("research-strategies")
    p_rb = sub.add_parser("research-backtest")
    p_rb.add_argument("code")
    p_rb.add_argument("--strategy", default=None, help="single strategy id; default=all")
    p_rr = sub.add_parser("research-report")
    p_rr.add_argument(
        "--codes",
        default=",".join(default_research_codes()),
        help="comma-separated ETF codes",
    )
    p_rp = sub.add_parser("research-playbook")
    p_rp.add_argument(
        "--codes",
        default=",".join(default_research_codes()),
        help="comma-separated ETF codes (default: 6 broad + QDII)",
    )
    p_rp.add_argument(
        "--out-dir",
        default="reports/daily",
        help="output directory for md/json/status/log",
    )
    p_rp.add_argument(
        "--notify",
        action="store_true",
        help="send email after report (requires notify.email in env.local.yaml)",
    )
    p_rp.add_argument(
        "--no-notify",
        action="store_true",
        help="do not send email",
    )
    p_rp.add_argument(
        "--sync",
        action="store_true",
        help="run EOD sync before report",
    )
    p_rp.add_argument(
        "--notify-test",
        action="store_true",
        help="only send a short SMTP test email; skip report",
    )
    p_rp.add_argument(
        "--attach-cross-etf",
        action="store_true",
        help="attach cross-ETF generalization scores (Phase-2; slower)",
    )
    p_rm = sub.add_parser("research-sync-minute")
    p_rm.add_argument("code")
    p_rm.add_argument("--freq", default="1m", choices=["1m", "5m"])
    p_rm.add_argument("--bars", type=int, default=2400)
    p_rmin = sub.add_parser("research-minute")
    p_rmin.add_argument("code")
    p_rmin.add_argument("--freq", default="1m", choices=["1m", "5m"])
    p_rmin.add_argument("--limit", type=int, default=20)
    p_rmin.add_argument("--no-sync", action="store_true")
    p_rg = sub.add_parser("research-generalize")
    p_rg.add_argument("strategy")
    p_rg.add_argument(
        "--codes",
        default="",
        help="comma-separated ETF codes; default broad universe",
    )
    p_rwf = sub.add_parser("research-walk-forward")
    p_rwf.add_argument("code")
    p_rwf.add_argument("strategy")
    p_rwf.add_argument("--train-years", type=float, default=3.0)
    p_rwf.add_argument("--test-years", type=float, default=1.0)
    p_rwf.add_argument("--step-years", type=float, default=1.0)

    # Seven-layer stock selection
    sub.add_parser("selection-status")
    sub.add_parser("selection-universe")
    sub.add_parser("selection-sync-universe")
    sub.add_parser("selection-sync-finance")
    p_sr = sub.add_parser("selection-run")
    p_sr.add_argument("--top", type=int, default=10)
    p_sr.add_argument("--validate", action="store_true")
    p_srep = sub.add_parser("selection-report")
    p_srep.add_argument("code")
    p_srep.add_argument("--validate", action="store_true")
    p_sv = sub.add_parser("selection-validate")
    p_sv.add_argument("--factor", default="")
    p_sv.add_argument("--months", type=int, default=12)
    p_sdr = sub.add_parser("selection-daily")
    p_sdr.add_argument("--top", type=int, default=10)
    p_sdr.add_argument("--validate", action="store_true")
    p_sdr.add_argument("--no-stock-reports", action="store_true")

    args = parser.parse_args(argv)
    settings = Settings.load(args.config)
    setup_logging(settings.log_level)
    svc = AnalysisService(settings)

    if args.cmd == "status":
        print(svc.sync_status())
    elif args.cmd == "bars":
        print(svc.get_daily_bars(args.code)[-5:])
    elif args.cmd == "screen":
        print(svc.screen_stocks(limit=args.limit))
    elif args.cmd == "recommend":
        print(svc.recommend(args.code)["narrative"])
    elif args.cmd == "report":
        print(svc.daily_report())
    elif args.cmd == "research-status":
        print(json.dumps(ResearchService(settings).data_status(), ensure_ascii=False, indent=2))
    elif args.cmd == "research-strategies":
        print(json.dumps(ResearchService(settings).list_strategies(), ensure_ascii=False, indent=2))
    elif args.cmd == "research-backtest":
        rs = ResearchService(settings)
        if args.strategy:
            out = rs.backtest_one(args.code, args.strategy)
        else:
            out = rs.backtest_all(args.code)
            print(out.get("report_markdown", ""))
            out = {k: v for k, v in out.items() if k != "report_markdown"}
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    elif args.cmd == "research-report":
        codes = [c.strip() for c in args.codes.split(",") if c.strip()]
        out = ResearchService(settings).daily_research_report(codes)
        print(out["report_markdown"])
    elif args.cmd == "research-playbook":
        rs = ResearchService(settings)
        if args.notify_test:
            out = rs.send_notify_test()
            print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
            return 0 if out.get("ok") else 2
        codes = [c.strip() for c in args.codes.split(",") if c.strip()]
        # Default: notify if enabled in config unless --no-notify
        do_notify = (not args.no_notify) and (
            args.notify or settings.notify.email.enabled
        )
        out = rs.run_daily_playbook(
            codes=codes,
            out_dir=args.out_dir,
            notify=do_notify,
            sync=args.sync,
            force_sync=args.sync,
            attach_cross_etf=bool(getattr(args, "attach_cross_etf", False)),
        )
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return int(out.get("exit_code", 1))
    elif args.cmd == "research-sync-minute":
        out = ResearchService(settings).sync_minute(
            args.code, freq=args.freq, max_bars=args.bars
        )
        print(json.dumps(out, ensure_ascii=False, indent=2))
    elif args.cmd == "research-minute":
        out = ResearchService(settings).get_minute_bars(
            args.code,
            freq=args.freq,
            limit=args.limit,
            auto_sync=not args.no_sync,
        )
        print(json.dumps(out, ensure_ascii=False, indent=2))
    elif args.cmd == "research-generalize":
        codes = [c.strip() for c in args.codes.split(",") if c.strip()] or None
        out = ResearchService(settings).generalize_strategy(args.strategy, codes=codes)
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    elif args.cmd == "research-walk-forward":
        out = ResearchService(settings).walk_forward_strategy(
            args.code,
            args.strategy,
            train_years=args.train_years,
            test_years=args.test_years,
            step_years=args.step_years,
        )
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    elif args.cmd == "selection-status":
        out = SelectionService(settings).data_status()
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    elif args.cmd == "selection-universe":
        out = SelectionService(settings).universe_snapshot()
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    elif args.cmd == "selection-sync-universe":
        out = SelectionService(settings).sync_universe()
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    elif args.cmd == "selection-sync-finance":
        out = SelectionService(settings).sync_finance()
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    elif args.cmd == "selection-run":
        out = SelectionService(settings).run_daily(
            top_n=args.top, with_validation=bool(args.validate)
        )
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    elif args.cmd == "selection-report":
        out = SelectionService(settings).stock_report(
            args.code, with_validation=bool(args.validate)
        )
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    elif args.cmd == "selection-validate":
        out = SelectionService(settings).factor_validation(
            args.factor, months=args.months, refresh=True
        )
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    elif args.cmd == "selection-daily":
        out = SelectionService(settings).daily_report(
            top_n=args.top,
            with_validation=bool(args.validate),
            include_stock_reports=not args.no_stock_reports,
        )
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
