from __future__ import annotations

import argparse
import json
import re

from .models import Mode, ObservationRequest, ScanRequest
from .service import OptionsStructureTraderService


def main() -> None:
    parser = argparse.ArgumentParser(description="Standalone Options Structure Trader")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    daemon = sub.add_parser("daemon")
    daemon.add_argument("--once", action="store_true", help="Run one scheduler heartbeat and exit")
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    scan = sub.add_parser("scan")
    scan.add_argument("--tickers", nargs="*")
    scan.add_argument("--open-paper", action="store_true")
    scan.add_argument("--demo", action="store_true", help="Use deterministic synthetic fixtures")
    observe = sub.add_parser("observe")
    observe.add_argument("--tickers", nargs="*")
    observe.add_argument("--symbols", help="Comma-separated ticker list")
    observe.add_argument("--cycles", type=int, default=1)
    observe.add_argument("--interval-seconds", type=int, default=60)
    observe.add_argument("--interval", help="Polling interval such as 5m or 300s")
    observe.add_argument("--mode", choices=["free-validation", "shadow", "production-paper"],
                         default="free-validation")
    observe.add_argument("--rth-only", action="store_true")
    observe.add_argument("--target-scans", type=int)
    observe.add_argument("--no-paper", action="store_true")
    observe.add_argument("--no-free-fallback", action="store_true")
    sub.add_parser("report")
    sub.add_parser("phase2c-report")
    sub.add_parser("phase2d-report")
    edge = sub.add_parser("phase2d5-edge")
    edge.add_argument("--date")
    forward_edge = sub.add_parser("phase2d6-forward-edge")
    forward_edge.add_argument("--date")
    forward_edge.add_argument("--activate-now", action="store_true",
                              help="Reset Phase 2D.6 activation timestamp to now without relabeling old setups")
    short_decomp = sub.add_parser("phase2d7-short")
    short_decomp.add_argument("--date")
    short_decomp.add_argument("--activate-now", action="store_true",
                              help="Reset Phase 2D.7 activation timestamp to now without relabeling old setups")
    phase4a = sub.add_parser("phase4a-edge")
    phase4a.add_argument("--date")
    phase4b2qa = sub.add_parser("phase4b2-qa")
    phase4b2qa.add_argument("--date", required=True)
    phase4b2qa.add_argument("--no-mark-prefix", action="store_true",
                            help="Generate the QA report without marking pre-fix research rows")
    sub.add_parser(
        "phase4b3-start-clean",
        help="Quarantine invalid no-fill research P/L and start a new clean forward cutoff",
    )
    historical = sub.add_parser("phase3b-historical")
    historical.add_argument("--symbols", help="Comma-separated symbol list")
    historical.add_argument("--period", default="20d", help="Recent underlying period for free yfinance 5m data")
    historical.add_argument("--interval", default="5m", help="Underlying candle interval; 5m is the supported minimum")
    daily = sub.add_parser("daily-report")
    daily.add_argument("--date")
    sub.add_parser("export")
    args = parser.parse_args()
    if args.command == "serve":
        import uvicorn
        uvicorn.run("options_structure_trader.api:app", host=args.host, port=args.port, reload=False)
        return
    service = OptionsStructureTraderService()
    if args.command == "daemon":
        from .scheduler import SchedulerEngine
        engine = SchedulerEngine(service)
        if args.once:
            result = engine.tick()
            print(json.dumps(result, indent=2, default=str))
        else:
            engine.run_forever()
        return
    if args.command == "init":
        result = service.health()
    elif args.command == "scan":
        result = service.scan_once(ScanRequest(tickers=args.tickers, fixture=args.demo, open_paper=args.open_paper))
    elif args.command == "observe":
        tickers = args.tickers
        if args.symbols:
            tickers = [item.strip().upper() for item in args.symbols.split(",") if item.strip()]
        interval_seconds = args.interval_seconds
        if args.interval:
            match = re.fullmatch(r"(\d+)([smh])", args.interval.strip().lower())
            if not match:
                parser.error("--interval must look like 30s, 5m, or 1h")
            scale = {"s": 1, "m": 60, "h": 3600}[match.group(2)]
            interval_seconds = int(match.group(1)) * scale
        cycles = args.cycles if not args.target_scans else 1000
        result = service.run_observation(ObservationRequest(
            tickers=tickers, cycles=cycles, interval_seconds=interval_seconds,
            open_paper=not args.no_paper, include_free_fallback=not args.no_free_fallback,
            mode=args.mode, rth_only=args.rth_only, target_scans=args.target_scans))
    elif args.command == "report":
        result = service.performance.summary(Mode.PRODUCTION)
    elif args.command == "daily-report":
        result = service.daily_reports.generate(args.date)
    elif args.command == "phase2c-report":
        result = service.phase2c_report()
    elif args.command == "phase2d-report":
        result = service.phase2d_report()
    elif args.command == "phase2d5-edge":
        result = service.phase2d5_edge_discovery(args.date)
    elif args.command == "phase2d6-forward-edge":
        if args.activate_now:
            service.forward_edge_validation.activate(force=True)
        result = service.phase2d6_forward_edge_validation(args.date)
    elif args.command == "phase2d7-short":
        if args.activate_now:
            service.short_failure_decomposition.activate_phase2d7(force=True)
        result = service.phase2d7_short_failure_decomposition(args.date)
    elif args.command == "phase4a-edge":
        result = service.phase4a_multitimeframe_edge_report(args.date)
    elif args.command == "phase4b2-qa":
        result = service.phase4b2_research_integrity_qa(args.date, mark_pre_fix=not args.no_mark_prefix)
    elif args.command == "phase4b3-start-clean":
        result = service.phase4b3_start_clean_forward_validation()
    elif args.command == "phase3b-historical":
        symbols = [item.strip().upper() for item in args.symbols.split(",") if item.strip()] if args.symbols else None
        result = service.phase3b_historical_reconstruction(symbols=symbols, period=args.period, interval=args.interval)
    else:
        result = service.performance.export(service.settings.root / "data" / "exports")
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
