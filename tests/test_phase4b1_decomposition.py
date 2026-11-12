from __future__ import annotations

from datetime import timedelta

from options_structure_trader.models import GexMap
from options_structure_trader.phase4b1 import classify_direction, classify_structure, giveback_bucket, loss_reason
from options_structure_trader.service import OptionsStructureTraderService


def test_call_wall_is_not_naively_forced_short():
    row = {
        "parent_event_id": "evt_call_wall_breakout",
        "direction": "LONG",
        "structural_family": "LEVEL_BREAKOUT",
        "level_type": "CALL_WALL",
        "level_tier": "LEVEL_TIER_S",
        "intraday_persistence_state": "STRENGTHENING",
        "trend_5m": "BULLISH",
        "trend_15m": "BULLISH",
        "trend_30m": "BULLISH",
        "trend_1h": "BULLISH",
        "market_alignment": "WITH_MARKET_TREND",
    }

    classified = classify_direction(row)

    assert classified["direction_class"] == "BREAKOUT_SUPPORT"
    assert classified["predicted_direction"] == "LONG"
    assert classified["naive_level_direction"] == "SHORT"
    assert classified["direction_confidence_0_100"] >= 70


def test_market_structure_alignment_is_deterministic():
    aligned = classify_structure({
        "direction": "SHORT",
        "trend_5m": "BEARISH",
        "trend_15m": "BEARISH",
        "trend_30m": "NEUTRAL",
        "trend_1h": "BEARISH",
    })
    conflicted = classify_structure({
        "direction": "SHORT",
        "trend_5m": "BULLISH",
        "trend_15m": "BULLISH",
        "trend_30m": "BULLISH",
        "trend_1h": "NEUTRAL",
    })

    assert aligned["structure_alignment"] == "FULL_ALIGNMENT"
    assert conflicted["structure_alignment"] == "COUNTERTREND"


def test_giveback_and_loss_reason_are_diagnostic_not_causal():
    row = {
        "result_R": -1.0,
        "MFE_R": 0.8,
        "MAE_R": 1.1,
        "exit_reason": "stop_loss",
        "diagnostic_data_quality": "FULL",
        "direction": "LONG",
        "predicted_direction": "LONG",
        "direction_class": "BULLISH_SUPPORT",
        "structure_alignment": "FULL_ALIGNMENT",
        "entry_quality_class": "ON_TIME_ENTRY",
    }

    assert giveback_bucket(row) == "REACHED_0_7R_THEN_LOSS"
    assert loss_reason(row) == ("BAD_STOP", "ASSOCIATED")


def test_phase4b1_forward_metadata_is_research_only(settings, long_scan):
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
    event = service.repository.list_json("intraday_options_edge_events", limit=1)[0]
    diagnostics = event["phase4b1_diagnostics"]
    assert diagnostics["research_only"] is True
    assert diagnostics["canonical_behavior_changed"] is False
    assert event["phase4b1_instrumentation_version"] == "phase4b1_forward_metadata_v2"
    assert service.repository.list_json("paper_trades", limit=100) == []
