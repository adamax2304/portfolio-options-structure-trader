from __future__ import annotations

from datetime import timedelta

from options_structure_trader.models import Bar, GexMap
from options_structure_trader.service import OptionsStructureTraderService


def _record_test_event(service: OptionsStructureTraderService, long_scan):
    activation_time = long_scan.confirmation_bar.bar_end_utc - timedelta(minutes=1)
    service.multitimeframe_edge_research.activate(force=True, activated_at=activation_time)
    service.multitimeframe_edge_research.activate_phase4b2(force=True, activated_at=activation_time)
    long_scan.source_mode = "REAL_TEST_PRICE"
    gex = GexMap(
        ticker="TEST",
        source="test_gex",
        source_timestamp_utc=long_scan.confirmation_bar.bar_end_utc,
        spot=long_scan.ticker_state.spot_price,
        gamma_flip=100,
        call_wall=105,
        put_wall=95,
        gamma_regime="POSITIVE_GAMMA",
        confidence_score=0.8,
        free_validation_complete=True,
    )
    return service.multitimeframe_edge_research.register_scan(
        run_id="test_run",
        observation_id="obs_test",
        ticker="TEST",
        source_mode=long_scan.source_mode,
        gex=gex,
        current_levels=[long_scan.level],
        prior_levels=[long_scan.level],
        bars=[long_scan.previous_bar, long_scan.confirmation_bar],
        state=long_scan.ticker_state,
        guard=long_scan.guard,
        eligibility=long_scan.eligibility,
        providers={"price": "test_price", "structure": "test_gex"},
        setup=None,
        outcome="free_validation_valid_no_setup",
    )


def test_phase4b2_creates_frozen_research_branches_without_paper_trades(settings, long_scan):
    service = OptionsStructureTraderService(settings)

    result = _record_test_event(service, long_scan)

    assert result["events_created"] >= 1
    assert result["branches_created"] >= 14
    branches = service.repository.list_json("intraday_options_edge_branches", limit=500)
    phase4b2 = [row for row in branches if row.get("phase4b2_experiment_id")]
    assert phase4b2
    assert {row["phase4b2_experiment_id"] for row in phase4b2} == {
        "EXPERIMENT_1_INVALIDATION_STOP",
        "EXPERIMENT_2_PROFIT_PROTECTION",
        "EXPERIMENT_3_OPTIONS_VALUE",
    }
    assert {
        row["stop_variant"] for row in phase4b2
        if row["phase4b2_experiment_id"] == "EXPERIMENT_1_INVALIDATION_STOP"
    } == {
        "S0_CANONICAL_STOP",
        "S1_FULL_OPTIONS_LEVEL_ZONE_INVALIDATION",
        "S2_15M_STRUCTURAL_INVALIDATION",
        "S3_LAST_CONFIRMED_HL_LH_INVALIDATION",
    }
    assert {
        row["management_variant"] for row in phase4b2
        if row["phase4b2_experiment_id"] == "EXPERIMENT_2_PROFIT_PROTECTION"
    } == {
        "M0_CURRENT_MANAGEMENT",
        "M1_HALF_0_5R_RUNNER",
        "M2_HALF_0_7R_RUNNER",
        "M3_PROTECT_AFTER_1R_NO_PARTIAL",
        "M4_STRUCTURE_TRAIL_NO_IMMEDIATE_BE",
    }
    assert {"P0", "P1", "P2", "P3", "P4"} <= {
        row["phase4b2_branch"] for row in phase4b2
        if row["phase4b2_experiment_id"] == "EXPERIMENT_3_OPTIONS_VALUE"
    }
    assert all(row["research_only"] for row in phase4b2)
    assert all(row["phase4b2_no_canonical_change"] for row in phase4b2)
    assert service.repository.list_json("paper_trades", limit=100) == []
    assert len(branches) == 22


def test_phase4b2_status_separates_it_from_phase4a_dashboard(settings, long_scan):
    service = OptionsStructureTraderService(settings)
    _record_test_event(service, long_scan)

    phase4a = service.phase4a_multitimeframe_edge_status()
    phase4b2 = service.phase4b2_prospective_status()

    assert phase4b2["phase"] == "4B2_PROSPECTIVE_EXECUTION_OPTIONS_VALUE_VALIDATION"
    assert phase4b2["research_only"] is True
    assert phase4b2["canonical_strategy_unchanged"] is True
    assert phase4b2["counts"]["branches"] >= 14
    assert all(
        not row["strategy_variant"].startswith("P4B2_")
        for row in phase4a["variant_summaries"]
    )


def test_phase4b2_report_writes_research_outputs(settings, long_scan):
    service = OptionsStructureTraderService(settings)
    _record_test_event(service, long_scan)

    result = service.phase4b2_prospective_report()

    assert result["report"]["research_only"] is True
    assert result["report"]["portfolio_os_isolated"] is True
    assert result["markdown_path"].endswith("PHASE_4B2_PROSPECTIVE_EXECUTION_OPTIONS_VALUE.md")


def test_unfilled_pending_branch_is_censored_without_fabricated_pnl(settings, long_scan):
    service = OptionsStructureTraderService(settings)
    _record_test_event(service, long_scan)
    branches = service.repository.list_json("intraday_options_edge_branches", limit=500)
    target = next(
        row for row in branches
        if row.get("phase4b2_experiment_id") == "EXPERIMENT_1_INVALIDATION_STOP"
        and row.get("stop_variant") == "S0_CANONICAL_STOP"
        and row.get("status") == "pending"
    )

    start = long_scan.confirmation_bar.bar_end_utc
    for index in range(3):
        bar = Bar(
            ticker="TEST",
            bar_start_utc=start + timedelta(minutes=5 * index),
            bar_end_utc=start + timedelta(minutes=5 * (index + 1)),
            open=110.0,
            high=111.0,
            low=109.0,
            close=110.0,
            volume=1000,
            atr=0.5,
        )
        service.multitimeframe_edge_research.update_for_bar("TEST", bar)

    updated = service.repository.list_json(
        "intraday_options_edge_branches", "WHERE id=?", (target["id"],), 1
    )[0]
    assert updated["status"] == "censored"
    assert updated["lifecycle_state"] == "CENSORED_NO_ENTRY"
    assert updated["actual_fill_price"] is None
    assert updated["result_R"] is None
    assert updated["realized_R"] is None
    assert updated["MFE"] is None
    assert updated["MAE"] is None
    assert updated["remaining_size"] == 0.0
    assert updated["accounting_integrity_status"] == "VALID_CENSORED_NO_FILL"
    assert [event["event_type"] for event in updated["events"]] == ["ORDER_EXPIRED_NO_FILL"]


def test_reconcile_quarantines_historical_no_fill_pnl_and_preserves_audit(settings, long_scan):
    service = OptionsStructureTraderService(settings)
    _record_test_event(service, long_scan)
    branch = next(
        row for row in service.repository.list_json("intraday_options_edge_branches", limit=500)
        if row.get("phase4b2_experiment_id") == "EXPERIMENT_1_INVALIDATION_STOP"
        and row.get("status") == "pending"
    )
    branch.update({
        "status": "censored",
        "lifecycle_state": "CENSORED",
        "exit_reason": "pending_order_expiry",
        "actual_fill_price": None,
        "result_R": 12.5,
        "realized_R": 12.5,
    })
    service.repository.store_intraday_edge_branch(branch)

    result = service.multitimeframe_edge_research.reconcile_no_fill_accounting()
    updated = service.repository.list_json(
        "intraday_options_edge_branches", "WHERE id=?", (branch["id"],), 1
    )[0]

    assert result["accounting_invalid_branches_marked"] == 1
    assert updated["status"] == "accounting_invalid_pre_fix"
    assert updated["accounting_integrity_status"] == "INVALID_NO_FILL_REPORTED_RESULT"
    assert updated["result_R"] is None
    assert updated["accounting_pre_fix_original"]["result_R"] == 12.5
    assert service.repository.list_json("paper_trades", limit=100) == []
