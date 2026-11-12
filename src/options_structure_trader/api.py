from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import PROJECT_ROOT
from .models import Mode, ObservationRequest, ReplayRequest, ScanRequest
from .service import OptionsStructureTraderService


service = OptionsStructureTraderService()
app = FastAPI(title="Options Structure Trader", version="0.1.0",
              description="Standalone research and paper-trading service. Live auto execution is unavailable.")
static_dir = PROJECT_ROOT / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", include_in_schema=False)
def dashboard() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.get("/health")
def health():
    return service.health()


@app.get("/sources/status")
def sources_status():
    return service.source_status()


@app.get("/sources/health-check")
def sources_health_check(symbol: str = "SPY"):
    return service.provider_health_checks(symbol)


@app.get("/market-data/freshness")
def market_data_freshness():
    return service.market_data_freshness_status()


@app.get("/config/status")
def config_status():
    return {"config_version": service.settings.version,
            "runtime_mode": service.settings.get("system.runtime_mode"),
            "database_path": str(service.repository.path),
            "isolated_standalone_mvp": service.settings.get("system.isolated_standalone_mvp"),
            "live_auto_enabled": False,
            "production_setup_families": service.settings.get("setup_families.production_enabled"),
            "score_model": service.settings.get("scores.active_score_model"),
            "watchlist": {"configured_symbols": len(service.watchlist.entries),
                          "path": str(service.watchlist.config_path)},
            "scheduler": service.settings.get("scheduler"),
            "freshness": {"price_max_seconds": service.settings.get("freshness.price_max_seconds"),
                          "options_structure_max_seconds": service.settings.get("freshness.gex_max_seconds"),
                          "free_validation_price_max_seconds": service.settings.get(
                              "freshness.free_validation_price_max_seconds"),
                          "free_validation_structure_max_seconds": service.settings.get(
                              "freshness.free_validation_gex_max_seconds")},
            "paper_lanes": [Mode.SHADOW.value, Mode.FREE_VALIDATION.value, Mode.PRODUCTION.value],
            "macro_calendar_production_eligible": service.macro_adapter.approved,
            "macro_calendar": service.macro_adapter.status(),
            "observation": service.settings.get("observation"),
            "phase4a": service.settings.get("phase4a")}


@app.get("/macro/events")
def macro_events():
    return [event.model_dump(mode="json") for event in service.events]


@app.get("/macro/guard-status")
def macro_guard_status(ticker: str):
    from datetime import datetime, timezone
    return service.guard.evaluate(ticker.upper(), datetime.now(timezone.utc))


@app.get("/ticker/{ticker}/options-map")
def options_map(ticker: str):
    return service.ticker_map(ticker)


@app.get("/ticker/{ticker}/levels")
def levels(ticker: str):
    return service.repository.list_json("option_levels", "WHERE ticker=?", (ticker.upper(),))


@app.get("/ticker/{ticker}/flow")
def flow(ticker: str):
    return {"ticker": ticker.upper(), "events": [], "aggregates": [],
            "message": "No flow source configured"}


@app.get("/setups/live")
def live_setups(signal_family: str = "OPTIONS_STRUCTURE"):
    if signal_family != "OPTIONS_STRUCTURE":
        return []
    return service.repository.list_json("setup_events", limit=500)


@app.get("/journal/events")
def journal_events(limit: int = Query(100, ge=1, le=1000)):
    return service.repository.list_json("audit_events", limit=limit)


@app.get("/setups/{setup_id}")
def get_setup(setup_id: str):
    setup = service.repository.get_setup(setup_id)
    if not setup:
        raise HTTPException(404, "Setup not found")
    return setup


@app.post("/setups/{setup_id}/paper/accept")
def accept_setup(setup_id: str):
    try:
        return service.accept_setup(setup_id)
    except KeyError:
        raise HTTPException(404, "Setup not found")
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@app.get("/paper/open")
def paper_open(signal_family: str = "OPTIONS_STRUCTURE", mode: Mode | None = None):
    where, params = "WHERE status IN ('pending','open','partial')", []
    if mode:
        where += " AND mode=?"
        params.append(mode.value)
    return service.repository.list_json("paper_trades", where, tuple(params)) if signal_family == "OPTIONS_STRUCTURE" else []


@app.get("/paper/closed")
def paper_closed(signal_family: str = "OPTIONS_STRUCTURE", mode: Mode | None = None):
    where, params = "WHERE status='closed'", []
    if mode:
        where += " AND mode=?"
        params.append(mode.value)
    return service.repository.list_json("paper_trades", where, tuple(params)) if signal_family == "OPTIONS_STRUCTURE" else []


@app.get("/paper/status")
def paper_status():
    return service.paper_mode_status()


@app.get("/reports/phase-2d2-paper-diagnostic")
def phase2d2_paper_diagnostic():
    return service.phase2d2_paper_diagnostic()


@app.get("/reports/phase-2d3-trade-management")
def phase2d3_trade_management():
    return service.phase2d3_trade_management_research()


@app.get("/trade-management/research/status")
def trade_management_research_status():
    return service.phase2d3_trade_management_research()


@app.get("/management/ab/status")
def management_ab_status():
    return service.forward_management_ab_status()


@app.get("/reports/phase-2d4-forward-management-ab")
def phase2d4_forward_management_ab():
    return service.phase2d4_forward_management_ab()


@app.get("/reports/phase-2d5-edge-discovery")
def phase2d5_edge_discovery(report_date: str | None = None):
    return service.phase2d5_edge_discovery(report_date)


@app.get("/reports/phase-2d6-forward-edge-validation")
def phase2d6_forward_edge_validation(report_date: str | None = None):
    return service.phase2d6_forward_edge_validation(report_date)


@app.get("/reports/phase-2d7-short-failure-decomposition")
def phase2d7_short_failure_decomposition(report_date: str | None = None):
    return service.phase2d7_short_failure_decomposition(report_date)


@app.get("/research/multitimeframe-edge/status")
def multitimeframe_edge_status():
    return service.phase4a_multitimeframe_edge_status()


@app.get("/reports/phase-4a-multitimeframe-edge")
def phase4a_multitimeframe_edge(report_date: str | None = None):
    return service.phase4a_multitimeframe_edge_report(report_date)


@app.get("/research/phase-4b2/status")
def phase4b2_prospective_status(report_date: str | None = None):
    return service.phase4b2_prospective_status(report_date)


@app.get("/reports/phase-4b2-prospective")
def phase4b2_prospective_report(report_date: str | None = None):
    return service.phase4b2_prospective_report(report_date)


@app.get("/reports/phase-4b2-research-integrity")
def phase4b2_research_integrity(report_date: str, mark_pre_fix: bool = False):
    return service.phase4b2_research_integrity_qa(report_date, mark_pre_fix=mark_pre_fix)


@app.get("/research/edge-decomposition/status")
def edge_decomposition_status():
    return service.phase4b1_edge_decomposition_status()


@app.get("/reports/phase-4b1-edge-decomposition")
def phase4b1_edge_decomposition():
    return service.phase4b1_edge_decomposition_report()


@app.get("/reports/phase-3b-historical-reconstruction")
def phase3b_historical_reconstruction(symbols: str | None = None, period: str = "20d", interval: str = "5m"):
    parsed = [item.strip().upper() for item in symbols.split(",") if item.strip()] if symbols else None
    return service.phase3b_historical_reconstruction(symbols=parsed, period=period, interval=interval)


@app.get("/performance/summary")
def performance_summary(signal_family: str = "OPTIONS_STRUCTURE", mode: Mode = Mode.PRODUCTION):
    return service.performance.summary(mode) if signal_family == "OPTIONS_STRUCTURE" else {}


@app.get("/performance/by-setup")
def performance_by_setup(signal_family: str = "OPTIONS_STRUCTURE", mode: Mode = Mode.PRODUCTION):
    return service.performance.by_setup(mode) if signal_family == "OPTIONS_STRUCTURE" else []


@app.get("/performance/ablation")
def performance_ablation(signal_family: str = "OPTIONS_STRUCTURE"):
    return {"signal_family": signal_family, "weight_sets": service.scorer.ablation_weight_sets(),
            "variants_recorded": len(service.repository.list_json("paper_trade_variants", limit=100000))}


@app.get("/performance/real-ablation")
def real_ablation(limit: int = Query(5000, ge=1, le=100000)):
    return service.repository.list_json("real_ablation_results", limit=limit)


@app.get("/observation/status")
def observation_status():
    return service.observation_status()


@app.get("/scheduler/status")
def scheduler_status():
    return service.scheduler_status()


@app.get("/watchlist/status")
def watchlist_status():
    return service.watchlist_status()


@app.get("/observations/latest")
def latest_observations(limit: int = Query(100, ge=1, le=1000)):
    return service.repository.list_json("scan_observations", limit=limit)


@app.post("/observation/run")
def run_observation(request: ObservationRequest = ObservationRequest()):
    return service.run_observation(request)


@app.get("/reports/daily")
def daily_report(report_date: str | None = None):
    return service.daily_reports.generate(report_date)


@app.get("/reports/provider-freshness")
def provider_freshness_report(report_date: str | None = None):
    return service.provider_freshness_report(report_date)


@app.get("/reports/phase-2c")
def phase2c_report():
    return service.phase2c_report()


@app.get("/reports/phase-2d")
def phase2d_report():
    return service.phase2d_report()


@app.post("/scanner/options-structure/run-once")
def scan_once(request: ScanRequest = ScanRequest()):
    return service.scan_once(request)


@app.post("/scanner/options-structure/evaluate-normalized")
def evaluate_normalized(payload: dict, open_paper: bool = False):
    return service.evaluate_normalized_payload(payload, open_paper)


@app.post("/replay/options-structure/run")
def replay(request: ReplayRequest):
    return service.replay_snapshots(request)


@app.post("/exports/research")
def export_research():
    return service.performance.export(PROJECT_ROOT / "data" / "exports")
