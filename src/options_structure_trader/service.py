from __future__ import annotations

from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from statistics import median
import time
from typing import Any

from pydantic import ValidationError

from .adapters import (AdapterError, AlgoXAdapter, AlpacaMarketBarsAdapter, AlphaVantageMarketBarsAdapter,
                       DemoFixtureAdapter, FinnhubContextAdapter, GammaGridAdapter, MacroYamlAdapter,
                       QuantDataAdapter, UnusualWhalesAdapter, YFinanceMarketBarsAdapter)
from .alerts import AlertDispatcher, format_production_alert
from .analytics import (DaemonWatchlistReporter, DailyObservationReporter,
                        ForwardManagementAB, FreeValidationAcceptanceReporter,
                        PerformanceReporter, ReplayRunner, TradeManagementResearch)
from .broker import StandalonePaperBroker, VariantRecorder
from .config import PROJECT_ROOT, Settings
from .db import Repository
from .edge import EdgeDiscoveryReporter, ForwardEdgeValidationReporter, ShortFailureDecompositionReporter
from .engines import ConfluenceEngine, LevelEngine, MacroEventGuard, ReclaimSetupDetector, TradeConstructor
from .market_data import CandleProviderRouter, summarize_provider_freshness
from .models import (EligibilityContext, FeatureSet, GuardStatus, Level, Mode, ObservationRequest,
                     PaperTrade, ReplayRequest, ScanInput, ScanRequest, SetupEvent, Side, new_id)
from .multitimeframe import MultiTimeframeOptionsEdgeResearch
from .session import SessionCalendar
from .scheduler import sanitize_message
from .watchlist import WatchlistManager


class OptionsStructureTraderService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings.load()
        self.repository = Repository(self.settings.path("database.path"), PROJECT_ROOT / "migrations")
        self.macro_adapter = MacroYamlAdapter(self.settings.path("sources.macro_calendar.yaml_path"))
        self.events = self.macro_adapter.normalize(self.macro_adapter.fetch({})) if self.macro_adapter.configured else []
        for event in self.events:
            self.repository.upsert_macro(event.event_id, event.event_time_utc.isoformat(), event.importance, event)
        self.adapters = {
            "demo_fixture": DemoFixtureAdapter(),
            "algox": AlgoXAdapter(self.settings.get("sources.algox.base_url", "https://algoxflow.com")),
            "alpaca": AlpacaMarketBarsAdapter(self.settings.get("sources.alpaca.feed", "iex")),
            "yfinance": YFinanceMarketBarsAdapter(self.settings.get("sources.yfinance.cache_seconds", 60)),
            "alpha_vantage": AlphaVantageMarketBarsAdapter(
                self.settings.get("sources.alpha_vantage.minimum_request_interval_seconds", 12)),
            "finnhub": FinnhubContextAdapter(),
            "gammagrid": GammaGridAdapter(self.settings.get("sources.gammagrid.sqlite_path", ""),
                                           self.settings.get("sources.gammagrid.database_url_env", "GAMMAGRID_DATABASE_URL")),
            "macro_calendar": self.macro_adapter,
            "unusual_whales": UnusualWhalesAdapter(),
            "quantdata": QuantDataAdapter(),
        }
        self.candle_router = CandleProviderRouter(self.settings, self.adapters)
        self.level_engine = LevelEngine(self.settings)
        self.guard = MacroEventGuard(self.settings, self.events, self.macro_adapter.approved)
        self.scorer = ConfluenceEngine(self.settings)
        self.constructor = TradeConstructor(self.settings)
        self.detector = ReclaimSetupDetector(self.settings, self.scorer, self.constructor)
        self.broker = StandalonePaperBroker(self.settings, self.repository)
        self.variants = VariantRecorder(self.settings, self.repository)
        self.performance = PerformanceReporter(self.repository)
        default_db = (PROJECT_ROOT / "data" / "options_structure_trader.db").resolve()
        artifact_root = PROJECT_ROOT if self.repository.path.resolve() == default_db else self.repository.path.parent
        self.artifact_root = artifact_root
        self.daily_reports = DailyObservationReporter(self.repository, artifact_root / "reports")
        phase2c_path = (PROJECT_ROOT / "PHASE_2C_FREE_VALIDATION_REPORT.md" if
                        self.repository.path.resolve() == default_db else
                        self.repository.path.parent / "PHASE_2C_FREE_VALIDATION_REPORT.md")
        self.phase2c_reports = FreeValidationAcceptanceReporter(self.repository, phase2c_path)
        self.phase2d_reports = DaemonWatchlistReporter(
            self.repository, artifact_root / "PHASE_2D_DAEMON_WATCHLIST_REPORT.md")
        self.replay = ReplayRunner(self.detector)
        self.alerts = AlertDispatcher(self.settings)
        self.session_calendar = SessionCalendar(self.settings.get("session.calendar", "XNYS"))
        self.watchlist = WatchlistManager(
            self.settings.path("watchlist.path"), self.settings.path("watchlist.status_path"),
            failed_cooldown_minutes=int(self.settings.get("scan.failed_symbol_cooldown_minutes", 30)),
            max_failures_per_day=int(self.settings.get("scan.max_failures_per_symbol_per_day", 5)))
        self.trade_management_research = TradeManagementResearch(
            self.repository, self.settings, self.watchlist, artifact_root)
        self.forward_management_ab = ForwardManagementAB(
            self.repository, self.settings, self.watchlist, artifact_root)
        self.edge_discovery = EdgeDiscoveryReporter(
            self.repository, self.settings, self.watchlist, artifact_root)
        self.forward_edge_validation = ForwardEdgeValidationReporter(
            self.repository, self.settings, self.watchlist, artifact_root)
        self.short_failure_decomposition = ShortFailureDecompositionReporter(
            self.repository, self.settings, self.watchlist, artifact_root)
        self.multitimeframe_edge_research = MultiTimeframeOptionsEdgeResearch(
            self.repository, self.settings, self.watchlist, artifact_root)

    def health(self) -> dict[str, Any]:
        return {"status": "ok", "service_name": "options_structure_trader",
                "signal_family": "OPTIONS_STRUCTURE", "runtime_mode": self.settings.get("system.runtime_mode"),
                "live_auto_enabled": False, "config_version": self.settings.version,
                "database": str(self.repository.path), "counts": self.repository.counts(),
                "paper_lanes": [Mode.SHADOW.value, Mode.FREE_VALIDATION.value, Mode.PRODUCTION.value],
                "session": self.session_calendar.evaluate(datetime.now(timezone.utc)),
                "server_time_utc": datetime.now(timezone.utc)}

    def source_status(self) -> list[dict[str, Any]]:
        result = []
        for name, adapter in self.adapters.items():
            status = adapter.status()
            if status.get("last_error"):
                status["last_error"] = sanitize_message(status["last_error"])
            status["enabled"] = self.settings.get(f"sources.{name}.enabled", True)
            status["production_eligible"] = bool(self.settings.get(f"sources.{name}.production_eligible", False))
            status["free_validation_eligible"] = bool(
                self.settings.get(f"sources.{name}.free_validation_eligible", False))
            status["unofficial_source"] = bool(self.settings.get(f"sources.{name}.unofficial_source", False))
            result.append(status)
        return result

    def provider_health_checks(self, symbol: str = "SPY") -> dict[str, Any]:
        symbol = symbol.upper()
        checks: dict[str, Any] = {}
        finnhub = self.adapters["finnhub"]
        if self.settings.get("sources.finnhub.enabled", False) and finnhub.configured:
            started = time.perf_counter()
            try:
                quote = finnhub.normalize(finnhub.fetch({"ticker": symbol, "endpoint": "quote"}))
                latency_ms = int((time.perf_counter()-started)*1000)
                quote_age = quote.get("quote_age_seconds")
                checks["FINNHUB"] = {"configured": True, "authenticated": True,
                                      "quote_available": bool(quote.get("quote_available")),
                                      "quote_age_seconds": quote_age,
                                      "price_fields": "VALID" if quote.get("current_price", 0) > 0 else "INVALID",
                                      "observed_latency_ms": latency_ms,
                                      "production_grade": False,
                                      "free_validation_eligible": bool(quote.get("quote_available"))}
            except Exception as exc:
                checks["FINNHUB"] = {"configured": True, "authenticated": False,
                                      "provider_status": "FINNHUB_AUTH_INVALID" if
                                      "401" in str(exc) or "403" in str(exc) else "ERROR",
                                      "production_grade": False, "free_validation_eligible": False,
                                      "error": sanitize_message(exc)}
        else:
            checks["FINNHUB"] = {"configured": False, "authenticated": False,
                                  "provider_status": "NOT_CONFIGURED",
                                  "production_grade": False, "free_validation_eligible": False}
        alpha = self.adapters["alpha_vantage"]
        if self.settings.get("sources.alpha_vantage.enabled", False) and alpha.configured:
            started = time.perf_counter()
            try:
                raw = alpha.fetch({"ticker": symbol, "timeframe": "5Min", "interval": "5m", "force_refresh": True})
                normalized = alpha.normalize(raw)
                latest = normalized["bars"][-1] if normalized.get("bars") else None
                latency_ms = int((time.perf_counter()-started)*1000)
                checks["ALPHA_VANTAGE"] = {"configured": True, "authenticated": True,
                                            "time_series_intraday_available": bool(latest),
                                            "available_intervals_checked": ["5min"],
                                            "latest_completed_candle_utc": latest.bar_end_utc.isoformat() if latest else None,
                                            "candle_age_seconds": latest.source_freshness_seconds if latest else None,
                                            "observed_latency_ms": latency_ms,
                                            "rate_limit_status": alpha.status().get("rate_limit_responses", 0),
                                            "production_grade": False,
                                            "free_validation_eligible": bool(latest)}
            except Exception as exc:
                error = sanitize_message(exc)
                status = ("RATE_LIMITED" if "rate" in error.lower() else
                          "ENTITLEMENT_UNAVAILABLE" if "premium endpoint" in error.lower() or
                          "entitlement" in error.lower() else
                          "ALPHA_VANTAGE_AUTH_INVALID" if "key" in error.lower() or
                          "apikey" in error.lower() else "ERROR")
                checks["ALPHA_VANTAGE"] = {"configured": True, "authenticated": status != "ALPHA_VANTAGE_AUTH_INVALID",
                                            "provider_status": status,
                                            "time_series_intraday_available": False,
                                            "production_grade": False,
                                            "free_validation_eligible": False,
                                            "error": error}
        else:
            checks["ALPHA_VANTAGE"] = {"configured": False, "authenticated": False,
                                        "provider_status": "NOT_CONFIGURED",
                                        "production_grade": False, "free_validation_eligible": False}
        self.repository.store_audit("provider_health_check", "completed", [],
                                    {name: {key: value for key, value in payload.items() if "key" not in key.lower()}
                                     for name, payload in checks.items()},
                                    symbol)
        return checks

    def fixture_scan_input(self, ticker: str, now: datetime | None = None) -> ScanInput:
        adapter: DemoFixtureAdapter = self.adapters["demo_fixture"]  # type: ignore[assignment]
        normalized = adapter.normalize(adapter.fetch({"ticker": ticker, "now": now or datetime.now(timezone.utc)}))
        gex, state = normalized["gex"], normalized["ticker_state"]
        raw_id = self.repository.store_raw(adapter.name, ticker, "fixture_snapshot", normalized, gex.source_timestamp_utc)
        gex.raw_payload_reference = raw_id
        self.repository.store_gex(gex, raw_id)
        spread = state.ask - state.bid
        levels = self.level_engine.from_gex(gex, normalized["confirmation_bar"].atr * 1.5, spread)
        for level in levels:
            self.repository.store_level(level)
        flip = next(level for level in levels if level.level_type == "GAMMA_FLIP")
        guard = self.guard.evaluate(ticker, normalized["confirmation_bar"].bar_end_utc)
        features = FeatureSet(dealer_positioning=.88, options_flow=.72, oi_confirmation=.75,
                              big_trades_dark_pool=.45, price_structure=.95, volatility_liquidity=.82,
                              data_quality_event_guard=0 if guard.blocked else .8,
                              flow_direction="bullish", retest_confirmed=False, volume_expansion=True,
                              raw={"fixture": True, "gamma_regime": gex.gamma_regime})
        targets = sorted({level.price for level in levels if level.price != flip.price})
        return ScanInput(ticker_state=state, level=flip, previous_bar=normalized["previous_bar"],
                         confirmation_bar=normalized["confirmation_bar"], features=features,
                         target_nodes=targets, guard=guard, source_mode="DEMO_FIXTURE",
                         eligibility=EligibilityContext(real_data=False, synthetic_present=True,
                             supported_ticker=bool(self.watchlist.entry(ticker)),
                             session_valid=True, session_name="fixture", macro_guard_evaluated=True,
                             required_fields_complete=True, price_provider="demo_fixture",
                             structure_provider="demo_fixture", price_provider_production_eligible=False,
                             structure_provider_production_eligible=False,
                             price_provider_free_validation_eligible=False,
                             structure_provider_free_validation_eligible=False, core_fields_complete=False,
                             limited_data=True, production_grade=False, missing_components=["synthetic_data"],
                             price_freshness_seconds=0,
                             structure_freshness_seconds=gex.freshness_seconds,
                             raw_payload_references=[raw_id], confidence_score=0))

    def _price_adapter(self, include_free_fallback: bool = True):
        for name in self.settings.get("scanner.price_source_preference", ["yfinance", "alpha_vantage", "alpaca"]):
            adapter = self.adapters.get(name)
            if not adapter or not self.settings.get(f"sources.{name}.enabled", False):
                continue
            if name == "yfinance" and not include_free_fallback:
                continue
            if adapter.configured:
                return adapter
        raise AdapterError("No configured market-bars provider is available")

    def _structure_adapter(self):
        for name in self.settings.get("sources.structure_source_preference", ["gammagrid", "algox"]):
            adapter = self.adapters.get(name)
            if adapter and self.settings.get(f"sources.{name}.enabled", False) and adapter.configured:
                return adapter
        raise AdapterError("No configured options-structure provider is available")

    def _eligibility(self, *, ticker: str, supported: bool, session: dict[str, Any], guard: GuardStatus,
                     price_adapter, normalized: dict[str, Any], state, confirmation_bar,
                     gex, price_raw_id: str, gex_raw_id: str) -> EligibilityContext:
        price_prod = bool(self.settings.get(f"sources.{price_adapter.name}.production_eligible", False))
        structure_prod = bool(self.settings.get(f"sources.{gex.source}.production_eligible", False))
        price_free = bool(self.settings.get(f"sources.{price_adapter.name}.free_validation_eligible", False))
        structure_free = bool(self.settings.get(f"sources.{gex.source}.free_validation_eligible", False))
        watch = self.watchlist.entry(ticker)
        if watch:
            price_prod = price_prod and watch.production_allowed
            structure_prod = structure_prod and watch.production_allowed
            price_free = price_free and watch.free_validation_allowed
            structure_free = structure_free and watch.free_validation_allowed
        unofficial = bool(normalized.get("unofficial_source") or
                          self.settings.get(f"sources.{price_adapter.name}.unofficial_source", False))
        oi_unavailable = not bool(gex.oi_nodes)
        greeks_unavailable = not bool(gex.greeks_summary)
        gamma_grid_missing = gex.source != "gammagrid"
        macro_unknown = not self.macro_adapter.approved
        missing = list(normalized.get("missing_fields", [])) + list(gex.missing_required_fields)
        missing.extend(name for name, unavailable in (("options_flow", True), ("dark_pool", True),
            ("oi_confirmation", oi_unavailable), ("greeks", greeks_unavailable),
            ("approved_macro_calendar", macro_unknown)) if unavailable)
        missing = list(dict.fromkeys(missing))
        base_confidence = (float(state.confidence_score) + float(gex.confidence_score)) / 2
        penalty = (.05 if unofficial else 0) + (.06 if oi_unavailable else 0) + (.04 if greeks_unavailable else 0)
        penalty += (.03 if gamma_grid_missing else 0) + (.05 if macro_unknown else 0)
        confidence = round(max(0, min(1, base_confidence-penalty)), 4)
        core_complete = bool(normalized.get("core_fields_complete") and gex.free_validation_complete
                             and confirmation_bar.closed and state.spot_price > 0 and price_raw_id and gex_raw_id)
        full_complete = bool(normalized.get("required_fields_complete") and gex.required_fields_complete
                             and core_complete)
        production_grade = bool(full_complete and price_prod and structure_prod and not unofficial
                                and self.macro_adapter.approved and confidence >= self.settings.get(
                                    "scores.production_min_confidence", .8))
        return EligibilityContext(
            real_data=True, synthetic_present=False, supported_ticker=supported,
            session_valid=bool(session["is_open"] and session["authoritative"]),
            free_validation_session_valid=bool(
                session["authoritative"] and (session["is_open"] or (
                    self.settings.get("scheduler.free_validation_outside_rth", False) and
                    session.get("is_session_day", False)))),
            session_name=str(session["state"]), macro_guard_evaluated=True,
            macro_calendar_production_eligible=self.macro_adapter.approved,
            required_fields_complete=full_complete, core_fields_complete=core_complete,
            price_provider=price_adapter.name, structure_provider=gex.source,
            price_provider_production_eligible=price_prod,
            structure_provider_production_eligible=structure_prod,
            price_provider_free_validation_eligible=price_free,
            structure_provider_free_validation_eligible=structure_free,
            price_freshness_seconds=max(state.source_freshness_seconds,
                                        confirmation_bar.source_freshness_seconds),
            structure_freshness_seconds=gex.freshness_seconds,
            limited_data=bool(missing), unofficial_source=unofficial, production_grade=production_grade,
            gamma_grid_missing=gamma_grid_missing, oi_unavailable=oi_unavailable,
            greeks_unavailable=greeks_unavailable, confidence_penalty_applied=bool(penalty),
            macro_unknown=macro_unknown, missing_components=missing,
            raw_payload_references=[price_raw_id, gex_raw_id], confidence_score=confidence,
            reasons=missing,
        )

    @staticmethod
    def _data_quality(value: EligibilityContext) -> dict[str, Any]:
        return {"limited_data": value.limited_data, "unofficial_source": value.unofficial_source,
                "production_grade": value.production_grade, "gamma_grid_missing": value.gamma_grid_missing,
                "oi_unavailable": value.oi_unavailable, "greeks_unavailable": value.greeks_unavailable,
                "confidence_penalty_applied": value.confidence_penalty_applied,
                "macro_unknown": value.macro_unknown, "confidence_score": value.confidence_score,
                "missing_components": value.missing_components,
                "data_quality_tier": "PRODUCTION_FULL" if value.production_grade else "FREE_LIMITED"}

    def _real_features(self, level: Level, previous_bar, confirmation_bar, state, gex, guard,
                       complete: bool) -> FeatureSet:
        long_pattern = min(previous_bar.low, confirmation_bar.low) < level.zone_low and confirmation_bar.close > level.zone_high
        short_pattern = max(previous_bar.high, confirmation_bar.high) > level.zone_high and confirmation_bar.close < level.zone_low
        price_structure = 1.0 if long_pattern or short_pattern else .25
        if long_pattern:
            direction = "bullish"
        elif short_pattern:
            direction = "bearish"
        else:
            direction = "unknown"
        spread_ok = state.spread_bps > 0 and state.spread_bps <= 25
        liquidity = min(1.0, .35 + min(confirmation_bar.relative_volume, 2) * .2 + (.25 if spread_ok else 0))
        fresh = (confirmation_bar.source_freshness_seconds <= self.settings.get(
                    "freshness.free_validation_price_max_seconds", 420)
                 and gex.freshness_seconds <= self.settings.get("freshness.free_validation_gex_max_seconds", 1200))
        return FeatureSet(
            dealer_positioning=min(1, .45 + level.strength_score * .45),
            options_flow=None,
            oi_confirmation=.75 if gex.oi_nodes else None,
            big_trades_dark_pool=None,
            price_structure=price_structure,
            volatility_liquidity=liquidity,
            data_quality_event_guard=(.95 if fresh and complete and not guard.blocked else
                                      None if guard.macro_unknown else .25),
            flow_direction=direction, volume_expansion=confirmation_bar.relative_volume >= 1.25,
            data_staleness_flag=not fresh, source_conflict_flag=gex.source_conflict_flag,
            raw={"real_data": True, "gamma_regime": gex.gamma_regime,
                 "flow_available": False, "oi_available": bool(gex.oi_nodes),
                 "dark_pool_available": False, "required_fields_complete": complete},
        )

    def _record_real_ablation(self, run_id: str, observation_id: str, scan: ScanInput) -> None:
        for name, weights in self.scorer.ablation_weight_sets().items():
            score = self.scorer.score(scan.features, name, weights,
                                      confidence_score=scan.eligibility.confidence_score if scan.eligibility else 0,
                                      data_quality_tier="FREE_LIMITED" if scan.eligibility and scan.eligibility.limited_data else "FULL")
            self.repository.store_ablation(run_id, observation_id, scan.ticker_state.ticker, name,
                                           score.model_dump(mode="json"), score.total, "score_model", name)
        for value in self.settings.get("stops.variants", []):
            side = "LONG" if scan.confirmation_bar.close >= scan.level.price else "SHORT"
            from .models import Side
            plan, blockers = self.constructor.construct(scan, Side(side), float(value))
            self.repository.store_ablation(run_id, observation_id, scan.ticker_state.ticker,
                                           "stop_buffer", {"plan": plan.model_dump(mode="json") if plan else None,
                                                           "blockers": blockers}, None, "stop_buffer", str(value))
        for value in self.settings.get("targets.logic_variants", []):
            self.repository.store_ablation(run_id, observation_id, scan.ticker_state.ticker,
                                           "tp_logic", {"value": value, "not_optimized": True},
                                           None, "tp_logic", str(value))
        for value in self.settings.get("targets.breakeven_variants", []):
            self.repository.store_ablation(run_id, observation_id, scan.ticker_state.ticker,
                                           "breakeven", {"value": value, "not_optimized": True},
                                           None, "breakeven", str(value))

    def _monitor_ticker_trades(self, ticker: str, bar) -> dict[str, Any]:
        """Advance paper/research state and return a compact monitoring receipt.

        Full canonical and research records are already persisted in their own
        tables.  Re-embedding every updated research branch in every scan
        observation made the database grow by multiple gigabytes and provided no
        independent evidence.
        """
        canonical_updates: list[dict[str, Any]] = []
        rows = self.repository.list_json("paper_trades",
                                         "WHERE ticker=? AND status IN ('pending','open','partial')", (ticker,), 100)
        for payload in rows:
            trade = PaperTrade.model_validate(payload)
            if trade.created_at_utc >= bar.bar_end_utc:
                continue
            canonical_updates.append(self.broker.on_bar(trade, bar).model_dump(mode="json"))
        management_updates = self.forward_management_ab.update_for_bar(ticker, bar)
        research_updates = self.multitimeframe_edge_research.update_for_bar(ticker, bar)
        return {
            "ticker": ticker,
            "bar_end_utc": bar.bar_end_utc.isoformat(),
            "canonical_updates": len(canonical_updates),
            "management_ab_updates": len(management_updates),
            "phase4_research_updates": len(research_updates),
            "canonical_trade_ids": [row.get("trade_id") for row in canonical_updates if row.get("trade_id")],
            "research_branch_ids_sample": [
                row.get("id") for row in research_updates[:10] if row.get("id")
            ],
            "payload_version": "compact_monitoring_receipt_v1",
        }

    def _record_phase4a_research(self, *, run_id: str, observation_id: str, ticker: str, source_mode: str,
                                 gex: Any, current_levels: list[Any], prior_levels: list[Any],
                                 bars: list[Any], state: Any, guard: Any, eligibility: Any,
                                 providers: dict[str, Any], setup: Any | None,
                                 outcome: str) -> dict[str, Any]:
        try:
            return self.multitimeframe_edge_research.register_scan(
                run_id=run_id, observation_id=observation_id, ticker=ticker,
                source_mode=source_mode, gex=gex, current_levels=current_levels,
                prior_levels=prior_levels, bars=bars, state=state, guard=guard,
                eligibility=eligibility, providers=providers, setup=setup, outcome=outcome)
        except Exception as exc:
            self.repository.store_audit(
                "phase4a_multitimeframe_research", "recording_error", [sanitize_message(exc)],
                {"observation_id": observation_id, "outcome": outcome,
                 "note": "Phase 4A research recording is isolated and non-fatal."},
                ticker, "WARNING")
            return {"status": "error", "error": sanitize_message(exc)}

    def real_scan_ticker(self, ticker: str, run_id: str, *, open_paper: bool = True,
                         include_free_fallback: bool = True) -> dict[str, Any]:
        ticker = ticker.upper().strip()
        now = datetime.now(timezone.utc)
        watch = self.watchlist.entry(ticker)
        supported = bool(watch and watch.enabled)
        if not supported:
            reasons = ["Ticker is disabled or absent from the expanded watchlist"]
            observation_id = self.repository.store_observation(run_id, ticker, "REAL", "rejected", False,
                                                               reasons, {}, {"supported": False})
            return {"ticker": ticker, "observation_id": observation_id, "outcome": "rejected",
                    "symbol_status": "DISABLED", "reasons": reasons}
        try:
            structure_adapter = self._structure_adapter()
            raw_gex = structure_adapter.fetch({"ticker": ticker})
            gex = structure_adapter.normalize(raw_gex)
            gex_raw_id = self.repository.store_raw(structure_adapter.name, ticker, "gex_map", raw_gex,
                                                   gex.source_timestamp_utc)
            gex.raw_payload_reference = gex_raw_id
            gex.staleness_flag = gex.freshness_seconds > self.settings.get("freshness.gex_max_seconds", 1200)
            self.repository.store_gex(gex, gex_raw_id)
        except Exception as exc:
            provider = getattr(locals().get("structure_adapter"), "name", "options_structure")
            failure_id = self.repository.store_provider_failure(provider, exc, run_id=run_id, ticker=ticker)
            observation_id = self.repository.store_observation(run_id, ticker, "REAL", "provider_error", False,
                [str(exc)], {"structure": provider, "failure_id": failure_id}, {})
            status = "NO_OPTIONS_DATA" if any(token in str(exc).lower() for token in
                ("no snapshot", "no option", "no data", "empty")) else "PROVIDER_UNAVAILABLE"
            return {"ticker": ticker, "observation_id": observation_id, "outcome": "provider_error",
                    "symbol_status": status, "reasons": [str(exc)]}
        session = self.session_calendar.evaluate(now)
        try:
            route = self.candle_router.route(
                ticker, interval="5m", tier=watch.tier, current_time=now,
                required_freshness=int(self.settings.get("freshness.free_validation_price_max_seconds", 420)),
                paper_mode="free-validation", session=session)
        except Exception as exc:
            failure_id = self.repository.store_provider_failure("candle_router", exc, run_id=run_id, ticker=ticker)
            observation_id = self.repository.store_observation(run_id, ticker, "REAL", "provider_error", False,
                [sanitize_message(exc)], {"structure": gex.source, "price": "candle_router",
                                          "failure_id": failure_id}, {})
            return {"ticker": ticker, "observation_id": observation_id, "outcome": "provider_error",
                    "symbol_status": "PROVIDER_UNAVAILABLE", "reasons": [sanitize_message(exc)]}
        if not route.free_validation_eligible or not route.normalized or not route.raw_payload:
            reasons = [route.rejection_reason or "MARKET_DATA_STALE"]
            if route.rejection_reason == "CANDLE_PROVIDER_DELAY":
                reasons.append("Finnhub quote is fresh, but no fresh completed OHLCV candle is available")
            else:
                reasons.append("No fresh completed OHLCV candle is available")
            data_quality = {"production_grade": False, "limited_data": True,
                            "unofficial_source": True, "data_quality_tier": "SHADOW_ONLY",
                            "watchlist_tier": watch.tier, **route.data_quality}
            providers = {"structure": gex.source, "price": route.selected_adapter_name,
                         "structure_raw_payload_id": gex_raw_id,
                         "structure_freshness_seconds": gex.freshness_seconds,
                         "candle_router": route.provider_payload(), "session_calendar": session}
            observation_id = self.repository.store_observation(
                run_id, ticker, "REAL_FREE_CORE", "shadow_candle_stale", False,
                reasons, providers, {"gex": gex.model_dump(mode="json")},
                free_validation_eligible=False, lane=Mode.SHADOW.value, data_quality=data_quality)
            self.repository.store_audit("real_scan", "shadow_candle_stale", reasons,
                                        {"observation_id": observation_id, "candle_router": route.provider_payload()},
                                        ticker)
            return {"ticker": ticker, "observation_id": observation_id, "outcome": "shadow_candle_stale",
                    "symbol_status": "STALE_CANDLES", "reasons": reasons, "providers": providers,
                    "setup": None, "trade": None}
        price_adapter = self.adapters[route.selected_adapter_name]
        raw_price = route.raw_payload
        normalized = route.normalized
        price_raw_id = self.repository.store_raw(price_adapter.name, ticker, "market_bars", raw_price)
        bars, state = normalized["bars"], normalized["ticker_state"]
        if len(bars) < 2:
            reasons = ["At least two completed 5m bars are required"]
            observation_id = self.repository.store_observation(run_id, ticker, "REAL_FREE_CORE", "shadow_candle_stale",
                False, reasons, {"structure": gex.source, "price": price_adapter.name,
                                 "candle_router": route.provider_payload()}, {},
                free_validation_eligible=False, lane=Mode.SHADOW.value)
            return {"ticker": ticker, "observation_id": observation_id, "outcome": "shadow_candle_stale",
                    "symbol_status": "STALE_CANDLES", "reasons": reasons}
        previous_bar, confirmation_bar = bars[-2], bars[-1]
        for bar in bars[-100:]:
            bar.raw_payload_reference = price_raw_id
            self.repository.store_bar(bar, price_raw_id)
        state.raw_payload_reference = price_raw_id
        state.trading_session = str(session["state"])
        self.repository.store_ticker_state(state, price_raw_id)
        guard = self.guard.evaluate(ticker, now)
        eligibility = self._eligibility(
            ticker=ticker, supported=supported, session=session, guard=guard,
            price_adapter=price_adapter, normalized=normalized, state=state,
            confirmation_bar=confirmation_bar, gex=gex, price_raw_id=price_raw_id,
            gex_raw_id=gex_raw_id,
        )
        data_quality = {**self._data_quality(eligibility), **route.data_quality,
                        "watchlist_tier": watch.tier}
        liquidity_reasons = []
        if state.spot_price < float(watch.min_price):
            liquidity_reasons.append(f"Price {state.spot_price:.2f} is below watchlist minimum {watch.min_price:.2f}")
        if state.average_daily_volume > 0 and state.average_daily_volume < float(watch.min_avg_volume):
            liquidity_reasons.append(
                f"Average volume {state.average_daily_volume:.0f} is below watchlist minimum {watch.min_avg_volume:.0f}")
        if liquidity_reasons:
            observation_id = self.repository.store_observation(
                run_id, ticker, "REAL_FILTER", "low_liquidity", False, liquidity_reasons,
                {"structure": gex.source, "price": price_adapter.name},
                {"ticker_state": state.model_dump(mode="json"), "gex": gex.model_dump(mode="json")},
                free_validation_eligible=False, lane=Mode.SHADOW.value,
                candle_end_utc=confirmation_bar.bar_end_utc, data_quality=data_quality)
            return {"ticker": ticker, "observation_id": observation_id, "outcome": "low_liquidity",
                    "symbol_status": "LOW_LIQUIDITY", "reasons": liquidity_reasons,
                    "setup": None, "trade": None}
        spread = max(0, state.ask - state.bid)
        prior_payloads = self.repository.levels_before(ticker, confirmation_bar.bar_start_utc)
        current_levels = self.level_engine.from_gex(gex, confirmation_bar.atr * 1.5, spread)
        for level in current_levels:
            level.metadata.update({"raw_payload_reference": gex_raw_id, "provider": gex.source,
                                   "provider_confidence": gex.confidence_score})
            self.repository.store_level(level)
        providers = {"structure": gex.source, "price": price_adapter.name,
                     "structure_raw_payload_id": gex_raw_id, "price_raw_payload_id": price_raw_id,
                     "structure_freshness_seconds": gex.freshness_seconds,
                     "price_freshness_seconds": eligibility.price_freshness_seconds,
                     "unofficial_source": eligibility.unofficial_source,
                     "candle_router": route.provider_payload(),
                     "session_calendar": session}
        monitoring_summary = self._monitor_ticker_trades(ticker, confirmation_bar)
        if not prior_payloads:
            reasons = ["No option level was known before the latest completed 5m bar; warming up"]
            reasons.extend(self.detector.classifier.free_blockers(
                ScanInput(ticker_state=state, level=current_levels[0], previous_bar=previous_bar,
                          confirmation_bar=confirmation_bar,
                          features=self._real_features(current_levels[0], previous_bar, confirmation_bar,
                                                       state, gex, guard, eligibility.core_fields_complete),
                          target_nodes=[], guard=guard, eligibility=eligibility,
                          source_mode=f"REAL_{gex.source.upper()}_{price_adapter.name.upper()}")))
            reasons.extend(eligibility.missing_components)
            reasons = list(dict.fromkeys(reasons))
            observation_id = self.repository.store_observation(run_id, ticker, "REAL_FREE_CORE", "warming_up", False,
                reasons, providers, {"gex": gex.model_dump(mode="json"),
                                     "confirmation_bar": confirmation_bar.model_dump(mode="json"),
                                     "new_levels": [level.model_dump(mode="json") for level in current_levels],
                                     "monitoring_summary": monitoring_summary}, free_validation_eligible=False,
                lane=Mode.SHADOW.value, candle_end_utc=confirmation_bar.bar_end_utc,
                data_quality=data_quality)
            phase4a = self._record_phase4a_research(
                run_id=run_id, observation_id=observation_id, ticker=ticker,
                source_mode=f"REAL_{gex.source.upper()}_{price_adapter.name.upper()}",
                gex=gex, current_levels=current_levels, prior_levels=[],
                bars=bars[-100:], state=state, guard=guard, eligibility=eligibility,
                providers=providers, setup=None, outcome="warming_up")
            return {"ticker": ticker, "observation_id": observation_id, "outcome": "warming_up",
                    "symbol_status": "ACTIVE", "reasons": reasons, "providers": providers,
                    "setup": None, "trade": None, "phase4a_research": phase4a}

        prior_levels = [Level.model_validate(payload) for payload in prior_payloads]
        prior_levels = sorted(prior_levels, key=lambda level: abs(level.price - confirmation_bar.close))
        target_nodes = sorted({level.price for level in prior_levels})
        detected_scan = None
        detected_setup = None
        closest_scan = None
        for level in prior_levels:
            features = self._real_features(level, previous_bar, confirmation_bar, state, gex, guard,
                                           eligibility.core_fields_complete)
            scan = ScanInput(ticker_state=state, level=level, previous_bar=previous_bar,
                             confirmation_bar=confirmation_bar, features=features, target_nodes=target_nodes,
                             guard=guard, source_mode=f"REAL_{gex.source.upper()}_{price_adapter.name.upper()}",
                             eligibility=eligibility)
            closest_scan = closest_scan or scan
            setup = self.detector.detect(scan)
            if setup:
                detected_scan, detected_setup = scan, setup
                break
        if detected_scan and detected_setup:
            setup, trade = self.process_scan_input(detected_scan, open_paper=open_paper)
            if not setup:
                reasons = ["Duplicate reclaim setup suppressed for same symbol, side, level, and completed candle"]
                payload = {"scan": detected_scan.model_dump(mode="json"),
                           "suppressed_setup": detected_setup.model_dump(mode="json"),
                           "monitoring_summary": monitoring_summary}
                observation_id = self.repository.store_observation(run_id, ticker, detected_scan.source_mode,
                    "duplicate_setup_suppressed", False, reasons, providers, payload,
                    free_validation_eligible=False, lane=Mode.SHADOW.value,
                    candle_end_utc=confirmation_bar.bar_end_utc, data_quality=data_quality)
                phase4a = self._record_phase4a_research(
                    run_id=run_id, observation_id=observation_id, ticker=ticker,
                    source_mode=detected_scan.source_mode, gex=gex, current_levels=current_levels,
                    prior_levels=prior_levels, bars=bars[-100:], state=state, guard=guard,
                    eligibility=eligibility, providers=providers, setup=detected_setup,
                    outcome="duplicate_setup_suppressed")
                return {"ticker": ticker, "observation_id": observation_id,
                        "outcome": "duplicate_setup_suppressed", "symbol_status": "ACTIVE",
                        "reasons": reasons, "providers": providers, "setup": None, "trade": None,
                        "phase4a_research": phase4a}
            lane = setup.recommended_mode
            outcome = f"{lane.value}_{'trade' if trade else 'setup'}"
            reasons = list(dict.fromkeys(setup.blocking_reasons + eligibility.missing_components))
            payload = {"scan": detected_scan.model_dump(mode="json"), "setup": setup.model_dump(mode="json"),
                       "trade": trade.model_dump(mode="json") if trade else None,
                       "monitoring_summary": monitoring_summary}
            observation_id = self.repository.store_observation(run_id, ticker, detected_scan.source_mode, outcome,
                setup.production_paper_allowed, reasons, providers, payload, setup.setup_event_id, setup.score.total,
                free_validation_eligible=setup.free_validation_paper_allowed, lane=lane.value,
                candle_end_utc=confirmation_bar.bar_end_utc, data_quality=data_quality)
            self._record_real_ablation(run_id, observation_id, detected_scan)
            phase4a = self._record_phase4a_research(
                run_id=run_id, observation_id=observation_id, ticker=ticker,
                source_mode=detected_scan.source_mode, gex=gex, current_levels=current_levels,
                prior_levels=prior_levels, bars=bars[-100:], state=state, guard=guard,
                eligibility=eligibility, providers=providers, setup=setup, outcome=outcome)
            return {"ticker": ticker, "observation_id": observation_id, "outcome": outcome,
                    "symbol_status": "MACRO_BLOCKED" if guard.blocked else "ACTIVE",
                    "reasons": reasons, "providers": providers, "setup": setup.model_dump(mode="json"),
                    "trade": trade.model_dump(mode="json") if trade else None,
                    "phase4a_research": phase4a}

        lane, free_blockers, production_blockers = self.detector.classifier.classify(closest_scan)
        reasons = ["No LEVEL_RECLAIM_LONG/SHORT pattern on the latest closed 5m bar"]
        reasons.extend(production_blockers if lane == Mode.FREE_VALIDATION else free_blockers)
        reasons.extend(eligibility.missing_components)
        reasons = list(dict.fromkeys(reasons))
        outcome = ("production_valid_no_setup" if lane == Mode.PRODUCTION else
                   "free_validation_valid_no_setup" if lane == Mode.FREE_VALIDATION else
                   "shadow_only_no_setup")
        payload = {"scan": closest_scan.model_dump(mode="json") if closest_scan else None,
                   "gex": gex.model_dump(mode="json"), "monitoring_summary": monitoring_summary}
        observation_id = self.repository.store_observation(run_id, ticker, "REAL_FREE_CORE", outcome,
            lane == Mode.PRODUCTION, reasons, providers, payload,
            free_validation_eligible=lane == Mode.FREE_VALIDATION, lane=lane.value,
            candle_end_utc=confirmation_bar.bar_end_utc, data_quality=data_quality)
        if closest_scan:
            self._record_real_ablation(run_id, observation_id, closest_scan)
        phase4a = self._record_phase4a_research(
            run_id=run_id, observation_id=observation_id, ticker=ticker,
            source_mode=closest_scan.source_mode if closest_scan else f"REAL_{gex.source.upper()}_{price_adapter.name.upper()}",
            gex=gex, current_levels=current_levels, prior_levels=prior_levels,
            bars=bars[-100:], state=state, guard=guard, eligibility=eligibility,
            providers=providers, setup=None, outcome=outcome)
        self.repository.store_audit("real_scan", "no_setup", reasons, {"observation_id": observation_id}, ticker)
        return {"ticker": ticker, "observation_id": observation_id, "outcome": outcome,
                "lane": lane.value, "free_validation_eligible": lane == Mode.FREE_VALIDATION,
                "production_data_eligible": lane == Mode.PRODUCTION, "reasons": reasons, "providers": providers,
                "symbol_status": ("MACRO_BLOCKED" if guard.blocked else "STALE_CANDLES" if any(
                    token in " ".join(reasons).lower() for token in ("stale", "freshness")) else "ACTIVE"),
                "setup": None, "trade": None, "phase4a_research": phase4a}

    def run_observation(self, request: ObservationRequest) -> dict[str, Any]:
        run_id = new_id("observe")
        tickers = [ticker.upper() for ticker in (request.tickers or self.watchlist.symbols())]
        session = self.session_calendar.evaluate(datetime.now(timezone.utc))
        if request.rth_only and not session["is_open"]:
            return {"run_id": run_id, "status": "skipped_market_closed", "cycles": 0,
                    "tickers": tickers, "scan_count": 0, "outcomes": {}, "results": [],
                    "session_state": session["state"], "next_rth_open": session.get("next_rth_open_utc"),
                    "message": "RTH-only observation did not call providers while the US market was closed"}
        results = []
        target = request.target_scans
        starting_valid = self._unique_free_validation_scans()
        completed_cycles = 0
        for cycle in range(request.cycles):
            if request.rth_only and not self.session_calendar.evaluate(datetime.now(timezone.utc))["is_open"]:
                break
            for ticker in tickers:
                results.append(self.real_scan_ticker(ticker, run_id, open_paper=request.open_paper,
                                                     include_free_fallback=request.include_free_fallback))
            completed_cycles += 1
            if target and self._unique_free_validation_scans() - starting_valid >= target:
                break
            if cycle + 1 < request.cycles and request.interval_seconds:
                time.sleep(request.interval_seconds)
        outcomes = Counter(item["outcome"] for item in results)
        return {"run_id": run_id, "status": "completed", "cycles": completed_cycles, "tickers": tickers,
                "scan_count": len(results), "outcomes": dict(outcomes), "results": results,
                "free_validation_unique_scans_added": self._unique_free_validation_scans() - starting_valid,
                "target_scans": target}

    def _unique_free_validation_scans(self) -> int:
        with self.repository.connect() as connection:
            row = connection.execute(
                """SELECT COUNT(*) FROM (
                       SELECT ticker,candle_end_utc FROM scan_observations
                       WHERE free_validation_eligible=1 AND lane=? AND candle_end_utc IS NOT NULL
                       GROUP BY ticker,candle_end_utc
                   )""", (Mode.FREE_VALIDATION.value,)
            ).fetchone()
        return int(row[0])

    def observation_status(self) -> dict[str, Any]:
        observations = self.repository.list_json("scan_observations", limit=100000)
        trades = self.repository.list_json("paper_trades", limit=100000)
        valid = [row for row in observations if row.get("production_eligible")]
        free_valid = [row for row in observations if row.get("free_validation_eligible")]
        production = [row for row in trades if row.get("mode") == Mode.PRODUCTION.value]
        free_trades = [row for row in trades if row.get("mode") == Mode.FREE_VALIDATION.value]
        shadow = [row for row in trades if row.get("mode") == Mode.SHADOW.value]
        target_scans = int(self.settings.get("observation.target_free_validation_scans", 50))
        target_trades = int(self.settings.get("observation.target_natural_paper_trades_min", 10))
        session = self.session_calendar.evaluate(datetime.now(timezone.utc))
        unique_free = self._unique_free_validation_scans()
        latest = observations[0] if observations else {}
        quality = latest.get("data_quality", {})
        providers = latest.get("providers", {})
        return {"real_observations": len(observations), "free_validation_valid_scans": unique_free,
                "free_validation_observation_rows": len(free_valid),
                "valid_production_data_scans": len(valid), "production_paper_trades": len(production),
                "free_validation_paper_trades": len(free_trades), "shadow_paper_trades": len(shadow),
                "shadow_only_observations": len([row for row in observations if
                    row.get("lane") == Mode.SHADOW.value or
                    (not row.get("free_validation_eligible") and not row.get("production_eligible"))]),
                "targets": {"free_validation_valid_scans": target_scans,
                            "valid_scans": target_scans, "natural_paper_trades_min": target_trades},
                "progress": {"free_validation_scans_remaining": max(0, target_scans-unique_free),
                             "valid_scans_remaining": max(0, target_scans-unique_free),
                             "paper_trades_observed": len(free_trades),
                             "paper_trades_remaining": max(0, target_trades-len(free_trades))},
                "session_state": session["state"], "next_rth_open": session.get("next_rth_open_utc"),
                "last_rth_observation": next((row.get("observed_at_utc") for row in observations
                                                if row.get("free_validation_eligible")), None),
                "candles_freshness": providers.get("price_freshness_seconds"),
                "provider_freshness": {"price": providers.get("price_freshness_seconds"),
                                       "structure": providers.get("structure_freshness_seconds")},
                "macro_calendar_approved": self.macro_adapter.approved,
                "unofficial_source_warning": bool(quality.get("unofficial_source") or
                    providers.get("unofficial_source") or providers.get("price") == "yfinance" or
                    any(row.get("providers", {}).get("price") == "yfinance" for row in observations[:25])),
                "missing_oi_greeks_count": sum(1 for row in observations if
                    row.get("data_quality", {}).get("oi_unavailable") or
                    row.get("data_quality", {}).get("greeks_unavailable") or
                    any(str(reason).lower() in {"open_interest", "greeks"}
                        for reason in row.get("reasons", []))),
                "stale_candle_count": sum(1 for row in observations if any(
                    "stale" in str(reason).lower() or "freshness" in str(reason).lower()
                    for reason in row.get("reasons", []))),
                "live_trading_disabled": True,
                "optimization_locked": (len(production) + len(free_trades)) < int(self.settings.get(
                    "observation.no_parameter_optimization_before_trades", 100)),
                "latest": observations[:25]}

    @staticmethod
    def _parse_time(value: str | None):
        if not value:
            return None
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    @staticmethod
    def _is_synthetic_record(payload: dict[str, Any]) -> bool:
        text = json.dumps(payload, sort_keys=True, default=str).lower()
        return "demo_fixture" in text or '"synthetic_present": true' in text or '"fixture": true' in text

    @staticmethod
    def _lane_label(value: str | None) -> str:
        labels = {
            Mode.SHADOW.value: "SHADOW",
            Mode.FREE_VALIDATION.value: "FREE_VALIDATION_PAPER",
            Mode.PRODUCTION.value: "PRODUCTION_PAPER",
        }
        return labels.get(str(value), str(value or "UNKNOWN").upper())

    @staticmethod
    def _reclaim_event_key_from_snapshot(setup: dict[str, Any]) -> str:
        snapshot = setup.get("signal_snapshot") or {}
        level = snapshot.get("level") or {}
        bar = snapshot.get("confirmation_bar") or {}
        level_price = level.get("price")
        rounded_price = round(float(level_price), 4) if level_price is not None else "unknown"
        return "|".join(str(part) for part in [
            setup.get("ticker"), setup.get("setup_type"), setup.get("side"),
            level.get("level_type") or setup.get("level_type"), rounded_price,
            bar.get("bar_end_utc") or setup.get("created_at_utc"),
        ])

    @staticmethod
    def _reclaim_event_key_from_setup(setup: SetupEvent) -> str:
        snapshot = setup.signal_snapshot or {}
        level = snapshot.get("level") or {}
        bar = snapshot.get("confirmation_bar") or {}
        level_price = level.get("price")
        rounded_price = round(float(level_price), 4) if level_price is not None else "unknown"
        return "|".join(str(part) for part in [
            setup.ticker, setup.setup_type.value, setup.side.value,
            level.get("level_type") or setup.level_type, rounded_price,
            bar.get("bar_end_utc") or setup.created_at_utc.isoformat(),
        ])

    def _duplicate_setup_exists(self, setup: SetupEvent) -> bool:
        if not str(setup.source_mode).startswith("REAL_"):
            return False
        key = setup.signal_snapshot.get("reclaim_event_key") or self._reclaim_event_key_from_setup(setup)
        for existing in self.repository.list_json(
                "setup_events", "WHERE ticker=? AND side=? AND setup_type=?",
                (setup.ticker, setup.side.value, setup.setup_type.value), limit=500):
            existing_key = (existing.get("signal_snapshot") or {}).get(
                "reclaim_event_key") or self._reclaim_event_key_from_snapshot(existing)
            if existing_key == key and not self._is_synthetic_record(existing):
                return True
        return False

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _median(values: list[float]) -> float:
        return float(median(values)) if values else 0.0

    @staticmethod
    def _score_bucket(value: Any) -> str:
        score = OptionsStructureTraderService._safe_float(value, -1)
        if score < 50:
            return "<50"
        if score < 60:
            return "50-59"
        if score < 70:
            return "60-69"
        if score < 80:
            return "70-79"
        if score < 90:
            return "80-89"
        return "90+"

    @staticmethod
    def _confidence_bucket(value: Any) -> str:
        confidence = OptionsStructureTraderService._safe_float(value, 0)
        if confidence < 0.35:
            return "<0.35"
        if confidence < 0.50:
            return "0.35-0.49"
        if confidence < 0.65:
            return "0.50-0.64"
        if confidence < 0.80:
            return "0.65-0.79"
        return "0.80+"

    def _natural_paper_sets(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, Any]]]:
        trades = self.repository.list_json("paper_trades", limit=100000)
        setups = self.repository.list_json("setup_events", limit=100000)
        setup_by_id = {item["setup_event_id"]: item for item in setups}
        natural_setups = [setup for setup in setups if not self._is_synthetic_record(setup)]
        natural_trades = [trade for trade in trades
                          if setup_by_id.get(trade["setup_event_id"])
                          and not self._is_synthetic_record(setup_by_id[trade["setup_event_id"]])]
        return natural_setups, natural_trades, setup_by_id

    def _paper_diagnostic_summary(self) -> dict[str, Any]:
        natural_setups, natural_trades, setup_by_id = self._natural_paper_sets()
        observations = [row for row in self.repository.list_json("scan_observations", limit=100000)
                        if not self._is_synthetic_record(row)]
        closed = [trade for trade in natural_trades if trade.get("status") == "closed"]
        active = [trade for trade in natural_trades if trade.get("status") in {"pending", "open", "partial"}]
        realized = [self._safe_float(trade.get("realized_r")) for trade in closed]
        winners = [value for value in realized if value > 0.05]
        losers = [value for value in realized if value < -0.05]
        gross_winners = sum(winners)
        gross_losers = abs(sum(losers))
        event_keys = [((setup.get("signal_snapshot") or {}).get("reclaim_event_key")
                       or self._reclaim_event_key_from_snapshot(setup)) for setup in natural_setups]
        reason_counts = Counter(
            reason for setup in natural_setups
            for reason in (setup.get("free_validation_blocking_reasons") or ["Free Validation eligible"]))
        duplicate_count = len(event_keys) - len(set(event_keys))
        per_symbol_active = Counter(trade.get("ticker") for trade in active)
        base_risk = (self._safe_float(self.settings.get("risk.paper_equity", 100000), 100000)
                     * self._safe_float(self.settings.get("risk.base_risk_per_trade", .0025), .0025))
        total_risk_dollars = sum(self._safe_float(trade.get("risk_dollars")) for trade in active)
        return {
            "unique_reclaim_events": len(set(event_keys)),
            "raw_reclaim_detections": len(natural_setups),
            "deduplicated_detections": len(set(event_keys)),
            "duplicate_reclaim_detections": duplicate_count,
            "duplicate_rate": round(duplicate_count / len(event_keys), 4) if event_keys else 0,
            "free_validation_trades": sum(1 for trade in natural_trades if trade.get("mode") == Mode.FREE_VALIDATION.value),
            "shadow_trades": sum(1 for trade in natural_trades if trade.get("mode") == Mode.SHADOW.value),
            "production_trades": sum(1 for trade in natural_trades if trade.get("mode") == Mode.PRODUCTION.value),
            "shadow_downgrade_reasons": reason_counts.most_common(8),
            "average_winner_r": round(sum(winners) / len(winners), 4) if winners else 0,
            "average_loser_r": round(sum(losers) / len(losers), 4) if losers else 0,
            "expectancy_r": round(sum(realized) / len(realized), 4) if realized else 0,
            "profit_factor": round(gross_winners / gross_losers, 4) if gross_losers else None,
            "open_portfolio_risk_r": round(total_risk_dollars / base_risk, 4) if base_risk else len(active),
            "open_positions_by_symbol": per_symbol_active.most_common(),
            "valid_free_observations": sum(1 for row in observations if row.get("free_validation_eligible")),
        }

    def paper_mode_status(self) -> dict[str, Any]:
        trades = self.repository.list_json("paper_trades", limit=100000)
        setups = self.repository.list_json("setup_events", limit=100000)
        observations = self.repository.list_json("scan_observations", limit=100000)
        states = self.repository.list_json("ticker_states", limit=100000)

        setup_by_id = {item["setup_event_id"]: item for item in setups}
        traded_setup_ids = {item["setup_event_id"] for item in trades}
        latest_price: dict[str, dict[str, Any]] = {}
        for state in states:
            latest_price.setdefault(state["ticker"], state)

        def natural_setup(setup: dict[str, Any] | None) -> bool:
            return bool(setup) and not self._is_synthetic_record(setup)

        natural_trades = [trade for trade in trades if natural_setup(setup_by_id.get(trade["setup_event_id"]))]
        synthetic_trades = [trade for trade in trades if not natural_setup(setup_by_id.get(trade["setup_event_id"]))]

        def risk_per_share(trade: dict[str, Any]) -> float:
            fill = trade.get("actual_fill_price") or trade.get("planned_entry") or 0
            return abs(float(fill) - float(trade.get("stop_initial") or trade.get("stop_current") or fill))

        def current_r(trade: dict[str, Any]) -> float | None:
            state = latest_price.get(trade["ticker"])
            price = state.get("spot_price") if state else None
            fill = trade.get("actual_fill_price") or trade.get("planned_entry")
            risk = risk_per_share(trade)
            if price is None or fill is None or risk <= 0:
                return None
            direction = 1 if trade.get("side") == Side.LONG.value else -1
            return round((float(price)-float(fill))*direction/risk, 4)

        def duration_minutes(trade: dict[str, Any]) -> float | None:
            start = self._parse_time(trade.get("opened_at_utc") or trade.get("created_at_utc"))
            end = self._parse_time(trade.get("closed_at_utc")) or datetime.now(timezone.utc)
            return round((end-start).total_seconds()/60, 2) if start else None

        def exit_price(trade: dict[str, Any]) -> float | None:
            reason = str(trade.get("exit_reason") or "")
            if "stop" in reason:
                return trade.get("stop_current")
            if reason == "tp1" and trade.get("targets"):
                return trade["targets"][0]
            return None

        def trade_row(trade: dict[str, Any], include_current: bool = False) -> dict[str, Any]:
            state = latest_price.get(trade["ticker"], {})
            targets = list(trade.get("targets") or [])
            row = {
                "symbol": trade["ticker"],
                "lane": self._lane_label(trade.get("mode")),
                "setup_family": trade.get("setup_type"),
                "direction": trade.get("side"),
                "entry": trade.get("actual_fill_price") or trade.get("planned_entry"),
                "stop": trade.get("stop_current") or trade.get("stop_initial"),
                "tp1": targets[0] if len(targets) > 0 else None,
                "tp2": targets[1] if len(targets) > 1 else None,
                "tp3": targets[2] if len(targets) > 2 else None,
                "targets": targets,
                "mfe": round(float(trade.get("mfe_r", 0)), 4),
                "mae": round(float(trade.get("mae_r", 0)), 4),
                "opened_at": trade.get("opened_at_utc"),
                "current_status": trade.get("status"),
                "realized_r": round(float(trade.get("realized_r", 0)), 4),
                "exit_reason": trade.get("exit_reason"),
                "duration_minutes": duration_minutes(trade),
                "data_quality_tier": (setup_by_id.get(trade["setup_event_id"], {}).get("score") or {}).get(
                    "data_quality_tier"),
            }
            if include_current:
                row["current_price"] = state.get("spot_price")
                row["current_r"] = current_r(trade)
            else:
                row["exit"] = exit_price(trade)
            return row

        open_trades = [trade_row(trade, True) for trade in natural_trades
                       if trade.get("status") in {"pending", "open", "partial"}]
        closed_trades = [trade_row(trade, False) for trade in natural_trades
                         if trade.get("status") == "closed"][:20]

        pending_setup_rows = []
        for setup in setups:
            if not natural_setup(setup) or setup["setup_event_id"] in traded_setup_ids:
                continue
            snapshot = setup.get("signal_snapshot") or {}
            level = snapshot.get("level") or {}
            score = setup.get("score") or {}
            reasons = list(dict.fromkeys(
                list(setup.get("blocking_reasons") or []) +
                list(setup.get("free_validation_blocking_reasons") or []) +
                list(setup.get("reason") or [])))
            pending_setup_rows.append({
                "symbol": setup["ticker"],
                "direction": setup.get("side"),
                "detected_options_level": {
                    "type": level.get("level_type"),
                    "price": level.get("price"),
                    "zone_low": level.get("zone_low"),
                    "zone_high": level.get("zone_high"),
                },
                "confluence_score": score.get("total"),
                "confidence": score.get("confidence_score"),
                "missing_confirmation": score.get("missing_components") or [],
                "reason_no_paper_order": reasons or ["No paper order was opened for this stored setup"],
                "detected_at": setup.get("created_at_utc"),
                "lane": self._lane_label(setup.get("recommended_mode")),
            })
            if len(pending_setup_rows) >= 20:
                break

        valid_scan_rows = []
        for row in observations:
            if not row.get("free_validation_eligible") or self._is_synthetic_record(row):
                continue
            payload = row.get("payload") or {}
            scan = payload.get("scan") or {}
            level = scan.get("level") or {}
            bar = scan.get("confirmation_bar") or {}
            gex = payload.get("gex") or {}
            setup = payload.get("setup") or {}
            close = bar.get("close")
            level_price = level.get("price")
            relative = round(float(close)-float(level_price), 4) if close is not None and level_price is not None else None
            valid_scan_rows.append({
                "symbol": row["ticker"],
                "timestamp": row.get("candle_end_utc") or row.get("observed_at_utc"),
                "gex": {"gamma_flip": gex.get("gamma_flip"), "call_wall": gex.get("call_wall"),
                        "put_wall": gex.get("put_wall"),
                        "detected_level": {"type": level.get("level_type"), "price": level_price}},
                "price_relative_to_level": relative,
                "reclaim_state": setup.get("setup_type") or ("NO_RECLAIM" if relative is not None else "UNKNOWN"),
                "score": row.get("score_total"),
                "result": "ENTERED" if row.get("setup_event_id") else "NO_SETUP",
            })
            if len(valid_scan_rows) >= 20:
                break

        closed_all = [trade for trade in natural_trades if trade.get("status") == "closed"]
        realized = [float(trade.get("realized_r", 0)) for trade in closed_all]
        mfes = [float(trade.get("mfe_r", 0)) for trade in closed_all]
        maes = [float(trade.get("mae_r", 0)) for trade in closed_all]
        unique_free = {(row["ticker"], row.get("candle_end_utc")) for row in observations
                       if row.get("free_validation_eligible") and row.get("candle_end_utc")
                       and not self._is_synthetic_record(row)}
        tier1 = {entry.symbol for entry in self.watchlist.entries.values() if entry.tier == "tier_1_core"}
        natural_setups = [setup for setup in setups if natural_setup(setup)]
        natural_entries = [trade for trade in natural_trades if trade.get("opened_at_utc")]
        breakevens = [trade for trade in closed_all if abs(float(trade.get("realized_r", 0))) < 0.05]
        diagnostic = self._paper_diagnostic_summary()
        return {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "synthetic_test_records_excluded": {"paper_trades": len(synthetic_trades)},
            "open_paper_trades": open_trades,
            "closed_paper_trades": closed_trades,
            "pending_setups": pending_setup_rows,
            "recent_valid_scans": valid_scan_rows,
            "summary": {
                "total_valid_rth_scans": len(unique_free),
                "free_validation_scans": len(unique_free),
                "tier1_scans": sum(1 for ticker, _ in unique_free if ticker in tier1),
                "natural_reclaim_setups_detected": len(natural_setups),
                "paper_entries_opened": len(natural_entries),
                "paper_entries_closed": len(closed_all),
                "winners": len([value for value in realized if value > 0.05]),
                "losers": len([value for value in realized if value < -0.05]),
                "breakevens": len(breakevens),
                "average_realized_r": round(sum(realized)/len(realized), 4) if realized else 0,
                "average_mfe": round(sum(mfes)/len(mfes), 4) if mfes else 0,
                "average_mae": round(sum(maes)/len(maes), 4) if maes else 0,
                **diagnostic,
            },
            "zero_natural_entries": len(natural_entries) == 0,
            "main_no_entry_reasons": Counter(
                reason for setup in pending_setup_rows for reason in setup["reason_no_paper_order"]).most_common(8),
        }

    def phase2d2_paper_diagnostic(self) -> dict[str, Any]:
        natural_setups, natural_trades, setup_by_id = self._natural_paper_sets()
        observations = [row for row in self.repository.list_json("scan_observations", limit=100000)
                        if not self._is_synthetic_record(row)]
        observations_by_setup: dict[str, dict[str, Any]] = {}
        for row in observations:
            if row.get("setup_event_id") and row["setup_event_id"] not in observations_by_setup:
                observations_by_setup[row["setup_event_id"]] = row
        trades_by_setup = defaultdict(list)
        for trade in natural_trades:
            trades_by_setup[trade["setup_event_id"]].append(trade)

        def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                for row in rows:
                    writer.writerow({key: json.dumps(value, default=str) if isinstance(value, (list, dict, tuple))
                                     else value for key, value in row.items()})

        def first_trade(setup_id: str) -> dict[str, Any] | None:
            items = trades_by_setup.get(setup_id) or []
            return items[0] if items else None

        lane_rows: list[dict[str, Any]] = []
        downgrade_reason_counts: Counter[str] = Counter()
        for setup in natural_setups:
            snapshot = setup.get("signal_snapshot") or {}
            eligibility = snapshot.get("eligibility") or {}
            guard = snapshot.get("guard") or {}
            score = setup.get("score") or {}
            obs = observations_by_setup.get(setup["setup_event_id"]) or {}
            providers = obs.get("providers") or {}
            router = providers.get("candle_router") or {}
            trade = first_trade(setup["setup_event_id"])
            free_reasons = setup.get("free_validation_blocking_reasons") or []
            reason = "; ".join(free_reasons) if free_reasons else "Free Validation eligible"
            downgrade_reason_counts.update(free_reasons or ["Free Validation eligible"])
            lane_rows.append({
                "setup_event_id": setup["setup_event_id"],
                "trade_id": trade.get("trade_id") if trade else None,
                "symbol": setup.get("ticker"),
                "timestamp": setup.get("created_at_utc"),
                "scan_lane": self._lane_label(obs.get("lane")),
                "scan_data_quality": (obs.get("data_quality") or {}).get("data_quality_tier"),
                "setup_lane": self._lane_label(setup.get("recommended_mode")),
                "trade_lane": self._lane_label(trade.get("mode") if trade else None),
                "free_validation_scan_eligible": bool(obs.get("free_validation_eligible")),
                "free_validation_trade_eligible": bool(setup.get("free_validation_paper_allowed")),
                "downgrade_reason": reason,
                "missing_components": score.get("missing_components") or eligibility.get("missing_components") or [],
                "candle_provider": router.get("selected_candle_provider") or providers.get("price") or eligibility.get("price_provider"),
                "candle_freshness": providers.get("price_freshness_seconds") or eligibility.get("price_freshness_seconds"),
                "options_provider": providers.get("structure") or eligibility.get("structure_provider"),
                "gex_available": eligibility.get("structure_provider") in {"algox", "gammagrid"},
                "oi_available": not bool(eligibility.get("oi_unavailable")),
                "greeks_available": not bool(eligibility.get("greeks_unavailable")),
                "macro_status": ("BLOCKED" if guard.get("blocked") else
                                 "UNKNOWN" if guard.get("macro_unknown") else
                                 "APPROVED" if guard.get("calendar_approved") else "UNAPPROVED"),
                "score_confidence": score.get("confidence_score"),
            })

        event_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for setup in natural_setups:
            key = ((setup.get("signal_snapshot") or {}).get("reclaim_event_key")
                   or self._reclaim_event_key_from_snapshot(setup))
            event_groups[key].append(setup)
        dedupe_rows: list[dict[str, Any]] = []
        for key, rows in sorted(event_groups.items(), key=lambda item: item[0]):
            ordered = sorted(rows, key=lambda item: item.get("created_at_utc") or "")
            for index, setup in enumerate(ordered, start=1):
                dedupe_rows.append({
                    "reclaim_event_key": key,
                    "setup_event_id": setup["setup_event_id"],
                    "symbol": setup.get("ticker"),
                    "side": setup.get("side"),
                    "setup_type": setup.get("setup_type"),
                    "level_type": setup.get("level_type"),
                    "created_at_utc": setup.get("created_at_utc"),
                    "duplicate_index": index,
                    "is_duplicate": index > 1,
                    "group_size": len(ordered),
                    "paper_trade_count": len(trades_by_setup.get(setup["setup_event_id"], [])),
                })

        def trade_dimension_row(trade: dict[str, Any]) -> dict[str, Any]:
            setup = setup_by_id.get(trade["setup_event_id"], {})
            snapshot = setup.get("signal_snapshot") or {}
            eligibility = snapshot.get("eligibility") or {}
            score = setup.get("score") or {}
            watch = self.watchlist.entry(trade.get("ticker", ""))
            return {
                "trade_id": trade.get("trade_id"),
                "setup_event_id": trade.get("setup_event_id"),
                "symbol": trade.get("ticker"),
                "tier": watch.tier if watch else "unknown",
                "direction": trade.get("side"),
                "lane": self._lane_label(trade.get("mode")),
                "setup_family": trade.get("setup_type"),
                "score": trade.get("score_total"),
                "score_bucket": self._score_bucket(trade.get("score_total")),
                "confidence": score.get("confidence_score"),
                "confidence_bucket": self._confidence_bucket(score.get("confidence_score")),
                "candle_provider": eligibility.get("price_provider"),
                "gex_regime": (snapshot.get("features") or {}).get("raw", {}).get("gamma_regime")
                              or (snapshot.get("features") or {}).get("gamma_regime") or "unknown",
                "entry_type": trade.get("entry_type"),
                "stop_variant": trade.get("variant_id") or "baseline",
                "target_variant": self.settings.get("targets.default_logic", "baseline"),
                "exit_reason": trade.get("exit_reason"),
                "realized_r": self._safe_float(trade.get("realized_r")),
                "mfe_r": self._safe_float(trade.get("mfe_r")),
                "mae_r": self._safe_float(trade.get("mae_r")),
            }

        closed = [trade for trade in natural_trades if trade.get("status") == "closed"]
        trade_rows = [trade_dimension_row(trade) for trade in closed]

        def stats(values: list[dict[str, Any]], dimension: str, bucket: str) -> dict[str, Any]:
            r_values = [self._safe_float(row["realized_r"]) for row in values]
            winners = [value for value in r_values if value > 0.05]
            losers = [value for value in r_values if value < -0.05]
            bes = [value for value in r_values if abs(value) <= 0.05]
            gross_winners = sum(winners)
            gross_losers = abs(sum(losers))
            return {
                "dimension": dimension,
                "bucket": bucket,
                "n": len(values),
                "total_r": round(sum(r_values), 4),
                "average_r": round(sum(r_values)/len(r_values), 4) if r_values else 0,
                "median_r": round(self._median(r_values), 4),
                "profit_factor": round(gross_winners/gross_losers, 4) if gross_losers else None,
                "win_rate": round(len(winners)/len(r_values), 4) if r_values else 0,
                "loss_rate": round(len(losers)/len(r_values), 4) if r_values else 0,
                "breakeven_rate": round(len(bes)/len(r_values), 4) if r_values else 0,
                "average_winner_r": round(sum(winners)/len(winners), 4) if winners else 0,
                "median_winner_r": round(self._median(winners), 4),
                "average_loser_r": round(sum(losers)/len(losers), 4) if losers else 0,
                "median_loser_r": round(self._median(losers), 4),
                "average_mfe": round(sum(self._safe_float(row["mfe_r"]) for row in values)/len(values), 4) if values else 0,
                "average_mae": round(sum(self._safe_float(row["mae_r"]) for row in values)/len(values), 4) if values else 0,
                "expectancy": round(sum(r_values)/len(r_values), 4) if r_values else 0,
            }

        expectancy_rows: list[dict[str, Any]] = [stats(trade_rows, "overall", "all")]
        for dimension in ["direction", "symbol", "tier", "score_bucket", "confidence_bucket",
                          "candle_provider", "gex_regime", "entry_type", "stop_variant",
                          "target_variant", "exit_reason"]:
            buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for row in trade_rows:
                buckets[str(row.get(dimension) or "unknown")].append(row)
            for bucket, rows in sorted(buckets.items()):
                expectancy_rows.append(stats(rows, dimension, bucket))

        def duration_minutes(trade: dict[str, Any]) -> float | None:
            start = self._parse_time(trade.get("opened_at_utc") or trade.get("created_at_utc"))
            end = self._parse_time(trade.get("closed_at_utc"))
            return round((end-start).total_seconds()/60, 2) if start and end else None

        partial = self._safe_float((self.settings.get("targets.partials", [.33]) or [.33])[0], .33)
        mfe_rows: list[dict[str, Any]] = []
        for trade in closed:
            entry = self._safe_float(trade.get("actual_fill_price") or trade.get("planned_entry"))
            stop = self._safe_float(trade.get("stop_initial"))
            risk = abs(entry - stop)
            side_mult = 1 if trade.get("side") == Side.LONG.value else -1
            targets = list(trade.get("targets") or [])
            target_rs = [abs(self._safe_float(target) - entry) / risk if risk else 0 for target in targets[:3]]
            close_tp1 = min(int(trade.get("shares") or 0), max(1, round(int(trade.get("shares") or 0) * partial))) \
                if trade.get("tp1_at_utc") else 0
            final_exit = None
            if trade.get("exit_reason") == "tp1" and targets:
                final_exit = targets[0]
            elif trade.get("exit_reason") and "stop" in str(trade.get("exit_reason")):
                final_exit = trade.get("stop_current")
            maximum_favorable_price = entry + (self._safe_float(trade.get("mfe_r")) * risk * side_mult)
            mfe_rows.append({
                "trade_id": trade.get("trade_id"),
                "setup_event_id": trade.get("setup_event_id"),
                "symbol": trade.get("ticker"),
                "direction": trade.get("side"),
                "lane": self._lane_label(trade.get("mode")),
                "entry": entry,
                "initial_stop": stop,
                "initial_risk": risk,
                "tp1": targets[0] if len(targets) > 0 else None,
                "tp2": targets[1] if len(targets) > 1 else None,
                "tp3": targets[2] if len(targets) > 2 else None,
                "size_at_entry": trade.get("shares"),
                "size_closed_at_tp1": close_tp1,
                "size_closed_at_tp2": 0,
                "runner_size": trade.get("remaining_shares"),
                "final_exit": final_exit,
                "gross_realized_r": round(self._safe_float(trade.get("realized_r")), 4),
                "remaining_unrealized_r": 0,
                "final_realized_r": round(self._safe_float(trade.get("realized_r")), 4),
                "mfe_before_exit": maximum_favorable_price,
                "mae_before_exit_r": round(self._safe_float(trade.get("mae_r")), 4),
                "mfe_r": round(self._safe_float(trade.get("mfe_r")), 4),
                "mae_r": round(self._safe_float(trade.get("mae_r")), 4),
                "reached_0_5r": self._safe_float(trade.get("mfe_r")) >= 0.5,
                "reached_1r": self._safe_float(trade.get("mfe_r")) >= 1.0,
                "reached_1_5r": self._safe_float(trade.get("mfe_r")) >= 1.5,
                "reached_2r": self._safe_float(trade.get("mfe_r")) >= 2.0,
                "tp1_touched": len(target_rs) > 0 and self._safe_float(trade.get("mfe_r")) >= target_rs[0],
                "tp2_touched": len(target_rs) > 1 and self._safe_float(trade.get("mfe_r")) >= target_rs[1],
                "tp3_touched": len(target_rs) > 2 and self._safe_float(trade.get("mfe_r")) >= target_rs[2],
                "exit_reason": trade.get("exit_reason"),
                "duration_minutes": duration_minutes(trade),
                "data_quality_tier": (setup_by_id.get(trade["setup_event_id"], {}).get("score") or {}).get("data_quality_tier"),
            })

        output_root = self.artifact_root
        lane_path = output_root / "paper_lane_downgrades.csv"
        dedupe_path = output_root / "setup_deduplication_report.csv"
        expectancy_path = output_root / "paper_expectancy_analysis.csv"
        mfe_path = output_root / "mfe_mae_analysis.csv"
        write_csv(lane_path, list(lane_rows[0].keys()) if lane_rows else ["setup_event_id"], lane_rows)
        write_csv(dedupe_path, list(dedupe_rows[0].keys()) if dedupe_rows else ["reclaim_event_key"], dedupe_rows)
        write_csv(expectancy_path, list(expectancy_rows[0].keys()), expectancy_rows)
        write_csv(mfe_path, list(mfe_rows[0].keys()) if mfe_rows else ["trade_id"], mfe_rows)

        diagnostic = self._paper_diagnostic_summary()
        status = self.paper_mode_status()["summary"]
        score_buckets = [row for row in expectancy_rows if row["dimension"] == "score_bucket"]
        closed_r = [self._safe_float(trade.get("realized_r")) for trade in closed]
        cumulative, max_peak, max_drawdown = 0.0, 0.0, 0.0
        for value in reversed(closed_r):
            cumulative += value
            max_peak = max(max_peak, cumulative)
            max_drawdown = min(max_drawdown, cumulative - max_peak)
        top_reasons = "\n".join(
            f"| {reason} | {count} | {sum(1 for row in lane_rows if reason in str(row['downgrade_reason']))} | {count/max(len(natural_setups),1):.1%} |"
            for reason, count in downgrade_reason_counts.most_common(12)) or "| none | 0 | 0 | 0% |"
        score_lines = "\n".join(
            f"| {row['bucket']} | {row['n']} | {row['win_rate']:.1%} | {row['average_r']} | {row['median_r']} | {row['profit_factor']} | {row['average_mfe']} | {row['average_mae']} |"
            for row in score_buckets) or "| none | 0 | 0% | 0 | 0 | 0 | 0 | 0 |"
        markdown = f"""# Phase 2D.2 Paper Lane + Expectancy Diagnostic

Generated: {datetime.now(timezone.utc).isoformat()}

## Current natural paper sample

- Synthetic/test paper records excluded: {self.paper_mode_status()['synthetic_test_records_excluded']['paper_trades']}
- Unique Free Validation RTH scans: {status['free_validation_scans']}
- Tier 1 scans: {status['tier1_scans']}
- Natural reclaim setup detections: {status['natural_reclaim_setups_detected']}
- Unique reclaim events: {diagnostic['unique_reclaim_events']}
- Duplicate reclaim detections: {diagnostic['duplicate_reclaim_detections']} ({diagnostic['duplicate_rate']:.1%})
- Paper entries opened: {status['paper_entries_opened']}
- Closed natural trades: {status['paper_entries_closed']}
- Free Validation Paper trades: {diagnostic['free_validation_trades']}
- Shadow Paper trades: {diagnostic['shadow_trades']}
- Production Paper trades: {diagnostic['production_trades']}

## Lane diagnosis

The earlier pasted snapshot said all natural paper trades were Shadow. The live journal now contains one natural Free Validation Paper trade; all remaining natural trades are Shadow. This is mostly intended lane behavior, not retroactive trade promotion material: scan eligibility is less strict than trade eligibility. A scan can be Free-Validation-valid while the detected setup is still downgraded because trade-level requirements fail.

There is one prospective hygiene issue: repeated observation can re-detect the same completed-candle reclaim. The system now records a stable reclaim_event_key and suppresses future duplicate natural setup/trade creation for the same symbol, side, level, and completed candle.

| reason | setups | trades | % |
|---|---:|---:|---:|
{top_reasons}

## Expectancy summary

- Total closed-trade R: {round(sum(closed_r), 4)}
- Average / expectancy R: {diagnostic['expectancy_r']}
- Median R: {round(self._median(closed_r), 4)}
- Profit factor: {diagnostic['profit_factor']}
- Winners / losers / breakevens: {status['winners']} / {status['losers']} / {status['breakevens']}
- Average winner R: {diagnostic['average_winner_r']}
- Average loser R: {diagnostic['average_loser_r']}
- Average MFE / MAE: {status['average_mfe']} / {status['average_mae']}
- Max drawdown in R: {round(max_drawdown, 4)}

## TP1 behavior

TP1 is implemented as a partial exit using the first configured target partial. The broker then moves the stop to breakeven when `targets.breakeven_default` is `after_TP1`. The current broker only checks TP1 in live paper simulation; TP2/TP3 are recorded in the plan but are not yet executed as independent scale-out events. This can make a trade count as a winner after a small TP1 partial while the remaining runner later exits at breakeven or loss, which explains how the win count can exceed the loss count while average R remains flat-to-negative.

## Score discrimination

| score bucket | N | win rate | average R | median R | profit factor | avg MFE | avg MAE |
|---|---:|---:|---:|---:|---:|---:|---:|
{score_lines}

## Open trade sanity

- Active natural paper trades: {len([trade for trade in natural_trades if trade.get('status') in {'pending', 'open', 'partial'}])}
- Total concurrent initial risk: {diagnostic['open_portfolio_risk_r']}R-equivalent
- Positions by symbol: {diagnostic['open_positions_by_symbol']}
- Duplicate positions per identical setup event: {sum(max(0, count-1) for count in Counter(trade.get('setup_event_id') for trade in natural_trades if trade.get('status') in {'pending', 'open', 'partial'}).values())}

Shadow Paper currently does not enforce the same max-open/max-same-symbol limits that Free Validation and Production Paper enforce. That allows broad research capture, but it can create unrealistic portfolio exposure in Shadow statistics. I did not change this behavior because the phase asks for diagnosis, not strategy or risk-rule changes.

## Artifact files

- paper_lane_downgrades.csv
- setup_deduplication_report.csv
- paper_expectancy_analysis.csv
- mfe_mae_analysis.csv

## No parameter changes

Confluence weights, score thresholds, stop logic, target logic, breakeven logic, setup definitions, Production gates, no-live-trading structure, and Portfolio OS isolation were left unchanged.
"""
        markdown_path = output_root / "PHASE_2D2_PAPER_DIAGNOSTIC.md"
        markdown_path.write_text(markdown, encoding="utf-8")
        return {"report": {"summary": status, "diagnostic": diagnostic,
                           "closed_trade_count": len(closed), "lane_reason_counts": downgrade_reason_counts.most_common()},
                "markdown_path": str(markdown_path),
                "csv_paths": [str(lane_path), str(dedupe_path), str(expectancy_path), str(mfe_path)]}

    def phase2d3_trade_management_research(self) -> dict[str, Any]:
        return self.trade_management_research.generate()

    def forward_management_ab_status(self) -> dict[str, Any]:
        return self.forward_management_ab.status()

    def phase2d4_forward_management_ab(self) -> dict[str, Any]:
        return self.forward_management_ab.generate_report()

    def phase2d5_edge_discovery(self, report_date: str | None = None) -> dict[str, Any]:
        return self.edge_discovery.generate(report_date, ab_status=self.forward_management_ab_status())

    def phase2d6_forward_edge_validation(self, report_date: str | None = None) -> dict[str, Any]:
        return self.forward_edge_validation.generate(report_date)

    def phase2d7_short_failure_decomposition(self, report_date: str | None = None) -> dict[str, Any]:
        return self.short_failure_decomposition.generate_phase2d7(report_date)

    def phase4a_multitimeframe_edge_status(self) -> dict[str, Any]:
        return self.multitimeframe_edge_research.status()

    def phase4a_multitimeframe_edge_report(self, report_date: str | None = None) -> dict[str, Any]:
        return self.multitimeframe_edge_research.generate_report(report_date)

    def phase4b2_prospective_status(self, report_date: str | None = None) -> dict[str, Any]:
        return self.multitimeframe_edge_research.phase4b2_status(report_date)

    def phase4b2_prospective_report(self, report_date: str | None = None) -> dict[str, Any]:
        return self.multitimeframe_edge_research.generate_phase4b2_report(report_date)

    def phase4b2_research_integrity_qa(self, report_date: str, *, mark_pre_fix: bool = True) -> dict[str, Any]:
        return self.multitimeframe_edge_research.generate_phase4b2_integrity_qa_report(
            report_date, mark_pre_fix=mark_pre_fix)

    def phase4b3_start_clean_forward_validation(self) -> dict[str, Any]:
        return self.multitimeframe_edge_research.start_clean_forward_validation()

    def phase4b1_edge_decomposition_status(self) -> dict[str, Any]:
        from .phase4b1 import Phase4B1EdgeDecomposer
        return Phase4B1EdgeDecomposer(self.artifact_root).status()

    def phase4b1_edge_decomposition_report(self) -> dict[str, Any]:
        from .phase4b1 import REPORT_NAME, Phase4B1EdgeDecomposer
        path = self.artifact_root / REPORT_NAME
        status = Phase4B1EdgeDecomposer(self.artifact_root).status()
        return {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "markdown_path": str(path),
            "markdown_available": path.exists(),
            "markdown": path.read_text(encoding="utf-8") if path.exists() else "",
            "dashboard": status,
            "research_only": True,
            "canonical_strategy_unchanged": True,
            "live_trading_disabled": True,
            "portfolio_os_isolated": True,
        }

    def phase3b_historical_reconstruction(self, *, symbols: list[str] | None = None,
                                           period: str = "20d", interval: str = "5m") -> dict[str, Any]:
        from .historical import HistoricalReconstructionPipeline
        return HistoricalReconstructionPipeline(self.repository, self.settings, self.artifact_root).run(
            symbols=symbols, period=period, interval=interval)

    def phase2c_report(self) -> dict[str, Any]:
        return self.phase2c_reports.generate(
            self.source_status(), self.macro_adapter.approved,
            int(self.settings.get("observation.target_free_validation_scans", 50)))

    def scheduler_status(self) -> dict[str, Any]:
        from .scheduler import JsonStateStore
        status = JsonStateStore(self.settings.path("scheduler.status_path")).read()
        session = self.session_calendar.evaluate(datetime.now(timezone.utc))
        if not status:
            status = {"daemon_status": "NOT_STARTED", "heartbeat_at_utc": None,
                      "last_scan_time": None, "next_scan_time": None, "last_error": None,
                      "scans_today": 0, "free_validation_scans_today": 0,
                      "shadow_scans_today": 0, "production_scans_today": 0,
                      "symbols_valid_today": 0, "symbols_blocked_today": 0,
                      "provider_failures_today": 0,
                      "daily_report_status": "pending"}
        pid_path = self.settings.path("scheduler.pid_path")
        running = False
        if pid_path.exists():
            try:
                daemon_pid = int(pid_path.read_text(encoding="utf-8").strip())
                if os.name == "nt":
                    import ctypes
                    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, daemon_pid)
                    running = bool(handle)
                    if handle:
                        ctypes.windll.kernel32.CloseHandle(handle)
                else:
                    os.kill(daemon_pid, 0)
                    running = True
            except (OSError, ValueError, AttributeError):
                running = False
        if not running and status.get("daemon_status") not in {"NOT_STARTED", "STOPPED"}:
            status["daemon_status"] = "NOT_RUNNING"
        status.update({"current_session_state": status.get("current_session_state", session["state"]),
                       "next_rth_open": session.get("next_rth_open_utc"),
                       "next_rth_close": session.get("next_rth_close_utc"),
                       "provider_status": self.source_status(), "live_trading_disabled": True})
        return status

    def watchlist_status(self) -> dict[str, Any]:
        return self.watchlist.status()

    def market_data_freshness_status(self) -> dict[str, Any]:
        observations = self.repository.list_json("scan_observations", limit=1000)
        summary = summarize_provider_freshness(observations)
        latest_by_symbol: dict[str, dict[str, Any]] = {}
        for row in observations:
            if row["ticker"] in latest_by_symbol:
                continue
            providers = row.get("providers", {})
            router = providers.get("candle_router") or {}
            quote = router.get("quote_confirmation") or {}
            latest_by_symbol[row["ticker"]] = {
                "symbol": row["ticker"],
                "tier": row.get("data_quality", {}).get("watchlist_tier"),
                "selected_candle_provider": router.get("selected_candle_provider") or providers.get("price"),
                "latest_completed_candle": router.get("candle_timestamp") or row.get("candle_end_utc"),
                "expected_completed_candle": router.get("expected_completed_bar_time"),
                "candle_lag_seconds": router.get("candle_age_seconds") or providers.get("price_freshness_seconds"),
                "finnhub_quote_age_seconds": quote.get("quote_age_seconds"),
                "fallback_used": bool(router.get("fallback_used")),
                "provider_attempts": router.get("providers_attempted") or [],
                "status": "VALID" if row.get("free_validation_eligible") else (
                    router.get("rejection_reason") or row.get("outcome")),
            }
        metrics = Counter()
        for row in observations:
            providers = row.get("providers", {})
            router = providers.get("candle_router") or {}
            statuses = router.get("router_status") or {}
            if "YFINANCE" in (router.get("providers_attempted") or []):
                metrics["yfinance_requests"] += 1
                metrics["yfinance_fresh" if statuses.get("yfinance_status") == "FRESH" else "yfinance_stale"] += 1
            if "FINNHUB" in (router.get("providers_attempted") or []):
                metrics["finnhub_requests"] += 1
                quote_status = statuses.get("finnhub_quote_status")
                metrics["finnhub_fresh_quotes" if quote_status == "FRESH" else "finnhub_stale_quotes"] += 1
                metrics["finnhub_auth_errors"] += int(quote_status == "AUTH_INVALID")
                metrics["finnhub_rate_limits"] += int(quote_status == "RATE_LIMITED")
            if "ALPHA_VANTAGE" in (router.get("providers_attempted") or []):
                metrics["alpha_vantage_requests"] += 1
                alpha_status = statuses.get("alpha_vantage_status")
                metrics["alpha_vantage_fresh" if alpha_status == "FRESH" else "alpha_vantage_stale"] += 1
                metrics["alpha_vantage_rate_limits"] += int(alpha_status == "RATE_LIMITED")
                metrics["alpha_vantage_auth_errors"] += int(alpha_status == "AUTH_INVALID")
            metrics["fallback_attempts"] += int(bool(router.get("fallback_used")))
            metrics["fallback_successes"] += int(bool(router.get("fallback_used") and row.get("free_validation_eligible")))
            cross = statuses.get("provider_crosscheck_status") or row.get("data_quality", {}).get("provider_crosscheck_status")
            if cross:
                metrics["cross_provider_agreements"] += int(cross.get("state") == "AGREE")
                metrics["cross_provider_conflicts"] += int(cross.get("state") in {"MAJOR_CONFLICT", "TIMESTAMP_MISMATCH"})
        return {"summary": summary, "metrics": dict(metrics),
                "alpha_vantage_budget": self.candle_router.alpha_budget.status(),
                "symbols": list(latest_by_symbol.values())}

    def provider_freshness_report(self, report_date: str | None = None) -> dict[str, Any]:
        from datetime import time as dt_time, timedelta
        from zoneinfo import ZoneInfo
        eastern = ZoneInfo("America/New_York")
        report_date = report_date or datetime.now(eastern).date().isoformat()
        local_day = datetime.fromisoformat(report_date).date()
        start_at = datetime.combine(local_day, dt_time.min, eastern).astimezone(timezone.utc)
        end_at = start_at + timedelta(days=1)
        rows = self.repository.list_json(
            "scan_observations", "WHERE observed_at_utc>=? AND observed_at_utc<?",
            (start_at.isoformat(), end_at.isoformat()), 100000)
        summary = summarize_provider_freshness(rows)
        by_symbol: dict[str, dict[str, Any]] = {}
        for row in rows:
            ticker = row["ticker"]
            providers = row.get("providers", {})
            router = providers.get("candle_router") or {}
            item = by_symbol.setdefault(ticker, {"symbol": ticker,
                "tier": row.get("data_quality", {}).get("watchlist_tier"),
                "valid_scans": 0, "stale_scans": 0, "primary_provider": None,
                "fallback_success": 0, "lags": []})
            if row.get("free_validation_eligible"):
                item["valid_scans"] += 1
            else:
                item["stale_scans"] += 1
            item["primary_provider"] = item["primary_provider"] or router.get("selected_candle_provider") or providers.get("price")
            item["fallback_success"] += int(bool(router.get("fallback_used") and row.get("free_validation_eligible")))
            lag = router.get("candle_age_seconds") or providers.get("price_freshness_seconds")
            if lag is not None:
                item["lags"].append(float(lag))
        table_rows = []
        for item in sorted(by_symbol.values(), key=lambda value: value["symbol"]):
            lags = item.pop("lags")
            item["avg_lag"] = round(sum(lags)/len(lags), 2) if lags else 0
            item["p95_lag"] = round(sorted(lags)[max(0, int(len(lags)*.95)-1)], 2) if lags else 0
            total = item["valid_scans"] + item["stale_scans"]
            item["reliability"] = round(item["valid_scans"]/total, 4) if total else 0
            table_rows.append(item)
        output_dir = (self.artifact_root / "reports" / report_date)
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "provider_freshness_report.md"
        lines = "\n".join(
            f"| {row['symbol']} | {row.get('tier') or 'unknown'} | {row['valid_scans']} | "
            f"{row['stale_scans']} | {row.get('primary_provider') or 'None'} | "
            f"{row['fallback_success']} | {row['avg_lag']} | {row['p95_lag']} | {row['reliability']} |"
            for row in table_rows) or "| - | - | 0 | 0 | - | 0 | 0 | 0 | 0 |"
        markdown = f"""# Provider Freshness Report - {report_date}

Generated: {datetime.now(timezone.utc).isoformat()}

This report measures free candle-data usability only. It does not change strategy logic, gates, weights, stops, targets, sizing, or lane rules.

## Summary

- Valid scans by candle provider: {json.dumps(summary['valid_scans_by_candle_provider'], sort_keys=True)}
- Average candle publication lag: {summary['average_candle_publication_lag']} seconds
- Median/P95/max lag: {summary['median_publication_lag']} / {summary['p95_publication_lag']} / {summary['maximum_lag']} seconds
- Fallback success rate: {summary['fallback_success_rate']}
- Cross-provider conflicts: {self.market_data_freshness_status()['metrics'].get('cross_provider_conflicts', 0)}

## Symbol Reliability

| symbol | tier | valid_scans | stale_scans | primary_provider | fallback_success | avg_lag | p95_lag | reliability |
|---|---|---:|---:|---|---:|---:|---:|---:|
{lines}

## Recommendation

Keep Yahoo as the bulk OHLCV source, Finnhub as quote freshness confirmation, and Alpha Vantage as a Tier 1 fallback only until a larger real-time sample proves a better free priority order.
"""
        path.write_text(markdown, encoding="utf-8")
        return {"report": {"report_date": report_date, "summary": summary, "symbols": table_rows},
                "markdown_path": str(path)}

    def phase2d_report(self) -> dict[str, Any]:
        return self.phase2d_reports.generate(
            self.watchlist, self.scheduler_status(), self.source_status(),
            {"total": int(self.settings.get("observation.target_phase2d_free_validation_scans", 500)),
             "tier1": int(self.settings.get("observation.target_phase2d_tier1_scans", 50)),
             "symbols": int(self.settings.get("observation.target_phase2d_valid_symbols", 20))})

    def process_scan_input(self, scan: ScanInput, open_paper: bool = False) -> tuple[SetupEvent | None, PaperTrade | None]:
        if scan.guard is None:
            scan.guard = self.guard.evaluate(scan.ticker_state.ticker, scan.confirmation_bar.bar_end_utc)
        setup = self.detector.detect(scan)
        if not setup:
            self.repository.store_audit("setup_evaluation", "no_setup", ["Reclaim pattern not detected"],
                                        scan.model_dump(mode="json"), scan.ticker_state.ticker)
            return None, None
        setup.signal_snapshot["reclaim_event_key"] = self._reclaim_event_key_from_setup(setup)
        if self._duplicate_setup_exists(setup):
            self.repository.store_audit(
                "setup_evaluation", "duplicate_setup_suppressed",
                ["Duplicate reclaim setup suppressed for same symbol, side, level, and completed candle"],
                {"reclaim_event_key": setup.signal_snapshot["reclaim_event_key"],
                 "source_mode": setup.source_mode, "score": setup.score.total},
                setup.ticker, "INFO")
            return None, None
        self.repository.store_setup(setup)
        self.forward_management_ab.create_for_setup(setup)
        self.forward_edge_validation.register_setup(setup)
        self.repository.store_audit(
            "setup_evaluation",
            setup.recommended_mode.value,
            setup.blocking_reasons,
            {"setup_event_id": setup.setup_event_id, "source_mode": setup.source_mode,
             "score": setup.score.total, "production_paper_allowed": setup.production_paper_allowed,
             "free_validation_paper_allowed": setup.free_validation_paper_allowed,
             "recommended_mode": setup.recommended_mode.value},
            setup.ticker,
            "WARNING" if setup.blocking_reasons else "INFO",
        )
        self.variants.record(setup, self.scorer.ablation_weight_sets())
        trade = None
        if open_paper and setup.trade_plan:
            mode = setup.recommended_mode
            trade = self.broker.accept(setup, mode)
            if mode == Mode.PRODUCTION:
                self.alerts.send(format_production_alert(setup, trade))
        return setup, trade

    def evaluate_normalized_payload(self, payload: dict[str, Any], open_paper: bool = False) -> dict[str, Any]:
        try:
            scan = ScanInput.model_validate(payload)
        except ValidationError as exc:
            reasons = [f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" for error in exc.errors()]
            event_id = self.repository.store_audit("normalized_input_rejected", "rejected", reasons,
                                                   {"provided_fields": sorted(payload)}, payload.get("ticker"), "ERROR")
            return {"status": "rejected", "audit_event_id": event_id, "reasons": reasons}
        setup, trade = self.process_scan_input(scan, open_paper)
        return {"status": "evaluated", "setup": setup.model_dump(mode="json") if setup else None,
                "trade": trade.model_dump(mode="json") if trade else None}

    def scan_once(self, request: ScanRequest) -> dict[str, Any]:
        tickers = [ticker.upper() for ticker in (request.tickers or self.watchlist.symbols())]
        results, errors = [], []
        if not request.fixture:
            observation = self.run_observation(ObservationRequest(tickers=tickers, cycles=1, interval_seconds=0,
                                                                  open_paper=request.open_paper,
                                                                  include_free_fallback=True))
            return {"status": "completed", "data_mode": "REAL", "production_eligible": None,
                    "scanned": observation["scan_count"],
                    "setups": len([row for row in observation["results"] if row.get("setup")]),
                    "run_id": observation["run_id"], "outcomes": observation["outcomes"],
                    "results": observation["results"], "errors": []}
        common_now = datetime.now(timezone.utc)
        for ticker in tickers:
            try:
                setup, trade = self.process_scan_input(self.fixture_scan_input(ticker, common_now), request.open_paper)
                results.append({"ticker": ticker, "setup": setup.model_dump(mode="json") if setup else None,
                                "trade": trade.model_dump(mode="json") if trade else None})
            except Exception as exc:
                errors.append({"ticker": ticker, "error": str(exc)})
        return {"status": "completed", "data_mode": "DEMO_FIXTURE", "production_eligible": False,
                "scanned": len(tickers), "setups": len([row for row in results if row["setup"]]),
                "results": results, "errors": errors}

    def accept_setup(self, setup_id: str) -> PaperTrade:
        payload = self.repository.get_setup(setup_id)
        if not payload:
            raise KeyError(setup_id)
        setup = SetupEvent.model_validate(payload)
        trade = self.broker.accept(setup)
        if trade.mode == Mode.PRODUCTION:
            self.alerts.send(format_production_alert(setup, trade))
        return trade

    def ticker_map(self, ticker: str) -> dict[str, Any]:
        ticker = ticker.upper()
        levels = self.repository.list_json("option_levels", "WHERE ticker=?", (ticker,))
        setups = self.repository.list_json("setup_events", "WHERE ticker=?", (ticker,), limit=20)
        return {"ticker": ticker, "levels": levels, "latest_setup": setups[0] if setups else None,
                "source_status": self.source_status(), "guard": self.guard.evaluate(ticker, datetime.now(timezone.utc))}

    def replay_snapshots(self, request: ReplayRequest) -> dict[str, Any]:
        result = self.replay.run(request)
        if request.open_paper:
            for payload in result["setups"]:
                setup = SetupEvent.model_validate(payload)
                self.repository.store_setup(setup)
                if setup.trade_plan:
                    self.broker.accept(setup, setup.recommended_mode)
        return result
