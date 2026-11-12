from __future__ import annotations

from datetime import timedelta

from options_structure_trader.models import Bar, GexMap
from options_structure_trader.service import OptionsStructureTraderService


def _gex_for(scan) -> GexMap:
    return GexMap(
        ticker="TEST",
        source="test_gex",
        source_timestamp_utc=scan.confirmation_bar.bar_end_utc,
        spot=scan.ticker_state.spot_price,
        gamma_flip=100,
        call_wall=105,
        put_wall=95,
        gamma_regime="POSITIVE_GAMMA",
        confidence_score=0.8,
        free_validation_complete=True,
    )


def _activate(service: OptionsStructureTraderService, scan) -> None:
    activation_time = scan.confirmation_bar.bar_end_utc - timedelta(minutes=1)
    service.multitimeframe_edge_research.activate(force=True, activated_at=activation_time)
    service.multitimeframe_edge_research.activate_phase4b2(force=True, activated_at=activation_time)


def _register(service: OptionsStructureTraderService, scan, *, prior_levels=None, bars=None):
    return service.multitimeframe_edge_research.register_scan(
        run_id="test_run",
        observation_id="obs_test",
        ticker="TEST",
        source_mode="REAL_TEST_PRICE",
        gex=_gex_for(scan),
        current_levels=[scan.level],
        prior_levels=scan.level if False else (prior_levels if prior_levels is not None else [scan.level]),
        bars=bars if bars is not None else [scan.previous_bar, scan.confirmation_bar],
        state=scan.ticker_state,
        guard=scan.guard,
        eligibility=scan.eligibility,
        providers={"price": "test_price", "structure": "test_gex"},
        setup=None,
        outcome="free_validation_valid_no_setup",
    )


def test_far_away_same_side_price_is_not_breakout(settings, long_scan):
    service = OptionsStructureTraderService(settings)
    _activate(service, long_scan)
    previous = long_scan.previous_bar.model_copy(update={"open": 103.0, "high": 104.0, "low": 102.5, "close": 103.5})
    confirm = long_scan.confirmation_bar.model_copy(update={"open": 103.5, "high": 104.2, "low": 103.1, "close": 103.8})

    result = _register(service, long_scan, bars=[previous, confirm])

    assert result["events_created"] == 0
    assert result["interactions_seen"] == 0
    assert service.repository.list_json("intraday_options_edge_events", limit=100) == []


def test_one_economic_zone_creates_one_parent_not_one_per_cluster_width(settings, long_scan):
    service = OptionsStructureTraderService(settings)
    _activate(service, long_scan)

    result = _register(service, long_scan)

    assert result["economic_zones"] == 1
    assert result["events_created"] == 1
    assert result["cluster_widths_audited"]
    assert len(service.repository.list_json("intraday_options_edge_events", limit=100)) == 1


def test_episode_dedup_suppresses_repeat_same_zone_interaction(settings, long_scan):
    service = OptionsStructureTraderService(settings)
    _activate(service, long_scan)

    first = _register(service, long_scan)
    second = _register(service, long_scan)

    assert first["events_created"] == 1
    assert second["events_created"] == 0
    assert second["dedup_suppressions"] >= 1
    assert len(service.repository.list_json("intraday_options_edge_events", limit=100)) == 1


def test_persistent_variants_require_trustworthy_persistence_fields(settings, long_scan):
    service = OptionsStructureTraderService(settings)
    _activate(service, long_scan)

    _register(service, long_scan, prior_levels=[])

    branches = service.repository.list_json("intraday_options_edge_branches", limit=500)
    persistent = [
        row for row in branches
        if row["strategy_variant"] in {"VARIANT_C_PERSISTENT_5M", "VARIANT_D_PERSISTENT_15M_5M"}
    ]
    assert persistent
    assert all(row["status"] == "not_qualified" for row in persistent)
    assert any("NOT_QUALIFIED_MISSING_PERSISTENCE" in row["entry_prerequisite_failures"] for row in persistent)


def test_phase4b2_prerequisites_gate_missing_structure_and_persistence(settings, long_scan):
    service = OptionsStructureTraderService(settings)
    _activate(service, long_scan)

    _register(service, long_scan, prior_levels=[])

    branches = service.repository.list_json("intraday_options_edge_branches", limit=500)
    s2 = [row for row in branches if row.get("stop_variant") == "S2_15M_STRUCTURAL_INVALIDATION"]
    s3 = [row for row in branches if row.get("stop_variant") == "S3_LAST_CONFIRMED_HL_LH_INVALIDATION"]
    p2 = [row for row in branches if row.get("phase4b2_branch") == "P2"]
    p4 = [row for row in branches if row.get("phase4b2_branch") == "P4"]

    assert s2 and all(row["status"] == "not_qualified" for row in s2)
    assert s3 and all(row["status"] == "not_qualified" for row in s3)
    assert p2 and all(row["status"] == "not_qualified" for row in p2)
    assert p4 and all(row["status"] == "not_qualified" for row in p4)


def test_p0_p1_options_value_pair_keeps_same_entry_stop_management_and_path(settings, long_scan):
    service = OptionsStructureTraderService(settings)
    _activate(service, long_scan)
    _register(service, long_scan)

    branches = service.repository.list_json("intraday_options_edge_branches", limit=500)
    p0 = next(row for row in branches if row.get("phase4b2_branch") == "P0")
    p1 = next(row for row in branches if row.get("phase4b2_branch") == "P1")

    assert p0["parent_event_id"] == p1["parent_event_id"]
    assert p0["phase4b2_pairing_key"] == p1["phase4b2_pairing_key"]
    assert p0["planned_entry"] == p1["planned_entry"]
    assert p0["stop_initial"] == p1["stop_initial"]
    assert p0["management_variant"] == p1["management_variant"]
    assert p0["direction"] == p1["direction"]
    assert p0["level_cluster"] == p1["level_cluster"]
    assert p0["control_level"]["role"] == "MATCHED_SAME_ENTRY_PRICE_STRUCTURE_ONLY"


def test_s2_s3_use_confirmed_structure_prices_not_atr_proxies(settings, long_scan):
    service = OptionsStructureTraderService(settings)
    research = service.multitimeframe_edge_research
    event = {
        "direction": "LONG",
        "level_price": 100.0,
        "structural_stop": 99.7,
        "cluster": {"cluster_low": 99.9, "cluster_high": 100.1},
        "context": {"short_term_ATR": 2.0},
        "phase4b1_diagnostics": {
            "structural_invalidation_15m": 98.37,
            "last_confirmed_hl_lh_invalidation": 98.91,
        },
    }

    assert research._stop_for_variant(event, "S2_15M_STRUCTURAL_INVALIDATION") == 98.37
    assert research._stop_for_variant(event, "S3_LAST_CONFIRMED_HL_LH_INVALIDATION") == 98.91


def test_persistence_uses_distinct_snapshot_horizons(settings, long_scan):
    service = OptionsStructureTraderService(settings)
    research = service.multitimeframe_edge_research
    observed = long_scan.confirmation_bar.bar_end_utc

    def level_at(minutes: int, strength: float):
        return long_scan.level.model_copy(update={
            "known_at_utc": observed - timedelta(minutes=minutes),
            "strength_score": strength,
        })

    current = level_at(0, 0.90)
    cluster = research._cluster_levels([current], 0.5, research.default_cluster_width)[0]
    result = research._persistence(
        "TEST", cluster,
        [level_at(5, 0.85), level_at(15, 0.75), level_at(30, 0.60)],
        0.5, observed,
    )

    assert result["snapshot_persistence_count"] == 4
    assert result["strength_change_5m"] == 0.05
    assert result["strength_change_15m"] == 0.15
    assert result["strength_change_30m"] == 0.3
    assert result["persistence_fields_complete"] is True
    assert result["persistence_model_version"] == "snapshot_timestamp_horizons_v2"


def test_15m_branch_waits_for_completed_confirmation_then_enters_next_bar(settings, long_scan):
    service = OptionsStructureTraderService(settings)
    boundary = long_scan.confirmation_bar.bar_end_utc
    previous = long_scan.previous_bar.model_copy(update={
        "bar_start_utc": boundary - timedelta(minutes=5),
        "bar_end_utc": boundary,
        "open": 99.8, "high": 100.0, "low": 99.4, "close": 99.7,
    })
    confirmation = long_scan.confirmation_bar.model_copy(update={
        "bar_start_utc": boundary,
        "bar_end_utc": boundary + timedelta(minutes=5),
        "open": 99.7, "high": 100.7, "low": 99.4, "close": 100.5,
    })
    scan = long_scan.model_copy(update={
        "previous_bar": previous,
        "confirmation_bar": confirmation,
        "ticker_state": long_scan.ticker_state.model_copy(update={
            "timestamp_utc": confirmation.bar_end_utc, "spot_price": 100.5,
        }),
    })
    _activate(service, scan)
    start = boundary - timedelta(minutes=15)
    history = [
        Bar(ticker="TEST", bar_start_utc=start, bar_end_utc=start + timedelta(minutes=5),
            open=100.2, high=100.3, low=99.7, close=99.8, volume=1000, atr=.5),
        Bar(ticker="TEST", bar_start_utc=start + timedelta(minutes=5),
            bar_end_utc=start + timedelta(minutes=10),
            open=99.8, high=100.0, low=99.5, close=99.8, volume=1000, atr=.5),
        previous,
        confirmation,
    ]
    for bar in history:
        service.repository.store_bar(bar)
    _register(service, scan, bars=history)

    branches = service.repository.list_json("intraday_options_edge_branches", limit=500)
    b_ids = [row["id"] for row in branches if row["strategy_variant"] == "VARIANT_B_15M_CONFIRM_5M_ENTRY"]
    assert b_ids
    assert all(next(row for row in branches if row["id"] == branch_id)["status"] == "registered" for branch_id in b_ids)

    future = [
        Bar(ticker="TEST", bar_start_utc=boundary + timedelta(minutes=5),
            bar_end_utc=boundary + timedelta(minutes=10),
            open=100.5, high=100.7, low=100.2, close=100.4, volume=1000, atr=.5),
        Bar(ticker="TEST", bar_start_utc=boundary + timedelta(minutes=10),
            bar_end_utc=boundary + timedelta(minutes=15),
            open=100.4, high=100.8, low=100.3, close=100.6, volume=1500, atr=.5),
    ]
    for bar in future:
        service.repository.store_bar(bar)
        service.multitimeframe_edge_research.update_for_bar("TEST", bar)

    confirmed = service.repository.list_json("intraday_options_edge_branches", limit=500)
    assert all(next(row for row in confirmed if row["id"] == branch_id)["status"] == "pending" for branch_id in b_ids)
    entry_bar = Bar(
        ticker="TEST",
        bar_start_utc=boundary + timedelta(minutes=15),
        bar_end_utc=boundary + timedelta(minutes=20),
        open=100.5, high=100.8, low=100.2, close=100.6, volume=1200, atr=.5,
    )
    service.repository.store_bar(entry_bar)
    service.multitimeframe_edge_research.update_for_bar("TEST", entry_bar)
    entered = service.repository.list_json("intraday_options_edge_branches", limit=500)
    assert all(next(row for row in entered if row["id"] == branch_id)["status"] in {"open", "partial", "closed"} for branch_id in b_ids)


def test_integrity_report_marks_prefix_research_rows_and_excludes_them(settings, long_scan):
    service = OptionsStructureTraderService(settings)
    _activate(service, long_scan)
    _register(service, long_scan)
    report_date = long_scan.confirmation_bar.bar_end_utc.date().isoformat()

    result = service.phase4b2_research_integrity_qa(report_date, mark_pre_fix=True)

    assert result["report"]["counts"]["qa_pre_fix_events_marked"] == 1
    assert result["report"]["counts"]["qa_pre_fix_branches_marked"] > 0
    assert service.multitimeframe_edge_research.status(report_date)["counts"]["parent_events"] == 0
