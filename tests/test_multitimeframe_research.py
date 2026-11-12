from __future__ import annotations

from datetime import timedelta

from options_structure_trader.models import GexMap
from options_structure_trader.service import OptionsStructureTraderService


def test_phase4a_research_records_parent_events_without_paper_trades(settings, long_scan):
    service = OptionsStructureTraderService(settings)
    activation_time = long_scan.confirmation_bar.bar_end_utc - timedelta(minutes=1)
    service.multitimeframe_edge_research.activate(force=True, activated_at=activation_time)
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

    result = service.multitimeframe_edge_research.register_scan(
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

    assert result["events_created"] >= 1
    assert result["branches_created"] >= 1
    events = service.repository.list_json("intraday_options_edge_events", limit=100)
    branches = service.repository.list_json("intraday_options_edge_branches", limit=500)
    assert events
    assert branches
    assert all(row["research_only"] for row in branches)
    assert service.repository.list_json("paper_trades", limit=100) == []


def test_phase4a_research_excludes_synthetic_inputs(settings, long_scan):
    service = OptionsStructureTraderService(settings)
    long_scan.source_mode = "DEMO_FIXTURE"
    eligibility = long_scan.eligibility.model_copy(update={"synthetic_present": True, "real_data": False})

    result = service.multitimeframe_edge_research.register_scan(
        run_id="test_run",
        observation_id="obs_test",
        ticker="TEST",
        source_mode=long_scan.source_mode,
        gex=None,
        current_levels=[long_scan.level],
        prior_levels=[],
        bars=[long_scan.previous_bar, long_scan.confirmation_bar],
        state=long_scan.ticker_state,
        guard=long_scan.guard,
        eligibility=eligibility,
        providers={},
        setup=None,
        outcome="fixture",
    )

    assert result["status"] == "skipped"
    assert service.repository.list_json("intraday_options_edge_events", limit=100) == []
    assert service.repository.list_json("intraday_options_edge_branches", limit=100) == []
