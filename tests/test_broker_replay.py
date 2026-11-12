from __future__ import annotations

from datetime import datetime, timedelta, timezone

from options_structure_trader.analytics import PerformanceReporter, ReplayRunner, TradeManagementResearch
from options_structure_trader.broker import StandalonePaperBroker
from options_structure_trader.db import Repository
from options_structure_trader.engines import ConfluenceEngine, ReclaimSetupDetector, TradeConstructor
from options_structure_trader.models import Bar, Mode, ReplayRequest
from options_structure_trader.config import PROJECT_ROOT
from options_structure_trader.service import OptionsStructureTraderService


def make_stack(settings):
    repo = Repository(settings.path("database.path"), PROJECT_ROOT / "migrations")
    detector = ReclaimSetupDetector(settings, ConfluenceEngine(settings), TradeConstructor(settings))
    return repo, detector


def test_paper_fill_same_bar_resolves_to_stop(settings, long_scan):
    repo, detector = make_stack(settings)
    setup = detector.detect(long_scan)
    repo.store_setup(setup)
    broker = StandalonePaperBroker(settings, repo)
    trade = broker.accept(setup, Mode.PRODUCTION)
    bar = Bar(ticker="TEST", bar_start_utc=long_scan.confirmation_bar.bar_end_utc,
              bar_end_utc=long_scan.confirmation_bar.bar_end_utc + timedelta(minutes=5),
              open=trade.planned_entry, high=setup.trade_plan.targets[0] + 1,
              low=setup.trade_plan.stop_initial - 1, close=trade.planned_entry, volume=1000, atr=.5)
    trade = broker.on_bar(trade, bar)
    assert trade.status == "closed"
    assert trade.exit_reason == "stop_loss"
    assert trade.realized_r < 0


def test_pending_order_expires(settings, long_scan):
    repo, detector = make_stack(settings)
    setup = detector.detect(long_scan)
    repo.store_setup(setup)
    broker = StandalonePaperBroker(settings, repo)
    trade = broker.accept(setup, Mode.PRODUCTION)
    for index in range(3):
        start = long_scan.confirmation_bar.bar_end_utc + timedelta(minutes=5 * index)
        bar = Bar(ticker="TEST", bar_start_utc=start, bar_end_utc=start + timedelta(minutes=5),
                  open=110, high=111, low=109, close=110, volume=1000, atr=.5)
        trade = broker.on_bar(trade, bar)
    assert trade.status == "expired"


def test_replay_determinism_and_lookahead(settings, long_scan):
    _, detector = make_stack(settings)
    runner = ReplayRunner(detector)
    request = ReplayRequest(snapshots=[long_scan])
    first, second = runner.run(request), runner.run(request)
    assert first["determinism_hash"] == second["determinism_hash"]
    bad = long_scan.model_copy(deep=True)
    bad.level.known_at_utc = bad.confirmation_bar.bar_end_utc
    result = runner.run(ReplayRequest(snapshots=[bad]))
    assert result["lookahead_rejections"] == 1


def test_shadow_is_excluded_from_production_metrics(settings, long_scan):
    repo, detector = make_stack(settings)
    setup = detector.detect(long_scan)
    repo.store_setup(setup)
    broker = StandalonePaperBroker(settings, repo)
    broker.accept(setup, Mode.SHADOW)
    assert PerformanceReporter(repo).summary(Mode.PRODUCTION)["open_count"] == 0
    assert PerformanceReporter(repo).summary(Mode.SHADOW)["open_count"] == 1


def test_csv_and_parquet_export_handles_mixed_variants(settings, long_scan, tmp_path):
    repo, detector = make_stack(settings)
    setup = detector.detect(long_scan)
    repo.store_setup(setup)
    repo.store_variant(setup.setup_event_id, "stop_buffer_atr", "0.3", {"value": .3})
    repo.store_variant(setup.setup_event_id, "breakeven", "after_TP1", {"value": "after_TP1"})
    paths = PerformanceReporter(repo).export(tmp_path / "exports")
    assert len(paths) == 8
    assert all(__import__("pathlib").Path(path).exists() for path in paths.values())


def test_trade_management_scaleout_executes_tp2_tp3_and_accounts_r(settings, long_scan, tmp_path):
    service = OptionsStructureTraderService(settings)
    research = TradeManagementResearch(service.repository, settings, service.watchlist, tmp_path)
    trade = {"trade_id": "trade_test", "setup_event_id": "setup_test", "ticker": "TEST", "side": "LONG",
             "actual_fill_price": 100, "planned_entry": 100, "stop_initial": 99,
             "targets": [101, 102, 103], "created_at_utc": long_scan.confirmation_bar.bar_end_utc.isoformat(),
             "opened_at_utc": long_scan.confirmation_bar.bar_end_utc.isoformat(), "realized_r": 0}
    setup = {"setup_event_id": "setup_test", "signal_snapshot": {}, "score": {}}
    start = long_scan.confirmation_bar.bar_end_utc
    bars = [
        Bar(ticker="TEST", bar_start_utc=start, bar_end_utc=start + timedelta(minutes=5),
            open=100, high=101.2, low=99.5, close=101, volume=1000, atr=.5).model_dump(mode="json"),
        Bar(ticker="TEST", bar_start_utc=start + timedelta(minutes=5), bar_end_utc=start + timedelta(minutes=10),
            open=101, high=102.2, low=100.5, close=102, volume=1000, atr=.5).model_dump(mode="json"),
        Bar(ticker="TEST", bar_start_utc=start + timedelta(minutes=10), bar_end_utc=start + timedelta(minutes=15),
            open=102, high=103.2, low=101.5, close=103, volume=1000, atr=.5).model_dump(mode="json"),
    ]
    spec = next(item for item in research._variant_specs(trade) if item["version"] == "TM_V1_SCALEOUT_33_33_34")
    replay = research._simulate(trade, setup, spec, bars)
    event_types = [event["event_type"] for event in replay["events"]]
    assert "TP2_PARTIAL" in event_types
    assert "TP3_EXIT" in event_types
    assert replay["final_r"] == 2.01
    assert replay["events"][-1]["remaining_fraction"] == 0


def test_trade_management_delayed_be_waits_until_one_r_or_tp2(settings, long_scan, tmp_path):
    service = OptionsStructureTraderService(settings)
    research = TradeManagementResearch(service.repository, settings, service.watchlist, tmp_path)
    trade = {"trade_id": "trade_test", "setup_event_id": "setup_test", "ticker": "TEST", "side": "LONG",
             "actual_fill_price": 100, "planned_entry": 100, "stop_initial": 98,
             "targets": [101, 102, 104], "created_at_utc": long_scan.confirmation_bar.bar_end_utc.isoformat(),
             "opened_at_utc": long_scan.confirmation_bar.bar_end_utc.isoformat(), "realized_r": 0}
    setup = {"setup_event_id": "setup_test", "signal_snapshot": {}, "score": {}}
    start = long_scan.confirmation_bar.bar_end_utc
    bars = [
        Bar(ticker="TEST", bar_start_utc=start, bar_end_utc=start + timedelta(minutes=5),
            open=100, high=101.1, low=99.2, close=100.8, volume=1000, atr=.5).model_dump(mode="json"),
        Bar(ticker="TEST", bar_start_utc=start + timedelta(minutes=5), bar_end_utc=start + timedelta(minutes=10),
            open=100.8, high=101.5, low=99.5, close=101.2, volume=1000, atr=.5).model_dump(mode="json"),
        Bar(ticker="TEST", bar_start_utc=start + timedelta(minutes=10), bar_end_utc=start + timedelta(minutes=15),
            open=101.2, high=102.2, low=100.8, close=102, volume=1000, atr=.5).model_dump(mode="json"),
        Bar(ticker="TEST", bar_start_utc=start + timedelta(minutes=15), bar_end_utc=start + timedelta(minutes=20),
            open=102, high=102.1, low=99.9, close=100, volume=1000, atr=.5).model_dump(mode="json"),
    ]
    spec = next(item for item in research._variant_specs(trade) if item["version"] == "TM_V6_STRUCTURE_TARGETS_DELAYED_BE")
    replay = research._simulate(trade, setup, spec, bars)
    events = replay["events"]
    tp1_index = next(index for index, event in enumerate(events) if event["event_type"] == "TP1_PARTIAL")
    stop_move_index = next(index for index, event in enumerate(events) if event["event_type"] == "STOP_MOVE")
    assert stop_move_index > tp1_index
    assert events[-1]["event_type"] == "BREAKEVEN_EXIT"
    assert round(sum(event["realized_r_event"] for event in events), 6) == replay["final_r"]


def test_trade_management_report_is_deterministic_and_does_not_mutate_history(settings, long_scan, tmp_path):
    service = OptionsStructureTraderService(settings)
    setup = service.detector.detect(long_scan)
    service.repository.store_setup(setup)
    trade = service.broker.accept(setup, Mode.SHADOW)
    fill_bar = Bar(ticker="TEST", bar_start_utc=long_scan.confirmation_bar.bar_end_utc,
                   bar_end_utc=long_scan.confirmation_bar.bar_end_utc + timedelta(minutes=5),
                   open=100.5, high=101, low=100.4, close=100.8, volume=1000, atr=.5)
    trade = service.broker.on_bar(trade, fill_bar)
    close_bar = Bar(ticker="TEST", bar_start_utc=fill_bar.bar_end_utc,
                    bar_end_utc=fill_bar.bar_end_utc + timedelta(minutes=5),
                    open=100.8, high=106, low=100.7, close=105, volume=1000, atr=.5)
    stop_bar = Bar(ticker="TEST", bar_start_utc=close_bar.bar_end_utc,
                   bar_end_utc=close_bar.bar_end_utc + timedelta(minutes=5),
                   open=105, high=105.2, low=100.4, close=100.5, volume=1000, atr=.5)
    service.repository.store_bar(close_bar)
    trade = service.broker.on_bar(trade, close_bar)
    service.repository.store_bar(stop_bar)
    service.broker.on_bar(trade, stop_bar)
    before = service.repository.list_json("paper_trades", limit=100)
    first = TradeManagementResearch(service.repository, settings, service.watchlist, tmp_path).generate()
    second = TradeManagementResearch(service.repository, settings, service.watchlist, tmp_path).generate()
    after = service.repository.list_json("paper_trades", limit=100)
    assert before == after
    assert first["summary"]["closed_trades_replayed"] == second["summary"]["closed_trades_replayed"]
    assert first["variant_summaries"] == second["variant_summaries"]
    assert first["summary"]["closed_trades_replayed"] == 1


def test_forward_management_ab_creates_paired_branches_without_duplicate_setups(settings, long_scan):
    service = OptionsStructureTraderService(settings)
    scan = long_scan.model_copy(deep=True)
    scan.source_mode = "REAL_TEST_PRICE"
    setup, trade = service.process_scan_input(scan, open_paper=True)

    assert setup is not None and trade is not None
    assert len(service.repository.list_json("setup_events", limit=100)) == 1
    branches = service.repository.list_json("trade_management_branches", limit=100)
    assert {row["branch"] for row in branches} == {"A", "B"}
    assert {row["parent_setup_id"] for row in branches} == {setup.setup_event_id}


def test_forward_management_ab_updates_branch_partials_runner_and_be(settings, long_scan):
    service = OptionsStructureTraderService(settings)
    scan = long_scan.model_copy(deep=True)
    scan.source_mode = "REAL_TEST_PRICE"
    setup, _ = service.process_scan_input(scan, open_paper=True)
    start = scan.confirmation_bar.bar_end_utc
    fill = Bar(ticker="TEST", bar_start_utc=start, bar_end_utc=start + timedelta(minutes=5),
               open=100.5, high=100.8, low=100.4, close=100.7, volume=1000, atr=.5)
    tp1 = Bar(ticker="TEST", bar_start_utc=fill.bar_end_utc, bar_end_utc=fill.bar_end_utc + timedelta(minutes=5),
              open=100.7, high=105.5, low=100.6, close=105, volume=1000, atr=.5)
    runner = Bar(ticker="TEST", bar_start_utc=tp1.bar_end_utc, bar_end_utc=tp1.bar_end_utc + timedelta(minutes=5),
                 open=105, high=112.5, low=104.8, close=112, volume=1000, atr=.5)

    service.forward_management_ab.update_for_bar("TEST", fill)
    service.forward_management_ab.update_for_bar("TEST", tp1)
    service.forward_management_ab.update_for_bar("TEST", runner)

    branches = {row["branch"]: row for row in service.repository.list_json("trade_management_branches", limit=100)}
    assert branches["A"]["status"] == "partial"
    assert branches["B"]["status"] == "closed"
    assert any(event["event_type"] == "RUNNER_EXIT" for event in branches["B"]["events"])
    assert branches["B"]["runner_contribution_r"] > 0
    assert any(event["event_type"] == "STOP_MOVE" for event in branches["A"]["events"])
    assert branches["A"]["parent_setup_id"] == setup.setup_event_id


def test_forward_management_ab_report_and_status(settings, long_scan, tmp_path):
    service = OptionsStructureTraderService(settings)
    service.forward_management_ab.output_root = tmp_path
    scan = long_scan.model_copy(deep=True)
    scan.source_mode = "REAL_TEST_PRICE"
    service.process_scan_input(scan, open_paper=True)
    status = service.forward_management_ab_status()
    assert status["paired_parent_setups"] == 1
    report = service.phase2d4_forward_management_ab()
    assert __import__("pathlib").Path(report["markdown_path"]).exists()
    assert report["status"]["acceptance_target"] == 100


def test_edge_discovery_uses_one_row_per_parent_setup(settings, long_scan, tmp_path):
    service = OptionsStructureTraderService(settings)
    service.edge_discovery.output_root = tmp_path
    scan = long_scan.model_copy(deep=True)
    scan.source_mode = "REAL_TEST_PRICE"

    setup, trade = service.process_scan_input(scan, open_paper=True)
    assert setup is not None and trade is not None
    assert len(service.repository.list_json("trade_management_branches", limit=100)) == 2

    report = service.phase2d5_edge_discovery("2026-08-03")

    assert __import__("pathlib").Path(report["markdown_path"]).exists()
    assert __import__("pathlib").Path(report["parquet_path"]).exists()
    assert report["report"]["rows"] == 1
    assert "edge_by_symbol.csv" in [__import__("pathlib").Path(path).name for path in report["csv_paths"]]


def test_forward_edge_validation_is_prospective_only(settings, long_scan, tmp_path):
    service = OptionsStructureTraderService(settings)
    service.forward_edge_validation.output_root = tmp_path
    old_scan = long_scan.model_copy(deep=True)
    old_scan.source_mode = "REAL_TEST_PRICE"
    old_setup, _ = service.process_scan_input(old_scan, open_paper=False)

    assert old_setup is not None
    assert service.repository.list_json("forward_edge_memberships", limit=100) == []

    activation = datetime(2026, 9, 3, 15, 0, tzinfo=timezone.utc)
    now = datetime(2026, 9, 3, 16, 0, tzinfo=timezone.utc)
    service.forward_edge_validation.activate(force=True, activated_at=activation)
    new_scan = long_scan.model_copy(deep=True)
    new_scan.source_mode = "REAL_TEST_PRICE"
    new_scan.level.known_at_utc = now - timedelta(hours=1)
    new_scan.previous_bar.bar_start_utc = now - timedelta(minutes=10)
    new_scan.previous_bar.bar_end_utc = now - timedelta(minutes=5)
    new_scan.confirmation_bar.bar_start_utc = now - timedelta(minutes=5)
    new_scan.confirmation_bar.bar_end_utc = now
    new_scan.ticker_state.timestamp_utc = now
    new_scan.guard.evaluated_at_utc = now
    new_setup, _ = service.process_scan_input(new_scan, open_paper=False)

    memberships = service.repository.list_json("forward_edge_memberships", limit=100)
    keys = {(row["parent_setup_id"], row["cohort"], row["management_version"]) for row in memberships}
    assert new_setup is not None
    assert old_setup.setup_event_id not in {row["parent_setup_id"] for row in memberships}
    assert (new_setup.setup_event_id, "A_ALL_LONG", "TM_V0_CURRENT") in keys
    assert (new_setup.setup_event_id, "A_ALL_LONG", "TM_V3_TP1_PLUS_RUNNER") in keys
    assert (new_setup.setup_event_id, "H_LONG_GAMMA_FLIP", "TM_V0_CURRENT") in keys

    report = service.phase2d6_forward_edge_validation()
    assert __import__("pathlib").Path(report["markdown_path"]).exists()
    assert report["report"]["unique_forward_parent_setups"] == 1
    assert "forward_edge_cohorts.csv" in [__import__("pathlib").Path(path).name for path in report["csv_paths"]]


def test_forward_edge_validation_short_failure_diagnostic(settings, long_scan, tmp_path):
    service = OptionsStructureTraderService(settings)
    service.forward_edge_validation.output_root = tmp_path
    activation = datetime(2026, 9, 3, 15, 0, tzinfo=timezone.utc)
    now = datetime(2026, 9, 3, 16, 5, tzinfo=timezone.utc)
    service.forward_edge_validation.activate(force=True, activated_at=activation)

    scan = long_scan.model_copy(deep=True)
    scan.source_mode = "REAL_TEST_PRICE"
    scan.level.known_at_utc = now - timedelta(hours=1)
    scan.previous_bar.bar_start_utc = now - timedelta(minutes=10)
    scan.previous_bar.bar_end_utc = now - timedelta(minutes=5)
    scan.previous_bar.open = 100.2
    scan.previous_bar.high = 100.45
    scan.previous_bar.low = 99.8
    scan.previous_bar.close = 100.3
    scan.confirmation_bar.bar_start_utc = now - timedelta(minutes=5)
    scan.confirmation_bar.bar_end_utc = now
    scan.confirmation_bar.open = 100.3
    scan.confirmation_bar.high = 100.6
    scan.confirmation_bar.low = 99.2
    scan.confirmation_bar.close = 99.5
    scan.confirmation_bar.atr = 0.6
    scan.ticker_state.timestamp_utc = now
    scan.ticker_state.spot_price = 99.5
    scan.ticker_state.bid = 99.49
    scan.ticker_state.ask = 99.51
    scan.ticker_state.last = 99.5
    scan.features.flow_direction = "bearish"
    scan.target_nodes = [96, 94, 92]
    scan.guard.evaluated_at_utc = now

    setup, _ = service.process_scan_input(scan, open_paper=True)
    assert setup is not None and setup.side.value == "SHORT"
    diagnostics = service.repository.list_json("short_failure_analysis", limit=100)
    assert len(diagnostics) == 1
    assert diagnostics[0]["parent_setup_id"] == setup.setup_event_id
    assert diagnostics[0]["time_of_day"] == "11:30-13:00"

    report = service.phase2d6_forward_edge_validation()
    assert report["report"]["short_diagnostics"] == 1


def _store_bearish_trend_bars(service, ticker: str, at: datetime, start_price: float = 100) -> None:
    for index in range(13):
        bar_end = at - timedelta(minutes=(12 - index) * 5)
        close = start_price - index * 0.45
        service.repository.store_bar(Bar(
            ticker=ticker, bar_start_utc=bar_end - timedelta(minutes=5), bar_end_utc=bar_end,
            open=close + 0.15, high=close + 0.25, low=close - 0.25, close=close,
            volume=1000, atr=0.5, source="test_price"))


def test_phase2d7_short_midday_cohort_is_prospective_and_alignment_populated(settings, long_scan, tmp_path):
    service = OptionsStructureTraderService(settings)
    service.short_failure_decomposition.output_root = tmp_path
    activation = datetime(2026, 9, 3, 17, 0, tzinfo=timezone.utc)
    now = datetime(2026, 9, 3, 17, 5, tzinfo=timezone.utc)
    service.forward_edge_validation.activate(force=True, activated_at=activation - timedelta(hours=1))
    service.short_failure_decomposition.activate_phase2d7(force=True, activated_at=activation)
    for ticker in ("SPY", "QQQ", "TEST"):
        _store_bearish_trend_bars(service, ticker, now)

    scan = long_scan.model_copy(deep=True)
    scan.source_mode = "REAL_TEST_PRICE"
    scan.level.known_at_utc = now - timedelta(hours=1)
    scan.previous_bar.bar_start_utc = now - timedelta(minutes=10)
    scan.previous_bar.bar_end_utc = now - timedelta(minutes=5)
    scan.previous_bar.open = 100.2
    scan.previous_bar.high = 100.45
    scan.previous_bar.low = 99.8
    scan.previous_bar.close = 100.3
    scan.confirmation_bar.bar_start_utc = now - timedelta(minutes=5)
    scan.confirmation_bar.bar_end_utc = now
    scan.confirmation_bar.open = 100.3
    scan.confirmation_bar.high = 100.6
    scan.confirmation_bar.low = 99.2
    scan.confirmation_bar.close = 99.5
    scan.confirmation_bar.atr = 0.6
    scan.ticker_state.timestamp_utc = now
    scan.ticker_state.spot_price = 99.5
    scan.ticker_state.bid = 99.49
    scan.ticker_state.ask = 99.51
    scan.ticker_state.last = 99.5
    scan.features.flow_direction = "bearish"
    scan.target_nodes = [96, 94, 92]
    scan.guard.evaluated_at_utc = now

    setup, _ = service.process_scan_input(scan, open_paper=False)
    memberships = service.repository.list_json("forward_edge_memberships", limit=100)
    membership_keys = {(row["parent_setup_id"], row["cohort"], row["management_version"]) for row in memberships}
    diagnostics = service.repository.list_json("short_failure_analysis", limit=100)

    assert setup is not None and setup.side.value == "SHORT"
    assert (setup.setup_event_id, "SHORT_13_00_14_30", "TM_V0_CURRENT") in membership_keys
    assert (setup.setup_event_id, "SHORT_13_00_14_30", "TM_V3_TP1_PLUS_RUNNER") in membership_keys
    assert (setup.setup_event_id, "E_SHORT_MARKET_ALIGNED", "TM_V0_CURRENT") in membership_keys
    assert diagnostics[0]["short_alignment_class"] in {"FULLY_ALIGNED", "MARKET_ALIGNED"}
    assert diagnostics[0]["SPY_15m_trend"] == "BEARISH"
    assert diagnostics[0]["QQQ_15m_trend"] == "BEARISH"


def test_phase2d7_report_writes_short_decomposition_outputs(settings, long_scan, tmp_path):
    service = OptionsStructureTraderService(settings)
    service.short_failure_decomposition.output_root = tmp_path
    activation = datetime(2026, 9, 3, 17, 0, tzinfo=timezone.utc)
    now = datetime(2026, 9, 3, 17, 5, tzinfo=timezone.utc)
    service.forward_edge_validation.activate(force=True, activated_at=activation - timedelta(hours=1))
    service.short_failure_decomposition.activate_phase2d7(force=True, activated_at=activation)
    for ticker in ("SPY", "QQQ", "TEST"):
        _store_bearish_trend_bars(service, ticker, now)

    scan = long_scan.model_copy(deep=True)
    scan.source_mode = "REAL_TEST_PRICE"
    scan.level.known_at_utc = now - timedelta(hours=1)
    scan.previous_bar.bar_start_utc = now - timedelta(minutes=10)
    scan.previous_bar.bar_end_utc = now - timedelta(minutes=5)
    scan.previous_bar.open = 100.2
    scan.previous_bar.high = 100.45
    scan.previous_bar.low = 99.8
    scan.previous_bar.close = 100.3
    scan.confirmation_bar.bar_start_utc = now - timedelta(minutes=5)
    scan.confirmation_bar.bar_end_utc = now
    scan.confirmation_bar.open = 100.3
    scan.confirmation_bar.high = 100.6
    scan.confirmation_bar.low = 99.2
    scan.confirmation_bar.close = 99.5
    scan.confirmation_bar.atr = 0.6
    scan.ticker_state.timestamp_utc = now
    scan.ticker_state.spot_price = 99.5
    scan.ticker_state.bid = 99.49
    scan.ticker_state.ask = 99.51
    scan.ticker_state.last = 99.5
    scan.features.flow_direction = "bearish"
    scan.target_nodes = [96, 94, 92]
    scan.guard.evaluated_at_utc = now

    setup, trade = service.process_scan_input(scan, open_paper=True)
    assert setup is not None and trade is not None
    fill_bar = Bar(ticker="TEST", bar_start_utc=now, bar_end_utc=now + timedelta(minutes=5),
                   open=99.5, high=99.6, low=98.6, close=98.8, volume=2000, atr=0.6)
    stop_bar = Bar(ticker="TEST", bar_start_utc=fill_bar.bar_end_utc,
                   bar_end_utc=fill_bar.bar_end_utc + timedelta(minutes=5),
                   open=98.8, high=101.0, low=98.7, close=100.9, volume=2500, atr=0.6)
    service.repository.store_bar(fill_bar)
    trade = service.broker.on_bar(trade, fill_bar)
    service.repository.store_bar(stop_bar)
    service.broker.on_bar(trade, stop_bar)

    report = service.phase2d7_short_failure_decomposition()

    assert __import__("pathlib").Path(report["markdown_path"]).exists()
    assert report["report"]["resolved_short_setups"] == 1
    assert "short_path_decomposition.csv" in [
        __import__("pathlib").Path(path).name for path in report["csv_paths"]]
    assert "short_management_replay.csv" in [
        __import__("pathlib").Path(path).name for path in report["csv_paths"]]
