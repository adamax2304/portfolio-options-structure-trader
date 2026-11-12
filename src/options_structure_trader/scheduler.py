from __future__ import annotations

import json
import logging
import os
import re
import signal
import time
from collections import deque
from datetime import date, datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from .models import Mode, new_id


EASTERN = ZoneInfo("America/New_York")


def sanitize_message(value: object) -> str:
    text = str(value)
    return re.sub(r"(?i)(api[_-]?key|secret|token|authorization|password)([=: ]+)[^&\s]+",
                  r"\1\2[REDACTED]", text)


class JsonStateStore:
    def __init__(self, path: Path):
        self.path = path

    def read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def write(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        temporary.replace(self.path)


class ScanResultCache:
    def __init__(self, ttl_seconds: int):
        self.ttl_seconds = ttl_seconds
        self.values: dict[str, tuple[datetime, dict[str, Any]]] = {}

    def get(self, symbol: str, at: datetime) -> dict[str, Any] | None:
        cached = self.values.get(symbol)
        if not cached or (at-cached[0]).total_seconds() >= self.ttl_seconds:
            return None
        return cached[1]

    def put(self, symbol: str, at: datetime, value: dict[str, Any]) -> None:
        self.values[symbol] = (at, value)


class ProviderRateLimiter:
    """Small rolling-window budget used before a scan calls its price and structure providers."""

    def __init__(self, requests_per_minute: dict[str, int], sleeper: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic):
        self.requests_per_minute = {name: max(1, int(value)) for name, value in requests_per_minute.items()}
        self.sleeper, self.clock = sleeper, clock
        self.history: dict[str, deque[float]] = {name: deque() for name in self.requests_per_minute}

    def acquire(self, providers: list[str]) -> float:
        waited = 0.0
        for provider in providers:
            limit = self.requests_per_minute.get(provider)
            if not limit:
                continue
            history = self.history.setdefault(provider, deque())
            now = self.clock()
            while history and now-history[0] >= 60:
                history.popleft()
            if len(history) >= limit:
                delay = max(0, 60-(now-history[0]))
                if delay:
                    self.sleeper(delay)
                    waited += delay
                    now = self.clock()
                    while history and now-history[0] >= 60:
                        history.popleft()
            history.append(self.clock())
        return waited


class SchedulerEngine:
    def __init__(self, service: Any, *, now_fn: Callable[[], datetime] | None = None,
                 sleeper: Callable[[float], None] = time.sleep):
        self.service = service
        self.settings = service.settings
        self.now_fn = now_fn or (lambda: datetime.now(timezone.utc))
        self.sleeper = sleeper
        self.state = JsonStateStore(self.settings.path("scheduler.status_path"))
        self.cache = ScanResultCache(int(self.settings.get("scan.provider_cache_ttl_seconds", 240)))
        self.rate_limiter = ProviderRateLimiter(
            self.settings.get("scan.provider_requests_per_minute", {}), sleeper=sleeper)
        self.stop_requested = False
        self.logger = self._logger()

    def _logger(self) -> logging.Logger:
        logger = logging.getLogger(f"options_structure_trader.daemon.{id(self)}")
        logger.setLevel(logging.INFO)
        logger.propagate = False
        if not logger.handlers:
            path = self.settings.path("scheduler.log_path")
            path.parent.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(path, maxBytes=5_000_000, backupCount=5, encoding="utf-8")
            formatter = logging.Formatter("%(asctime)sZ %(levelname)s %(message)s")
            formatter.converter = time.gmtime
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        return logger

    @staticmethod
    def _parse(value: str | None) -> datetime | None:
        return datetime.fromisoformat(value) if value else None

    def _today_window(self, at: datetime) -> tuple[str, str]:
        local_day = at.astimezone(EASTERN).date()
        start = datetime.combine(local_day, datetime.min.time(), EASTERN).astimezone(timezone.utc)
        return start.isoformat(), (start+timedelta(days=1)).isoformat()

    def _counts_today(self, at: datetime) -> dict[str, int]:
        start, end = self._today_window(at)
        return self.service.repository.observation_counts_between(start, end)

    def _last_scan(self) -> str | None:
        rows = self.service.repository.list_json("scan_observations", limit=1)
        return rows[0].get("observed_at_utc") if rows else None

    def _active_window(self, at: datetime, session: dict[str, Any]) -> tuple[bool, str, datetime | None]:
        if not session.get("is_open"):
            if session.get("is_session_day") and (not self.settings.get("scheduler.rth_only", True) or
                                                   self.settings.get("scheduler.free_validation_outside_rth", False)):
                local_time = at.astimezone(EASTERN).time()
                if local_time.hour >= 4 and local_time.hour < 20:
                    state = ("EXTENDED_HOURS_FREE" if self.settings.get(
                        "scheduler.free_validation_outside_rth", False) else "EXTENDED_HOURS_SHADOW")
                    return True, state, at
            state = "CLOSED_WEEKEND_OR_HOLIDAY" if not session.get("is_session_day") else "CLOSED"
            next_open = self._parse(session.get("next_rth_open_utc"))
            if next_open:
                next_open += timedelta(minutes=int(self.settings.get("scheduler.warmup_after_open_minutes", 10)))
            return False, state, next_open
        opened = self._parse(session.get("session_open_utc"))
        closed = self._parse(session.get("session_close_utc"))
        warm = opened + timedelta(minutes=int(self.settings.get("scheduler.warmup_after_open_minutes", 10))) if opened else at
        stop = closed - timedelta(minutes=int(self.settings.get("scheduler.stop_before_close_minutes", 5))) if closed else None
        if at < warm:
            return False, "RTH_WARMUP", warm
        if stop and at >= stop:
            next_open = self.service.session_calendar.next_open(at)
            if next_open:
                next_open += timedelta(minutes=int(self.settings.get("scheduler.warmup_after_open_minutes", 10)))
            return False, "RTH_CLOSE_BUFFER", next_open
        return True, "RTH_ACTIVE", at

    def _maybe_report(self, at: datetime, session: dict[str, Any], prior: dict[str, Any]) -> dict[str, Any] | None:
        if not self.settings.get("scheduler.generate_daily_report_after_close", True):
            return None
        last_close = self._parse(session.get("last_rth_close_utc"))
        if not last_close:
            return None
        delay = timedelta(minutes=int(self.settings.get("scheduler.report_after_close_minutes", 15)))
        report_date = last_close.astimezone(EASTERN).date().isoformat()
        if at < last_close+delay or prior.get("last_report_date") == report_date:
            return None
        generated = self.service.daily_reports.generate(report_date)
        freshness = self.service.provider_freshness_report(report_date)
        generated["provider_freshness_report_path"] = freshness["markdown_path"]
        if self.settings.get("storage.transient_retention_enabled", True):
            retention_days = max(1, int(self.settings.get("storage.transient_retention_days", 30)))
            cutoff = at - timedelta(days=retention_days)
            generated["transient_cache_retention"] = {
                "cutoff_utc": cutoff.isoformat(),
                "rows_removed": self.service.repository.prune_transient_before(cutoff.isoformat()),
            }
        if hasattr(self.service, "phase4a_multitimeframe_edge_report"):
            phase4a = self.service.phase4a_multitimeframe_edge_report(report_date)
            generated["phase4a_research_summary_path"] = phase4a["markdown_path"]
        self.logger.info("Generated daily report for %s", report_date)
        return generated

    def _selected_provider_names(self) -> list[str]:
        try:
            structure = self.service._structure_adapter().name
        except Exception:
            structure = "algox"
        return [structure, "yfinance"]

    def tick(self, at: datetime | None = None) -> dict[str, Any]:
        at = (at or self.now_fn()).astimezone(timezone.utc)
        prior = self.state.read()
        session = self.service.session_calendar.evaluate(at)
        report = self._maybe_report(at, session, prior)
        active, session_state, window_time = self._active_window(at, session)
        next_scan = self._parse(prior.get("next_scan_time"))
        base = {"daemon_status": "RUNNING", "heartbeat_at_utc": at.isoformat(),
                "current_session_state": session_state,
                "next_rth_open": session.get("next_rth_open_utc"),
                "next_rth_close": session.get("next_rth_close_utc"),
                "last_scan_time": self._last_scan(), "last_error": None,
                "provider_status": self.service.source_status(), "live_trading_disabled": True,
                "pid": os.getpid(), **self._counts_today(at)}
        if report:
            base.update({"last_report_date": report["report"]["report_date_utc"],
                         "daily_report_status": "generated", "daily_report_path": report["markdown_path"]})
        else:
            base.update({"last_report_date": prior.get("last_report_date"),
                         "daily_report_status": prior.get("daily_report_status", "pending"),
                         "daily_report_path": prior.get("daily_report_path")})
        if not active:
            base.update({"daemon_status": "SLEEPING", "next_scan_time": window_time.isoformat() if window_time else None,
                         "last_cycle_results": [], "sleep_seconds": int(self.settings.get(
                             "scheduler.heartbeat_interval_seconds", 60))})
            self.state.write(base)
            return base
        if next_scan and at < next_scan:
            base.update({"daemon_status": "WAITING_FOR_NEXT_CYCLE", "next_scan_time": next_scan.isoformat(),
                         "last_cycle_results": prior.get("last_cycle_results", []),
                         "sleep_seconds": min(int((next_scan-at).total_seconds()), int(self.settings.get(
                             "scheduler.heartbeat_interval_seconds", 60)))})
            self.state.write(base)
            return base

        entries = self.service.watchlist.due_symbols(
            at, max_symbols=int(self.settings.get("scan.max_symbols_per_cycle", 100)),
            cycle_minutes=int(self.settings.get("scheduler.scan_interval_minutes", 5)))
        run_id, results, provider_errors = new_id("daemon"), [], 0
        providers = self._selected_provider_names()
        for entry in entries:
            guard = self.service.guard.evaluate(entry.symbol, at)
            if guard.blocked:
                self.service.watchlist.update_symbol(entry.symbol, "MACRO_BLOCKED", at=at,
                                                     outcome="macro_blocked", error="; ".join(guard.blocking_reasons))
                results.append({"ticker": entry.symbol, "outcome": "macro_blocked", "symbol_status": "MACRO_BLOCKED"})
                continue
            if self.cache.get(entry.symbol, at):
                results.append({"ticker": entry.symbol, "outcome": "provider_cache_cooldown",
                                "symbol_status": "ACTIVE"})
                continue
            self.rate_limiter.acquire(providers)
            try:
                result = self.service.real_scan_ticker(entry.symbol, run_id, open_paper=True,
                                                       include_free_fallback=True)
                self.cache.put(entry.symbol, at, result)
                status = result.get("symbol_status", "ACTIVE")
                failed = result.get("outcome") == "provider_error"
                provider_errors += 1 if failed else 0
                error = sanitize_message("; ".join(result.get("reasons", []))) if failed else None
                self.service.watchlist.update_symbol(entry.symbol, status, at=at,
                                                     outcome=result.get("outcome"), error=error, failure=failed)
                results.append({"ticker": entry.symbol, "outcome": result.get("outcome"),
                                "symbol_status": status, "observation_id": result.get("observation_id")})
            except Exception as exc:
                provider_errors += 1
                error = sanitize_message(exc)
                self.service.watchlist.update_symbol(entry.symbol, "PROVIDER_UNAVAILABLE", at=at,
                                                     outcome="scheduler_error", error=error, failure=True)
                results.append({"ticker": entry.symbol, "outcome": "scheduler_error",
                                "symbol_status": "PROVIDER_UNAVAILABLE", "error": error})
                self.logger.error("Scan failed for %s: %s", entry.symbol, error)
            if provider_errors >= int(self.settings.get("scheduler.max_provider_errors_before_pause", 5)):
                break
        interval = timedelta(minutes=int(self.settings.get("scheduler.scan_interval_minutes", 5)))
        next_cycle = at + interval
        paused = provider_errors >= int(self.settings.get("scheduler.max_provider_errors_before_pause", 5))
        if paused:
            next_cycle = at + timedelta(seconds=int(self.settings.get("scheduler.retry_backoff_seconds", 60)))
        base.update({"daemon_status": "PAUSED_PROVIDER_ERRORS" if paused else "RUNNING",
                     "next_scan_time": next_cycle.isoformat(), "last_scan_time": at.isoformat() if results else base["last_scan_time"],
                     "last_cycle_results": results, "last_error": next((row.get("error") for row in reversed(results)
                                                                         if row.get("error")), None),
                     "sleep_seconds": min(int((next_cycle-at).total_seconds()), int(self.settings.get(
                         "scheduler.heartbeat_interval_seconds", 60)))})
        base.update(self._counts_today(at))
        self.state.write(base)
        return base

    def request_stop(self, *_: Any) -> None:
        self.stop_requested = True

    def run_forever(self, *, max_ticks: int | None = None) -> None:
        pid_path = self.settings.path("scheduler.pid_path")
        pid_path.parent.mkdir(parents=True, exist_ok=True)
        pid_path.write_text(str(os.getpid()), encoding="utf-8")
        signal.signal(signal.SIGINT, self.request_stop)
        signal.signal(signal.SIGTERM, self.request_stop)
        ticks = 0
        self.logger.info("Daemon started; live trading disabled")
        try:
            while not self.stop_requested and (max_ticks is None or ticks < max_ticks):
                try:
                    status = self.tick()
                    delay = max(1, int(status.get("sleep_seconds", 60)))
                except Exception as exc:
                    error = sanitize_message(exc)
                    self.logger.exception("Daemon tick failed: %s", error)
                    prior = self.state.read()
                    prior.update({"daemon_status": "ERROR", "heartbeat_at_utc": self.now_fn().isoformat(),
                                  "last_error": error, "live_trading_disabled": True})
                    self.state.write(prior)
                    delay = int(self.settings.get("scheduler.retry_backoff_seconds", 60))
                ticks += 1
                if not self.stop_requested and (max_ticks is None or ticks < max_ticks):
                    self.sleeper(delay)
        finally:
            final = self.state.read()
            final.update({"daemon_status": "STOPPED", "heartbeat_at_utc": self.now_fn().isoformat(),
                          "live_trading_disabled": True})
            self.state.write(final)
            if pid_path.exists() and pid_path.read_text(encoding="utf-8").strip() == str(os.getpid()):
                pid_path.unlink()
            self.logger.info("Daemon stopped")
