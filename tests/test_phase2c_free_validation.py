from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from options_structure_trader.adapters import AlgoXAdapter, YFinanceMarketBarsAdapter
from options_structure_trader.broker import StandalonePaperBroker
from options_structure_trader.config import PROJECT_ROOT
from options_structure_trader.db import Repository
from options_structure_trader.engines import ConfluenceEngine, ReclaimSetupDetector, TradeConstructor
from options_structure_trader.models import Mode, ObservationRequest
from options_structure_trader.service import OptionsStructureTraderService


def free_scan(long_scan):
    scan = long_scan.model_copy(deep=True)
    eligibility = scan.eligibility
    eligibility.required_fields_complete = False
    eligibility.core_fields_complete = True
    eligibility.price_provider = "yfinance"
    eligibility.structure_provider = "algox"
    eligibility.price_provider_production_eligible = False
    eligibility.structure_provider_production_eligible = False
    eligibility.price_provider_free_validation_eligible = True
    eligibility.structure_provider_free_validation_eligible = True
    eligibility.macro_calendar_production_eligible = False
    eligibility.macro_unknown = True
    eligibility.unofficial_source = True
    eligibility.limited_data = True
    eligibility.production_grade = False
    eligibility.gamma_grid_missing = True
    eligibility.oi_unavailable = True
    eligibility.greeks_unavailable = True
    eligibility.confidence_penalty_applied = True
    eligibility.confidence_score = .55
    eligibility.missing_components = ["open_interest", "greeks", "options_flow", "dark_pool"]
    scan.features.options_flow = None
    scan.features.oi_confirmation = None
    scan.features.big_trades_dark_pool = None
    scan.guard.macro_unknown = True
    scan.source_mode = "REAL_ALGOX_YFINANCE"
    return scan


def detector(settings):
    return ReclaimSetupDetector(settings, ConfluenceEngine(settings), TradeConstructor(settings))


def test_synthetic_cannot_enter_free_validation(settings, long_scan):
    scan = free_scan(long_scan)
    scan.eligibility.real_data = False
    scan.eligibility.synthetic_present = True
    setup = detector(settings).detect(scan)
    assert setup and not setup.free_validation_paper_allowed
    assert "Synthetic data cannot enter Free Validation Paper" in setup.free_validation_blocking_reasons
    repo = Repository(settings.path("database.path"), PROJECT_ROOT / "migrations")
    with pytest.raises(ValueError, match="Free Validation"):
        StandalonePaperBroker(settings, repo).accept(setup, Mode.FREE_VALIDATION)


def test_stale_candles_cannot_enter_free_validation(settings, long_scan):
    scan = free_scan(long_scan)
    scan.features.data_staleness_flag = True
    scan.eligibility.price_freshness_seconds = 421
    setup = detector(settings).detect(scan)
    assert setup and not setup.free_validation_paper_allowed
    assert any("freshness" in reason or "stale" in reason.lower()
               for reason in setup.free_validation_blocking_reasons)


def test_yfinance_fresh_data_can_enter_free_but_not_production(settings, long_scan):
    scan = free_scan(long_scan)
    setup = detector(settings).detect(scan)
    assert setup and setup.free_validation_paper_allowed
    assert setup.recommended_mode == Mode.FREE_VALIDATION
    assert not setup.production_paper_allowed
    repo = Repository(settings.path("database.path"), PROJECT_ROOT / "migrations")
    trade = StandalonePaperBroker(settings, repo).accept(setup)
    assert trade.mode == Mode.FREE_VALIDATION

    now = datetime.now(timezone.utc)
    normalized = YFinanceMarketBarsAdapter().normalize({
        "ticker": "SPY", "last_price": 100, "last_volume": 1000, "average_volume": 1000,
        "bars": [{"t": (now-timedelta(minutes=10)).isoformat(), "o": 99, "h": 100,
                  "l": 98, "c": 99.5, "v": 900},
                 {"t": (now-timedelta(minutes=5)).isoformat(), "o": 99.5, "h": 101,
                  "l": 99, "c": 100, "v": 1000}],
    })
    assert normalized["core_fields_complete"] and normalized["unofficial_source"]
    assert not normalized["required_fields_complete"]


def test_algox_partial_supports_free_but_not_production(settings, long_scan):
    now = datetime.now(timezone.utc)
    gex = AlgoXAdapter().normalize({"ticker": "SPY", "updated": now.isoformat(), "spot": 100,
        "flip": 100, "callWall": 105, "putWall": 95, "expectedMove": 2,
        "strikes": [{"k": 95, "g": -1}, {"k": 105, "g": 1}]})
    assert gex.free_validation_complete
    assert not gex.required_fields_complete
    scan = free_scan(long_scan)
    setup = detector(settings).detect(scan)
    assert setup.free_validation_paper_allowed and not setup.production_paper_allowed


def test_missing_oi_and_greeks_are_null_and_reduce_confidence(settings, long_scan):
    scan = free_scan(long_scan)
    setup = detector(settings).detect(scan)
    assert scan.features.oi_confirmation is None
    assert setup.score.raw_components["oi_confirmation"] is None
    assert "oi_confirmation" in setup.score.missing_components
    assert setup.score.adjusted_score < setup.score.raw_score
    assert setup.score.confidence_score == .55
    assert setup.score.data_quality_tier == "FREE_LIMITED"


def test_macro_unknown_is_tagged_but_configurably_free_eligible(settings, long_scan):
    scan = free_scan(long_scan)
    setup = detector(settings).detect(scan)
    assert scan.guard.macro_unknown and scan.eligibility.macro_unknown
    assert setup.free_validation_paper_allowed
    assert not setup.production_paper_allowed


def test_live_trading_remains_impossible_and_portfolio_isolation_is_static(settings, long_scan):
    setup = detector(settings).detect(free_scan(long_scan))
    repo = Repository(settings.path("database.path"), PROJECT_ROOT / "migrations")
    with pytest.raises(ValueError, match="paper modes"):
        StandalonePaperBroker(settings, repo).accept(setup, Mode.LIVE_ASSISTED)
    imported = []
    for path in (PROJECT_ROOT / "src" / "options_structure_trader").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
    assert not any("portfolio" in name.lower() for name in imported)
    assert Path(repo.path).resolve().is_relative_to(Path(settings.path("database.path")).parent.resolve())


def test_rth_only_runner_skips_providers_when_closed(settings, monkeypatch):
    service = OptionsStructureTraderService(settings)
    monkeypatch.setattr(service.session_calendar, "evaluate", lambda now: {
        "is_open": False, "state": "closed", "authoritative": True,
        "next_rth_open_utc": "2026-09-03T13:30:00+00:00",
    })
    result = service.run_observation(ObservationRequest(
        tickers=["SPY"], rth_only=True, target_scans=50, cycles=1000, interval_seconds=0))
    assert result["status"] == "skipped_market_closed"
    assert result["scan_count"] == 0


def test_migrations_are_idempotent(settings):
    Repository(settings.path("database.path"), PROJECT_ROOT / "migrations")
    Repository(settings.path("database.path"), PROJECT_ROOT / "migrations")
