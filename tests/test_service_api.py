from __future__ import annotations

from fastapi.testclient import TestClient

from options_structure_trader import api
from options_structure_trader.service import OptionsStructureTraderService


def test_service_fixture_scan_is_shadow_only(settings):
    service = OptionsStructureTraderService(settings)
    result = service.scan_once(api.ScanRequest(tickers=["SPY"], fixture=True, open_paper=True))
    assert result["status"] == "completed"
    assert result["setups"] == 1
    setup = result["results"][0]["setup"]
    assert not setup["production_paper_allowed"]
    assert "Synthetic fixture data" in " ".join(setup["blocking_reasons"])
    assert result["results"][0]["trade"]["mode"] == "shadow_paper"


def test_api_health_scan_and_dashboard(settings, monkeypatch):
    monkeypatch.setattr(api, "service", OptionsStructureTraderService(settings))
    client = TestClient(api.app)
    health = client.get("/health")
    assert health.status_code == 200 and health.json()["live_auto_enabled"] is False
    assert client.get("/").status_code == 200
    scan = client.post("/scanner/options-structure/run-once", json={"tickers": ["OKLO"], "fixture": True})
    assert scan.status_code == 200 and scan.json()["scanned"] == 1
    assert client.get("/ticker/OKLO/options-map").json()["levels"]


def test_required_tables_exist(settings):
    service = OptionsStructureTraderService(settings)
    with service.repository.connect() as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    required = {"options_raw_payloads", "options_chain_snapshots", "options_gex_snapshots",
                "options_oi_snapshots", "options_flow_events", "options_flow_aggregates",
                "big_trade_events", "option_levels", "macro_events", "setup_events",
                "signal_snapshots", "paper_trades", "paper_trade_variants", "score_models",
                "score_results", "ablation_runs", "performance_summaries", "market_bars",
                "ticker_states", "scan_observations", "provider_failures",
                "real_ablation_results", "daily_reports", "trade_management_branches",
                "edge_candidates", "forward_edge_activation", "forward_edge_memberships",
                "short_failure_analysis", "phase4a_activation",
                "intraday_options_edge_events", "intraday_options_edge_branches"}
    assert required <= tables


def test_incomplete_payload_rejection_is_audited(settings):
    service = OptionsStructureTraderService(settings)
    result = service.evaluate_normalized_payload({"ticker": "SPY"})
    assert result["status"] == "rejected"
    events = service.repository.list_json("audit_events")
    assert events[0]["event_type"] == "normalized_input_rejected"
    assert events[0]["reasons"]


def test_phase_2c_api_surfaces(settings, monkeypatch):
    service = OptionsStructureTraderService(settings)
    service.phase3b_historical_reconstruction = lambda **kwargs: {
        "report": {"status": "MOCKED"},
        "markdown_path": "PHASE_3B_HISTORICAL_RECONSTRUCTION.md",
    }
    monkeypatch.setattr(api, "service", service)
    client = TestClient(api.app)
    status = client.get("/observation/status")
    assert status.status_code == 200
    assert status.json()["targets"]["valid_scans"] == 50
    assert status.json()["optimization_locked"] is True
    assert status.json()["live_trading_disabled"] is True
    assert status.json()["targets"]["free_validation_valid_scans"] == 50
    report = client.get("/reports/daily")
    assert report.status_code == 200
    assert report.json()["report"]["valid_real_scans"] == 0
    phase2c = client.get("/reports/phase-2c")
    assert phase2c.status_code == 200
    assert phase2c.json()["report"]["status"] == "EMPIRICAL_ACCEPTANCE_PENDING"
    assert client.get("/config/status").json()["paper_lanes"] == [
        "shadow_paper", "free_validation_paper", "production_paper"]
    assert client.get("/paper/open?mode=free_validation_paper").status_code == 200
    scheduler = client.get("/scheduler/status")
    assert scheduler.status_code == 200 and scheduler.json()["live_trading_disabled"] is True
    watchlist = client.get("/watchlist/status")
    assert 50 <= watchlist.json()["configured_symbols"] <= 100
    phase2d = client.get("/reports/phase-2d")
    assert phase2d.status_code == 200
    assert phase2d.json()["report"]["status"] == "EMPIRICAL_ACCEPTANCE_PENDING"
    assert client.get("/performance/real-ablation").status_code == 200
    paper = client.get("/paper/status")
    assert paper.status_code == 200
    assert paper.json()["summary"]["paper_entries_opened"] == 0
    assert "unique_reclaim_events" in paper.json()["summary"]
    assert "profit_factor" in paper.json()["summary"]
    assert paper.json()["synthetic_test_records_excluded"]["paper_trades"] >= 0
    phase2d2 = client.get("/reports/phase-2d2-paper-diagnostic")
    assert phase2d2.status_code == 200
    assert phase2d2.json()["report"]["diagnostic"]["production_trades"] == 0
    assert client.get("/management/ab/status").status_code == 200
    assert client.get("/reports/phase-2d4-forward-management-ab").status_code == 200
    assert client.get("/reports/phase-2d5-edge-discovery").status_code == 200
    assert client.get("/reports/phase-2d6-forward-edge-validation").status_code == 200
    assert client.get("/reports/phase-2d7-short-failure-decomposition").status_code == 200
    assert client.get("/research/multitimeframe-edge/status").status_code == 200
    assert client.get("/reports/phase-4a-multitimeframe-edge").status_code == 200
    assert client.get("/research/edge-decomposition/status").status_code == 200
    assert client.get("/reports/phase-4b1-edge-decomposition").status_code == 200
    assert client.get("/research/phase-4b2/status").status_code == 200
    assert client.get("/reports/phase-4b2-prospective").status_code == 200
    assert client.get("/reports/phase-3b-historical-reconstruction?symbols=SPY&period=5d").status_code == 200


def test_real_reclaim_duplicate_is_suppressed_prospectively(settings, long_scan):
    service = OptionsStructureTraderService(settings)
    first_scan = long_scan.model_copy(deep=True)
    first_scan.source_mode = "REAL_TEST_PRICE"
    second_scan = long_scan.model_copy(deep=True)
    second_scan.source_mode = "REAL_TEST_PRICE"

    first_setup, first_trade = service.process_scan_input(first_scan, open_paper=True)
    second_setup, second_trade = service.process_scan_input(second_scan, open_paper=True)

    assert first_setup is not None and first_trade is not None
    assert second_setup is None and second_trade is None
    audits = service.repository.list_json("audit_events", limit=10)
    assert any(event["outcome"] == "duplicate_setup_suppressed" for event in audits)
    assert len(service.repository.list_json("setup_events", limit=100)) == 1
