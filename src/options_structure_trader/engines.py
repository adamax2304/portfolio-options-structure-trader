from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from .config import Settings
from .models import (Bar, FeatureSet, GexMap, GuardStatus, Level, MacroEvent, ScanInput,
                     Mode, ScoreResult, SetupEvent, SetupType, Side, TradePlan)


class LevelEngine:
    def __init__(self, settings: Settings):
        self.settings = settings

    @staticmethod
    def zone_width(spot: float, atr_15m: float, spread: float, source_uncertainty: float = 0) -> float:
        return max(0.20 * atr_15m, 0.001 * spot, spread * 2, source_uncertainty)

    def from_gex(self, gex: GexMap, atr_15m: float, spread: float) -> list[Level]:
        values: list[tuple[str, float | None, float]] = [
            ("GAMMA_FLIP", gex.gamma_flip, 1.0), ("CALL_WALL", gex.call_wall, .9),
            ("PUT_WALL", gex.put_wall, .9), ("MAX_PAIN", gex.max_pain, .6),
        ]
        values.extend(("GEX_NODE", row["strike"], min(1, abs(row.get("net_gex", 0)) / 10)) for row in gex.strikes)
        values.extend(("OI_NODE", node, .7) for node in gex.oi_nodes)
        levels: list[Level] = []
        for level_type, price, strength in values:
            if price is None:
                continue
            width = self.zone_width(gex.spot, atr_15m, spread, source_uncertainty=gex.spot * .00025)
            levels.append(Level(ticker=gex.ticker, level_type=level_type, price=float(price),
                                zone_low=float(price) - width, zone_high=float(price) + width,
                                known_at_utc=gex.source_timestamp_utc, source=gex.source,
                                strength_score=strength, freshness_score=max(0, 1 - gex.freshness_seconds / 1800)))
        return levels

    def conflict(self, maps: list[GexMap], atr_15m: float) -> tuple[bool, str | None]:
        flips = [item.gamma_flip for item in maps if item.gamma_flip is not None]
        if len(flips) < 2:
            return False, None
        spot = sum(item.spot for item in maps) / len(maps)
        threshold = max(self.settings.get("freshness.conflict_pct_of_spot", .01) * spot,
                        self.settings.get("freshness.conflict_atr_multiplier", .5) * atr_15m)
        conflict = max(flips) - min(flips) > threshold
        return conflict, f"Gamma flips differ by {max(flips)-min(flips):.2f}, threshold {threshold:.2f}" if conflict else None


class MacroEventGuard:
    def __init__(self, settings: Settings, events: list[MacroEvent], calendar_approved: bool = False):
        self.settings = settings
        self.events = sorted(events, key=lambda event: event.event_time_utc)
        self.calendar_approved = calendar_approved

    def evaluate(self, ticker: str, at: datetime) -> GuardStatus:
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        if not self.settings.get("macro_event_guard.enabled", True):
            return GuardStatus(ticker=ticker, evaluated_at_utc=at, blocked=False,
                               macro_unknown=not self.calendar_approved, calendar_approved=self.calendar_approved)
        closest: tuple[float, MacroEvent, float, float] | None = None
        reasons: list[str] = []
        for event in self.events:
            if event.scope == "ticker" and ticker.upper() not in event.tickers:
                continue
            delta_minutes = (event.event_time_utc - at).total_seconds() / 60
            if event.block_before_minutes is not None:
                before = event.block_before_minutes
            elif event.importance == "high":
                before = self.settings.get("macro_event_guard.high_impact_block_before_minutes", 60)
            else:
                before = self.settings.get("macro_event_guard.medium_impact_block_before_minutes", 15)
            if event.block_after_minutes is not None:
                after = event.block_after_minutes
            elif event.importance == "high":
                after = self.settings.get("macro_event_guard.high_impact_block_after_minutes", 30)
            else:
                after = self.settings.get("macro_event_guard.medium_impact_block_after_minutes", 10)
            if -after <= delta_minutes <= before:
                reasons.append(f"{event.event_name} event window ({delta_minutes:+.0f} minutes)")
                distance = abs(delta_minutes)
                if closest is None or distance < closest[0]:
                    closest = (distance, event, delta_minutes, -delta_minutes)
        if closest:
            _, event, to_event, since_event = closest
            return GuardStatus(ticker=ticker, evaluated_at_utc=at, blocked=True, event_name=event.event_name,
                               event_time_utc=event.event_time_utc, minutes_to_event=to_event if to_event >= 0 else None,
                               minutes_since_event=since_event if since_event >= 0 else None,
                               macro_event_proximity_flag=True, blocking_reasons=reasons,
                               macro_unknown=not self.calendar_approved, calendar_approved=self.calendar_approved)
        return GuardStatus(ticker=ticker, evaluated_at_utc=at, blocked=False,
                           macro_unknown=not self.calendar_approved, calendar_approved=self.calendar_approved)


class ConfluenceEngine:
    def __init__(self, settings: Settings):
        self.settings = settings

    def score(self, features: FeatureSet, weight_set_id: str = "baseline_full",
              weights: dict[str, float] | None = None, confidence_score: float = 1.0,
              data_quality_tier: str = "FULL") -> ScoreResult:
        weights = weights or self.settings.get("scores.weights")
        components = features.model_dump(include=set(weights))
        missing = [name for name in weights if components.get(name) is None and float(weights[name]) > 0]
        available_weight = sum(float(weight) for name, weight in weights.items() if components.get(name) is not None)
        raw_parts = {name: (float(components[name]) * float(weight) * 100 / available_weight
                            if components.get(name) is not None and available_weight else None)
                     for name, weight in weights.items()}
        raw_score = round(sum(value for value in raw_parts.values() if value is not None), 2)
        floor = float(self.settings.get("scores.missing_data_adjustment_floor", .75))
        adjustment = 1.0 if not missing else floor + (1-floor) * max(0, min(1, confidence_score))
        adjusted_score = round(raw_score * adjustment, 2)
        breakdown = {name: (round(value * adjustment, 4) if value is not None else None)
                     for name, value in raw_parts.items()}
        version = self.settings.get("scores.active_score_model", "score_v0_baseline_manual")
        if weight_set_id not in {"baseline_manual", "baseline_full"}:
            version = f"{version}:{weight_set_id}"
        return ScoreResult(total=adjusted_score, raw_score=raw_score, adjusted_score=adjusted_score,
                           confidence_score=confidence_score, missing_components=missing,
                           data_quality_tier=data_quality_tier, breakdown=breakdown,
                           raw_components={key: (float(value) if value is not None else None)
                                           for key, value in components.items()},
                           score_model_version=version, score_weight_set_id=weight_set_id)

    def ablation_weight_sets(self) -> dict[str, dict[str, float]]:
        base = {k: float(v) for k, v in self.settings.get("scores.weights").items()}
        names = list(base)
        equal = {name: 100 / len(names) for name in names}
        price_only = {name: (100 if name == "price_structure" else 0) for name in names}
        option_names = {"dealer_positioning", "options_flow", "oi_confirmation"}
        options_only = {name: (100 / len(option_names) if name in option_names else 0) for name in names}
        result = {"baseline_full": base, "baseline_manual": base, "equal_weight": equal, "price_action_only": price_only,
                  "options_only": options_only}
        for label, omitted in (("no_flow", "options_flow"), ("no_gex", "dealer_positioning"),
                               ("no_oi", "oi_confirmation"), ("no_dark_pool", "big_trades_dark_pool"),
                               ("no_macro_filter", "data_quality_event_guard")):
            active_total = sum(v for k, v in base.items() if k != omitted)
            result[label] = {k: (0 if k == omitted else v * 100 / active_total) for k, v in base.items()}
        free_gex_price = {name: (50 if name in {"dealer_positioning", "price_structure"} else 0) for name in names}
        free_gex_price_macro = {name: (40 if name in {"dealer_positioning", "price_structure"}
                                       else 20 if name == "data_quality_event_guard" else 0) for name in names}
        no_oi_no_greeks = {name: (0 if name == "oi_confirmation" else value) for name, value in base.items()}
        remaining = sum(no_oi_no_greeks.values())
        no_oi_no_greeks = {name: value*100/remaining for name, value in no_oi_no_greeks.items()}
        result.update({"free_gex_price_only": free_gex_price,
                       "free_gex_price_macro": free_gex_price_macro,
                       "no_oi_no_greeks": no_oi_no_greeks,
                       "price_only_shadow": price_only})
        return result


class LaneEligibilityClassifier:
    """One source of truth for data-lane eligibility before setup-specific gates."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def free_blockers(self, scan: ScanInput) -> list[str]:
        value, guard = scan.eligibility, scan.guard
        if value is None:
            return ["Free Validation eligibility context is missing"]
        blockers: list[str] = []
        if not value.real_data:
            blockers.append("Free Validation requires real normalized data")
        if value.synthetic_present:
            blockers.append("Synthetic data cannot enter Free Validation Paper")
        if not value.supported_ticker:
            blockers.append("Ticker is not in the supported Free Validation watchlist")
        free_session_valid = (value.session_valid if value.free_validation_session_valid is None
                              else value.free_validation_session_valid)
        if not free_session_valid:
            blockers.append("US regular session is required for Free Validation")
        if not value.macro_guard_evaluated:
            blockers.append("Macro Event Guard was not evaluated")
        if value.macro_unknown and not self.settings.get("sources.macro_calendar.free_validation_allow_unknown", True):
            blockers.append("Macro calendar is unknown for Free Validation")
        if not value.core_fields_complete:
            blockers.append("Core reclaim fields are incomplete")
        if not value.price_provider_free_validation_eligible:
            blockers.append(f"Price provider {value.price_provider} is not Free-Validation-eligible")
        if not value.structure_provider_free_validation_eligible:
            blockers.append(f"Structure provider {value.structure_provider} is not Free-Validation-eligible")
        if value.price_freshness_seconds > self.settings.get("freshness.free_validation_price_max_seconds", 420):
            blockers.append("Price/candle data exceeds Free Validation freshness threshold")
        if value.structure_freshness_seconds > self.settings.get("freshness.free_validation_gex_max_seconds", 1200):
            blockers.append("Options-structure data exceeds Free Validation freshness threshold")
        if value.confidence_score < self.settings.get("scores.free_validation_min_confidence", .35):
            blockers.append("Data confidence is below the Free Validation floor")
        if scan.ticker_state.is_halted:
            blockers.append("Ticker is halted")
        if scan.features.source_conflict_flag:
            blockers.append("Options-structure sources conflict")
        if scan.features.data_staleness_flag:
            blockers.append("Critical market data is stale")
        if guard and guard.blocked:
            blockers.extend(guard.blocking_reasons)
        return list(dict.fromkeys(blockers))

    def production_blockers(self, scan: ScanInput) -> list[str]:
        value, guard = scan.eligibility, scan.guard
        if value is None:
            return ["Production eligibility context is missing"]
        blockers: list[str] = []
        if not value.real_data:
            blockers.append("Production Paper requires real normalized data")
        if value.synthetic_present:
            blockers.append("Synthetic data cannot enter Production Paper")
        if not value.supported_ticker:
            blockers.append("Ticker is not in the supported Production watchlist")
        if not value.session_valid:
            blockers.append("Session state is not valid for Production Paper")
        if not value.macro_guard_evaluated:
            blockers.append("Macro Event Guard was not evaluated")
        if not value.macro_calendar_production_eligible or value.macro_unknown:
            blockers.append("Macro calendar is not approved for Production Paper")
        if not value.required_fields_complete:
            blockers.append("Required normalized fields are incomplete")
        if not value.price_provider_production_eligible:
            blockers.append(f"Price provider {value.price_provider} is not Production-eligible")
        if not value.structure_provider_production_eligible:
            blockers.append(f"Structure provider {value.structure_provider} is not Production-eligible")
        if value.unofficial_source:
            blockers.append("Unofficial-only data cannot enter Production Paper")
        if value.price_freshness_seconds > self.settings.get("freshness.price_max_seconds", 120):
            blockers.append("Price/candle data exceeds freshness threshold")
        if value.structure_freshness_seconds > self.settings.get("freshness.gex_max_seconds", 1200):
            blockers.append("Options-structure data exceeds freshness threshold")
        if value.confidence_score < self.settings.get("scores.production_min_confidence", .8):
            blockers.append("Data confidence is below the Production Paper floor")
        if scan.ticker_state.is_halted:
            blockers.append("Ticker is halted")
        if scan.features.data_staleness_flag:
            blockers.append("Critical market data is stale")
        if scan.features.source_conflict_flag:
            blockers.append("Options-structure sources conflict")
        if guard and guard.blocked:
            blockers.extend(guard.blocking_reasons)
        return list(dict.fromkeys(blockers))

    def classify(self, scan: ScanInput) -> tuple[Mode, list[str], list[str]]:
        free, production = self.free_blockers(scan), self.production_blockers(scan)
        if not production:
            return Mode.PRODUCTION, free, production
        if not free:
            return Mode.FREE_VALIDATION, free, production
        return Mode.SHADOW, free, production


class TradeConstructor:
    def __init__(self, settings: Settings):
        self.settings = settings

    def construct(self, scan: ScanInput, side: Side, stop_buffer_multiplier: float | None = None) -> tuple[TradePlan | None, list[str]]:
        state, level, bar = scan.ticker_state, scan.level, scan.confirmation_bar
        spread = max(0, state.ask - state.bid)
        multiplier = stop_buffer_multiplier or self.settings.get("stops.baseline_atr_buffer", .3)
        buffer = max(bar.atr * multiplier, spread * self.settings.get("stops.spread_multiplier", 2),
                     self.settings.get("stops.minimum_tick_buffer", .01))
        if side == Side.LONG:
            entry = max(level.zone_high, bar.close)
            entry_high = entry + min(bar.atr * .25, max(spread * 2, .01))
            stop = min(scan.previous_bar.low, bar.low, level.zone_low) - buffer
            targets = sorted({float(node) for node in scan.target_nodes if node > entry})[:3]
            invalidation = f"5m close below {stop:.2f} or loss of reclaimed {level.level_type} zone"
        else:
            entry = min(level.zone_low, bar.close)
            entry_high = entry
            entry_low = entry - min(bar.atr * .25, max(spread * 2, .01))
            stop = max(scan.previous_bar.high, bar.high, level.zone_high) + buffer
            targets = sorted({float(node) for node in scan.target_nodes if node < entry}, reverse=True)[:3]
            invalidation = f"5m close above {stop:.2f} or reclaim of lost {level.level_type} zone"
        reasons: list[str] = []
        risk_per_share = abs(entry - stop)
        if risk_per_share <= max(spread, 0):
            reasons.append("Stop is inside spread/noise")
        if risk_per_share > bar.atr * self.settings.get("risk.max_stop_atr", 3):
            reasons.append("Stop distance exceeds configured ATR limit")
        if not targets:
            reasons.append("No structure target in trade direction")
            return None, reasons
        rr = abs(targets[0] - entry) / risk_per_share if risk_per_share else 0
        if rr < self.settings.get("risk.min_primary_RR", 1.8):
            reasons.append(f"Primary R:R {rr:.2f} is below minimum")
        risk_dollars = self.settings.get("risk.paper_equity", 100000) * self.settings.get("risk.base_risk_per_trade", .0025)
        shares = math.floor(risk_dollars / risk_per_share) if risk_per_share else 0
        if shares < self.settings.get("risk.minimum_shares", 1):
            reasons.append("Position size is below minimum")
        while len(targets) < 3:
            targets.append(targets[-1] + (risk_per_share if side == Side.LONG else -risk_per_share))
        plan = TradePlan(entry_zone_low=entry if side == Side.LONG else entry_low,
                         entry_zone_high=entry_high, planned_entry=entry, stop_initial=round(stop, 4),
                         targets=[round(value, 4) for value in targets], primary_rr=round(rr, 3), shares=shares,
                         risk_dollars=round(shares * risk_per_share, 2), invalidation_logic=invalidation)
        return plan, reasons


class ReclaimSetupDetector:
    VALID_LEVELS = {"GAMMA_FLIP", "GEX_NODE", "OI_NODE", "PUT_WALL", "CALL_WALL", "DARK_POOL", "VWAP_CONFLUENCE"}

    def __init__(self, settings: Settings, scorer: ConfluenceEngine, constructor: TradeConstructor):
        self.settings, self.scorer, self.constructor = settings, scorer, constructor
        self.classifier = LaneEligibilityClassifier(settings)

    def detect(self, scan: ScanInput, at: datetime | None = None) -> SetupEvent | None:
        level, prev, bar = scan.level, scan.previous_bar, scan.confirmation_bar
        at = at or bar.bar_end_utc
        if level.level_type not in self.VALID_LEVELS or level.known_at_utc >= bar.bar_start_utc:
            return None
        if not bar.closed or bar.timeframe != self.settings.get("entry.entry_tf", "5m"):
            return None
        long_pattern = min(prev.low, bar.low) < level.zone_low and bar.close > level.zone_high
        short_pattern = max(prev.high, bar.high) > level.zone_high and bar.close < level.zone_low
        if not long_pattern and not short_pattern:
            return None
        side = Side.LONG if long_pattern else Side.SHORT
        setup_type = SetupType.LEVEL_RECLAIM_LONG if long_pattern else SetupType.LEVEL_RECLAIM_SHORT
        options_flow = scan.features.options_flow
        dealer = scan.features.dealer_positioning
        oi = scan.features.oi_confirmation
        directional = ((options_flow is not None and options_flow >= .55)
                       or (dealer is not None and dealer >= .65) or (oi is not None and oi >= .65))
        opposite_flow = bool(options_flow is not None and
            ((side == Side.LONG and scan.features.flow_direction == "bearish" and options_flow < .25)
             or (side == Side.SHORT and scan.features.flow_direction == "bullish" and options_flow < .25)))
        eligibility = scan.eligibility
        quality_tier = "PRODUCTION_FULL" if eligibility and eligibility.production_grade else (
            "FREE_LIMITED" if eligibility and eligibility.real_data else "SHADOW")
        confidence = eligibility.confidence_score if eligibility else 0
        score = self.scorer.score(scan.features, "baseline_full", confidence_score=confidence,
                                  data_quality_tier=quality_tier)
        plan, plan_blockers = self.constructor.construct(scan, side)
        free_blockers = self.classifier.free_blockers(scan)
        production_blockers = self.classifier.production_blockers(scan)
        if not directional:
            plan_blockers.append("Directional flow or GEX/OI confirmation is insufficient")
        if opposite_flow:
            plan_blockers.append("Options flow is clearly opposite")
        free_blockers.extend(plan_blockers)
        production_blockers.extend(plan_blockers)
        if score.total < self.settings.get("scores.free_validation_threshold", 60):
            free_blockers.append(f"Adjusted score {score.total:.0f} is below Free Validation threshold")
        if score.total < self.settings.get("scores.production_threshold", 75):
            production_blockers.append(f"Adjusted score {score.total:.0f} is below Production threshold")
        if scan.source_mode == "DEMO_FIXTURE" and not self.settings.get("scanner.production_from_fixture", False):
            production_blockers.append("Synthetic fixture data cannot enter Production Paper")
            free_blockers.append("Synthetic fixture data cannot enter Free Validation Paper")
        free_blockers = list(dict.fromkeys(free_blockers))
        production_blockers = list(dict.fromkeys(production_blockers))
        recommended = Mode.PRODUCTION if plan and not production_blockers else (
            Mode.FREE_VALIDATION if plan and not free_blockers else Mode.SHADOW)
        state, guard = scan.ticker_state, scan.guard
        reason = [f"{side.value.title()} 5m closed-candle reclaim of {level.level_type}",
                  f"Level existed before reaction ({level.known_at_utc.isoformat()})",
                  f"Deterministic adjusted confluence score {score.total:.0f}/100"]
        if scan.features.volume_expansion:
            reason.append("Volume expanded versus baseline")
        if guard and not guard.blocked:
            reason.append("Macro Event Guard clear")
        snapshot = {"schema_version": "signal_snapshot.v1", "captured_at_utc": at.isoformat(),
                    "source_timestamp_utc": level.known_at_utc.isoformat(),
                    "ingestion_timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "ticker_state": state.model_dump(mode="json"), "level": level.model_dump(mode="json"),
                    "previous_bar": prev.model_dump(mode="json"), "confirmation_bar": bar.model_dump(mode="json"),
                    "features": scan.features.model_dump(mode="json"),
                    "eligibility": eligibility.model_dump(mode="json") if eligibility else None,
                    "guard": guard.model_dump(mode="json") if guard else None, "target_nodes": scan.target_nodes}
        return SetupEvent(ticker=state.ticker, setup_type=setup_type, side=side, level_id=level.level_id,
                          level_type=level.level_type, created_at_utc=at, score=score, trade_plan=plan,
                          production_paper_allowed=bool(plan and not production_blockers),
                          free_validation_paper_allowed=bool(plan and not free_blockers), shadow_paper_allowed=True,
                          blocking_reasons=production_blockers,
                          free_validation_blocking_reasons=free_blockers, recommended_mode=recommended, reason=reason,
                          config_version=self.settings.version, source_mode=scan.source_mode, signal_snapshot=snapshot)
