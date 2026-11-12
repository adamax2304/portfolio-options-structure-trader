from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from options_structure_trader.historical import (GEX_LEVEL_COLUMNS, HistoricalGEXEngine,
                                                 HistoricalGreeksEngine,
                                                 HistoricalReconstructionPipeline)
from options_structure_trader.service import OptionsStructureTraderService


def test_historical_greeks_recompute_requires_iv():
    engine = HistoricalGreeksEngine()
    row = {
        "snapshot_date": "2026-09-03",
        "snapshot_timestamp": "2026-09-03T16:00:00-04:00",
        "expiration": "2026-10-16",
        "strike": 100,
        "call_put": "CALL",
        "underlying_price": 101,
        "implied_volatility": 0.25,
    }

    computed = engine.recompute(row)
    unavailable = engine.recompute({**row, "implied_volatility": None})

    assert computed["greeks_source"] == "RECOMPUTED"
    assert computed["gamma"] > 0
    assert computed["delta"] > 0
    assert unavailable["greeks_source"] == "UNAVAILABLE"
    assert unavailable["gamma"] is None


def test_historical_gex_engine_derives_versioned_levels(settings):
    chain = pd.DataFrame([
        {"symbol": "TEST", "snapshot_date": "2026-09-03",
         "snapshot_timestamp": "2026-09-03T20:00:00+00:00",
         "publication_time": "2026-09-03T20:30:00+00:00", "strike": 95,
         "call_put": "PUT", "open_interest": 1000, "gamma": 0.02,
         "underlying_price": 100, "historical_data_tier": "TIER_H2_DAILY_CHAIN",
         "source_quality": "UNIT_TEST", "lookahead_risk": False},
        {"symbol": "TEST", "snapshot_date": "2026-09-03",
         "snapshot_timestamp": "2026-09-03T20:00:00+00:00",
         "publication_time": "2026-09-03T20:30:00+00:00", "strike": 105,
         "call_put": "CALL", "open_interest": 1000, "gamma": 0.02,
         "underlying_price": 100, "historical_data_tier": "TIER_H2_DAILY_CHAIN",
         "source_quality": "UNIT_TEST", "lookahead_risk": False},
    ])
    engine = HistoricalGEXEngine(settings)

    strike_gex = engine.reconstruct(chain)
    levels = engine.derive_levels(strike_gex)

    assert not strike_gex.empty
    assert "GEX_NODE" in set(levels["level_type"])
    assert set(levels["historical_data_tier"]) == {"TIER_H2_DAILY_CHAIN"}
    assert set(levels["lookahead_risk"]) == {False}


def _underlying_frame() -> pd.DataFrame:
    start = datetime(2026, 9, 3, 15, 0, tzinfo=timezone.utc)
    bars = []
    prices = [
        (100.4, 100.6, 99.2, 99.7),
        (99.7, 100.8, 99.4, 100.5),
        (100.5, 101.2, 100.3, 100.9),
        (100.9, 105.4, 100.8, 105.1),
    ]
    for index, (open_, high, low, close) in enumerate(prices):
        bar_start = start + timedelta(minutes=5 * index)
        bars.append({
            "symbol": "TEST", "timeframe": "5m",
            "bar_start_utc": bar_start.isoformat(),
            "bar_end_utc": (bar_start + timedelta(minutes=5)).isoformat(),
            "bar_start_et": bar_start.isoformat(),
            "open": open_, "high": high, "low": low, "close": close,
            "volume": 1000, "atr": 0.5, "relative_volume": 2.0,
            "provider": "unit_test", "dataset_source": "UNIT_TEST",
            "exchange_timezone": "America/New_York", "adjusted": False,
            "split_adjusted": "none", "source_timestamp_utc": (bar_start + timedelta(minutes=5)).isoformat(),
            "downloaded_at_utc": start.isoformat(), "raw_payload_reference": None,
        })
    return pd.DataFrame(bars)


def _level_frame() -> pd.DataFrame:
    known = datetime(2026, 9, 3, 14, 0, tzinfo=timezone.utc).isoformat()
    return pd.DataFrame([
        {"symbol": "TEST", "snapshot_date": "2026-09-03", "known_at_utc": known,
         "level_type": "GAMMA_FLIP", "price": 100, "zone_low": 99.9, "zone_high": 100.1,
         "strength_score": 0.9, "provider": "unit_test_historical_chain",
         "historical_data_tier": "TIER_H2_DAILY_CHAIN", "source_quality": "UNIT_TEST",
         "lookahead_risk": False, "gex_model_version": "unit_test",
         "dealer_assumption": "dealer_short_calls_long_puts", "raw_payload_reference": None,
         "metadata_json": "{}"},
        {"symbol": "TEST", "snapshot_date": "2026-09-03", "known_at_utc": known,
         "level_type": "GEX_NODE", "price": 105, "zone_low": 104.9, "zone_high": 105.1,
         "strength_score": 0.8, "provider": "unit_test_historical_chain",
         "historical_data_tier": "TIER_H2_DAILY_CHAIN", "source_quality": "UNIT_TEST",
         "lookahead_risk": False, "gex_model_version": "unit_test",
         "dealer_assumption": "dealer_short_calls_long_puts", "raw_payload_reference": None,
         "metadata_json": "{}"},
    ], columns=GEX_LEVEL_COLUMNS)


def test_historical_replay_uses_existing_detector_without_db_mutation(settings, tmp_path):
    service = OptionsStructureTraderService(settings)
    pipeline = HistoricalReconstructionPipeline(service.repository, settings, tmp_path)
    before_counts = service.repository.counts()

    replay = pipeline._replay(_underlying_frame(), _level_frame(), strategy_type="OPTIONS_STRUCTURE_RECON")
    after_counts = service.repository.counts()

    assert before_counts == after_counts
    assert not replay.empty
    assert set(replay["management_version"]) >= {"TM_V0_CURRENT", "TM_V3_TP1_PLUS_RUNNER"}
    assert set(replay["slippage_bps"]) == {0, 1, 3, 5}
    assert set(replay["historical_data_tier"]) == {"TIER_H2_DAILY_CHAIN"}


def test_phase3b_pipeline_writes_manifest_and_empty_chain_schema(settings, tmp_path, monkeypatch):
    service = OptionsStructureTraderService(settings)
    pipeline = HistoricalReconstructionPipeline(service.repository, settings, tmp_path)
    monkeypatch.setattr(pipeline, "_probe_sources", lambda: {
        "generated_at_utc": "2026-09-04T00:00:00+00:00",
        "yfinance": {"status": "MOCKED"},
        "alpha_vantage": {"status": "MOCKED"},
        "finnhub": {"status": "MOCKED"},
    })
    monkeypatch.setattr(pipeline, "_collect_historical_option_chains",
                        lambda symbols, probes: pd.DataFrame(columns=[]))
    monkeypatch.setattr(pipeline, "_collect_underlying",
                        lambda symbols, period, interval: _underlying_frame())
    monkeypatch.setattr(pipeline, "_local_archive_gex_levels",
                        lambda symbols: _level_frame())

    result = pipeline.run(symbols=["TEST"], period="20d", interval="5m")

    assert Path(result["markdown_path"]).exists()
    assert Path(result["manifest_path"]).exists()
    assert Path(result["source_matrix_path"]).exists()
    assert all(Path(path).exists() for path in result["parquet_paths"])
    assert all(Path(path).exists() for path in result["csv_paths"])
    assert result["report"]["historical_option_chain_rows"] == 0
    assert result["report"]["historical_replay_rows"] > 0
    management = pd.read_csv(tmp_path / "historical_management_comparison.csv")
    assert set(management["bucket"]) >= {
        "TM_V0_CURRENT",
        "TM_V3_TP1_PLUS_RUNNER",
        "FIXED_EXIT_0_5R",
        "FIXED_EXIT_1R",
        "HALF_0_5R_REST_RUNNER",
        "HALF_0_5R_HALF_1R",
    }
