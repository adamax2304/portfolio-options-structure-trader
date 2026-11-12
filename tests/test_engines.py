from __future__ import annotations

from datetime import datetime, timedelta, timezone

from options_structure_trader.engines import (ConfluenceEngine, LevelEngine, MacroEventGuard,
                                              ReclaimSetupDetector, TradeConstructor)
from options_structure_trader.models import GexMap, MacroEvent, SetupType


def test_level_zone_formula(settings):
    assert LevelEngine.zone_width(100, 2, .05, .1) == .4
    assert LevelEngine.zone_width(1000, .1, .01, 0) == 1


def test_gex_conflict_detection(settings):
    now = datetime.now(timezone.utc)
    maps = [GexMap(ticker="X", source="a", source_timestamp_utc=now, spot=100, gamma_flip=99),
            GexMap(ticker="X", source="b", source_timestamp_utc=now, spot=100, gamma_flip=102)]
    conflict, reason = LevelEngine(settings).conflict(maps, atr_15m=1)
    assert conflict and "differ" in reason


def test_macro_event_guard_windows(settings):
    event_time = datetime(2026, 9, 1, 14, 0, tzinfo=timezone.utc)
    event = MacroEvent(event_id="cpi", event_name="CPI", event_type="CPI", event_time_utc=event_time,
                       importance="high")
    guard = MacroEventGuard(settings, [event])
    assert guard.evaluate("SPY", event_time - timedelta(minutes=59)).blocked
    assert guard.evaluate("SPY", event_time + timedelta(minutes=29)).blocked
    assert not guard.evaluate("SPY", event_time - timedelta(minutes=61)).blocked


def test_long_reclaim_produces_structural_plan(settings, long_scan):
    detector = ReclaimSetupDetector(settings, ConfluenceEngine(settings), TradeConstructor(settings))
    setup = detector.detect(long_scan)
    assert setup is not None
    assert setup.setup_type == SetupType.LEVEL_RECLAIM_LONG
    assert setup.trade_plan.stop_initial < min(long_scan.previous_bar.low, long_scan.level.zone_low)
    assert setup.trade_plan.primary_rr >= 1.8
    assert setup.production_paper_allowed


def test_short_reclaim_is_symmetric(settings, long_scan):
    scan = long_scan.model_copy(deep=True)
    scan.previous_bar.open, scan.previous_bar.high, scan.previous_bar.low, scan.previous_bar.close = 99.7, 101, 99.5, 100.4
    scan.confirmation_bar.open, scan.confirmation_bar.high, scan.confirmation_bar.low, scan.confirmation_bar.close = 100.4, 100.7, 99.3, 99.5
    scan.features.flow_direction = "bearish"
    scan.target_nodes = [95, 92, 88]
    setup = ReclaimSetupDetector(settings, ConfluenceEngine(settings), TradeConstructor(settings)).detect(scan)
    assert setup and setup.setup_type == SetupType.LEVEL_RECLAIM_SHORT
    assert setup.trade_plan.stop_initial > max(scan.previous_bar.high, scan.level.zone_high)
    assert setup.trade_plan.targets == sorted(setup.trade_plan.targets, reverse=True)


def test_closed_candle_and_no_lookahead_are_required(settings, long_scan):
    detector = ReclaimSetupDetector(settings, ConfluenceEngine(settings), TradeConstructor(settings))
    scan = long_scan.model_copy(deep=True)
    scan.confirmation_bar.closed = False
    assert detector.detect(scan) is None
    scan.confirmation_bar.closed = True
    scan.level.known_at_utc = scan.confirmation_bar.bar_start_utc
    assert detector.detect(scan) is None


def test_macro_blocks_production_but_keeps_shadow(settings, long_scan):
    long_scan.guard.blocked = True
    long_scan.guard.blocking_reasons = ["CPI event window (+20 minutes)"]
    setup = ReclaimSetupDetector(settings, ConfluenceEngine(settings), TradeConstructor(settings)).detect(long_scan)
    assert setup and not setup.production_paper_allowed and setup.shadow_paper_allowed


def test_unapproved_macro_calendar_blocks_production(settings, long_scan):
    long_scan.eligibility.macro_calendar_production_eligible = False
    setup = ReclaimSetupDetector(settings, ConfluenceEngine(settings), TradeConstructor(settings)).detect(long_scan)
    assert setup and not setup.production_paper_allowed
    assert "Macro calendar is not approved" in " ".join(setup.blocking_reasons)


def test_score_models_are_versioned(settings, long_scan):
    engine = ConfluenceEngine(settings)
    baseline = engine.score(long_scan.features)
    no_flow = engine.score(long_scan.features, "no_flow", engine.ablation_weight_sets()["no_flow"])
    assert baseline.score_model_version != no_flow.score_model_version
    assert round(sum(no_flow.breakdown.values()), 2) == no_flow.total
