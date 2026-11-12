from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from options_structure_trader.scheduler import ProviderRateLimiter, ScanResultCache, SchedulerEngine
from options_structure_trader.service import OptionsStructureTraderService
from options_structure_trader.watchlist import WatchlistManager


def test_daemon_sleeps_outside_rth(settings, monkeypatch):
    service = OptionsStructureTraderService(settings)
    calls = []
    monkeypatch.setattr(service, "real_scan_ticker", lambda *args, **kwargs: calls.append(args))
    status = SchedulerEngine(service, sleeper=lambda _: None).tick(
        datetime(2026, 9, 2, 11, 0, tzinfo=timezone.utc))
    assert status["daemon_status"] == "SLEEPING"
    assert status["current_session_state"] == "CLOSED"
    assert not calls


def test_daemon_starts_rotating_scan_during_rth(settings, monkeypatch):
    service = OptionsStructureTraderService(settings)
    calls = []

    def fake_scan(symbol, run_id, **kwargs):
        calls.append(symbol)
        return {"ticker": symbol, "outcome": "free_validation_valid_no_setup",
                "symbol_status": "ACTIVE", "observation_id": f"obs_{symbol}"}

    monkeypatch.setattr(service, "real_scan_ticker", fake_scan)
    status = SchedulerEngine(service, sleeper=lambda _: None).tick(
        datetime(2026, 9, 2, 14, 0, tzinfo=timezone.utc))
    assert status["daemon_status"] == "RUNNING"
    assert status["current_session_state"] == "RTH_ACTIVE"
    assert set(calls) >= {"SPY", "QQQ", "IWM"}
    assert status["next_scan_time"]


def test_daemon_respects_weekend_and_exchange_holiday(settings, monkeypatch):
    service = OptionsStructureTraderService(settings)
    monkeypatch.setattr(service, "real_scan_ticker", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("provider should not be called")))
    engine = SchedulerEngine(service, sleeper=lambda _: None)
    weekend = engine.tick(datetime(2026, 9, 5, 14, 0, tzinfo=timezone.utc))
    holiday = engine.tick(datetime(2026, 7, 3, 14, 0, tzinfo=timezone.utc))
    assert weekend["current_session_state"] == "CLOSED_WEEKEND_OR_HOLIDAY"
    assert holiday["current_session_state"] == "CLOSED_WEEKEND_OR_HOLIDAY"


def test_daemon_stops_before_exchange_early_close(settings, monkeypatch):
    service = OptionsStructureTraderService(settings)
    monkeypatch.setattr(service, "real_scan_ticker", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("provider should not be called in close buffer")))
    status = SchedulerEngine(service, sleeper=lambda _: None).tick(
        datetime(2026, 11, 27, 17, 56, tzinfo=timezone.utc))
    assert status["current_session_state"] == "RTH_CLOSE_BUFFER"
    assert status["next_rth_close"] == "2026-11-27T18:00:00+00:00"


def test_daily_report_is_generated_automatically_after_close(settings, monkeypatch, tmp_path):
    service = OptionsStructureTraderService(settings)
    generated = []

    def fake_report(report_date):
        generated.append(report_date)
        return {"report": {"report_date_utc": report_date},
                "markdown_path": str(tmp_path / "daily_report.md")}

    monkeypatch.setattr(service.daily_reports, "generate", fake_report)
    status = SchedulerEngine(service, sleeper=lambda _: None).tick(
        datetime(2026, 9, 2, 20, 16, tzinfo=timezone.utc))
    assert generated == ["2026-09-02"]
    assert status["daily_report_status"] == "generated"


def test_daily_report_writes_all_phase2d_artifacts(settings):
    service = OptionsStructureTraderService(settings)
    result = service.daily_reports.generate("2026-09-02")
    for key in ("markdown_path", "json_path", "trades_csv_path", "scans_csv_path",
                "ablation_summary_csv_path"):
        assert Path(result[key]).exists()


def test_expanded_watchlist_loads_at_least_fifty_symbols(settings):
    service = OptionsStructureTraderService(settings)
    assert 50 <= len(service.watchlist.entries) <= 100
    assert {"SPY", "AAPL", "RKLB", "XLK"} <= set(service.watchlist.entries)
    assert len(service.watchlist.symbols()) == len(set(service.watchlist.symbols()))


def test_disabled_and_no_options_symbols_are_skipped(tmp_path):
    config = tmp_path / "watchlist.yaml"
    config.write_text(yaml.safe_dump({"watchlist": {"tier_1_core": [
        {"symbol": "ON", "enabled": True}, {"symbol": "OFF", "enabled": False},
        {"symbol": "NOOPT", "enabled": True}]}}), encoding="utf-8")
    manager = WatchlistManager(config, tmp_path / "status.json", failed_cooldown_minutes=30)
    now = datetime(2026, 9, 2, 14, 0, tzinfo=timezone.utc)
    manager.update_symbol("NOOPT", "NO_OPTIONS_DATA", at=now, outcome="provider_error", failure=True)
    due = {entry.symbol for entry in manager.due_symbols(now, max_symbols=10)}
    assert "ON" in due and "OFF" not in due and "NOOPT" not in due


def test_provider_rate_limit_waits_for_rolling_window():
    current = [0.0]
    waits = []

    def sleep(seconds):
        waits.append(seconds)
        current[0] += seconds

    limiter = ProviderRateLimiter({"free": 2}, sleeper=sleep, clock=lambda: current[0])
    limiter.acquire(["free"])
    limiter.acquire(["free"])
    limiter.acquire(["free"])
    assert waits == [60.0]


def test_provider_result_cache_expires_without_duplicate_fetch():
    cache = ScanResultCache(240)
    now = datetime(2026, 9, 2, 14, 0, tzinfo=timezone.utc)
    cache.put("SPY", now, {"outcome": "cached"})
    assert cache.get("SPY", now+timedelta(seconds=239))["outcome"] == "cached"
    assert cache.get("SPY", now+timedelta(seconds=240)) is None


def test_failed_symbol_cooldown_and_daily_pause(settings):
    service = OptionsStructureTraderService(settings)
    manager = service.watchlist
    now = datetime(2026, 9, 2, 14, 0, tzinfo=timezone.utc)
    manager.update_symbol("SPY", "PROVIDER_UNAVAILABLE", at=now, failure=True, error="temporary")
    assert manager.is_cooling_down("SPY", now+timedelta(minutes=1))
    assert not manager.is_cooling_down("SPY", now+timedelta(minutes=31))


def test_windows_autostart_deliverables_use_background_and_restart_settings():
    root = Path(__file__).resolve().parents[1]
    install = (root / "scripts" / "install_windows_task.ps1").read_text(encoding="utf-8")
    start = (root / "scripts" / "start_daemon.ps1").read_text(encoding="utf-8")
    assert "New-ScheduledTaskTrigger -AtLogOn" in install
    assert "-RestartCount" in install and "-StartWhenAvailable" in install
    assert "options_structure_trader daemon" in install
    assert "-WindowStyle Hidden" in start
    assert (root / "scripts" / "uninstall_windows_task.ps1").exists()
    assert (root / "docs" / "AUTOSTART_WINDOWS.md").exists()


def test_scheduler_status_never_exposes_secrets(settings):
    service = OptionsStructureTraderService(settings)
    status = SchedulerEngine(service, sleeper=lambda _: None).tick(
        datetime(2026, 9, 2, 11, 0, tzinfo=timezone.utc))
    rendered = str(status).lower()
    assert "authorization:" not in rendered and "[redacted]" not in rendered
    assert "alpaca_api_secret" not in rendered and "alphavantage_api_key=" not in rendered
    assert status["live_trading_disabled"] is True
    gitignore = (Path(__file__).resolve().parents[1] / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gitignore
