from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

import pytest
import yaml

from options_structure_trader.config import PROJECT_ROOT, Settings
from options_structure_trader.models import (Bar, EligibilityContext, FeatureSet, GuardStatus, Level, ScanInput, TickerState)


@pytest.fixture
def settings(tmp_path):
    data = yaml.safe_load((PROJECT_ROOT / "config" / "config.yaml").read_text(encoding="utf-8"))
    data = copy.deepcopy(data)
    data["database"]["path"] = str(tmp_path / "test.db")
    data["watchlist"]["status_path"] = str(tmp_path / "watchlist_status.json")
    data["scheduler"]["status_path"] = str(tmp_path / "daemon_status.json")
    data["scheduler"]["pid_path"] = str(tmp_path / "daemon.pid")
    data["scheduler"]["log_path"] = str(tmp_path / "daemon.log")
    return Settings(data, PROJECT_ROOT)


@pytest.fixture
def long_scan():
    now = datetime(2026, 8, 3, 15, 0, tzinfo=timezone.utc)
    level = Level(ticker="TEST", level_type="GAMMA_FLIP", price=100, zone_low=99.9, zone_high=100.1,
                  known_at_utc=now - timedelta(hours=1), source="test", strength_score=.9)
    previous = Bar(ticker="TEST", bar_start_utc=now - timedelta(minutes=10), bar_end_utc=now - timedelta(minutes=5),
                   open=100.3, high=100.5, low=99.0, close=99.7, volume=1000, atr=.5)
    confirm = Bar(ticker="TEST", bar_start_utc=now - timedelta(minutes=5), bar_end_utc=now,
                  open=99.7, high=100.7, low=99.4, close=100.5, volume=2200, atr=.5, relative_volume=2)
    state = TickerState(ticker="TEST", timestamp_utc=now, source="test", spot_price=100.5,
                        bid=100.49, ask=100.51, last=100.5, spread_bps=2, relative_volume=2)
    features = FeatureSet(dealer_positioning=.95, options_flow=.9, oi_confirmation=.9,
                          big_trades_dark_pool=.8, price_structure=1, volatility_liquidity=.9,
                          data_quality_event_guard=1, flow_direction="bullish", volume_expansion=True)
    guard = GuardStatus(ticker="TEST", evaluated_at_utc=now, blocked=False)
    return ScanInput(ticker_state=state, level=level, previous_bar=previous, confirmation_bar=confirm,
                     features=features, target_nodes=[105, 108, 112], guard=guard, source_mode="TEST_FEED",
                     eligibility=EligibilityContext(real_data=True, supported_ticker=True, session_valid=True,
                         session_name="regular", macro_guard_evaluated=True, required_fields_complete=True,
                         price_provider="test_price", structure_provider="test_structure",
                         price_provider_production_eligible=True, structure_provider_production_eligible=True,
                         price_provider_free_validation_eligible=True,
                         structure_provider_free_validation_eligible=True, core_fields_complete=True,
                         macro_calendar_production_eligible=True,
                         price_freshness_seconds=0, structure_freshness_seconds=0, confidence_score=1))
