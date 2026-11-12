from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any
from zoneinfo import ZoneInfo

from .db import Repository
from .models import Bar, EligibilityContext, GexMap, GuardStatus, Level, SetupEvent, TickerState, new_id


EASTERN = ZoneInfo("America/New_York")


class MultiTimeframeOptionsEdgeResearch:
    """Research-only forward event/branch tracker for Phase 4A.

    This class deliberately does not create canonical setup_events, paper_trades,
    alerts, live orders, or provider requests. It records separate parent market
    events and simulated research branches from scans the live daemon already
    normalized and gated.
    """

    PHASE_ID = "phase_4a_multitimeframe_intraday_options_edge"
    PHASE4B2_ID = "phase_4b2_prospective_execution_options_value"
    LEVEL_SCORE_VERSION = "level_strength_score_v1_research_only"
    BRANCH_MATRIX_VERSION = "phase4a_focused_forward_matrix_v2"
    PHASE4B2_BRANCH_MATRIX_VERSION = "phase4b2_execution_options_value_v2"
    QA_INTEGRITY_VERSION = "phase4b2_research_event_integrity_v1"
    ACCOUNTING_INTEGRITY_VERSION = "phase4b3_no_fill_accounting_v2"
    FORWARD_INSTRUMENTATION_VERSION = "phase4b3_forward_instrumentation_v3"

    VARIANT_SPECS: dict[str, dict[str, Any]] = {
        "VARIANT_A_5M_BASELINE": {
            "variant_letter": "A",
            "timeframe_context": "5m",
            "confirmation_tf": "5m",
            "execution_tf": "5m",
            "requires_persistent_level": False,
            "requires_15m_confirmation": False,
            "requires_30m_context": False,
            "requires_1m_entry": False,
        },
        "VARIANT_B_15M_CONFIRM_5M_ENTRY": {
            "variant_letter": "B",
            "timeframe_context": "15m",
            "confirmation_tf": "15m",
            "execution_tf": "5m",
            "requires_persistent_level": False,
            "requires_15m_confirmation": True,
            "requires_30m_context": False,
            "requires_1m_entry": False,
        },
        "VARIANT_C_PERSISTENT_5M": {
            "variant_letter": "C",
            "timeframe_context": "5m_persistent",
            "confirmation_tf": "5m",
            "execution_tf": "5m",
            "requires_persistent_level": True,
            "requires_15m_confirmation": False,
            "requires_30m_context": False,
            "requires_1m_entry": False,
        },
        "VARIANT_D_PERSISTENT_15M_5M": {
            "variant_letter": "D",
            "timeframe_context": "15m_persistent",
            "confirmation_tf": "15m",
            "execution_tf": "5m",
            "requires_persistent_level": True,
            "requires_15m_confirmation": True,
            "requires_30m_context": False,
            "requires_1m_entry": False,
        },
        "VARIANT_E_30M_CONTEXT_15M_SETUP_5M_ENTRY": {
            "variant_letter": "E",
            "timeframe_context": "30m_context",
            "confirmation_tf": "15m",
            "execution_tf": "5m",
            "requires_persistent_level": True,
            "requires_15m_confirmation": True,
            "requires_30m_context": True,
            "requires_1m_entry": False,
        },
        "VARIANT_F_15M_SETUP_1M_ENTRY": {
            "variant_letter": "F",
            "timeframe_context": "15m_1m_execution",
            "confirmation_tf": "15m",
            "execution_tf": "1m",
            "requires_persistent_level": False,
            "requires_15m_confirmation": True,
            "requires_30m_context": False,
            "requires_1m_entry": True,
        },
        "VARIANT_G_5M_SETUP_1M_ENTRY": {
            "variant_letter": "G",
            "timeframe_context": "5m_1m_execution",
            "confirmation_tf": "5m",
            "execution_tf": "1m",
            "requires_persistent_level": False,
            "requires_15m_confirmation": False,
            "requires_30m_context": False,
            "requires_1m_entry": True,
        },
    }

    ENTRY_VARIANTS: dict[str, str] = {
        "ENTRY_1": "close_reclaim_or_acceptance",
        "ENTRY_2": "reclaim_plus_retest",
        "ENTRY_3": "sweep_reclaim_plus_retest",
        "ENTRY_4": "reclaim_plus_volume_confirmation",
        "ENTRY_5": "reclaim_plus_market_alignment",
    }

    MANAGEMENT_VARIANTS = (
        "TM_V0_CURRENT",
        "TM_V3_TP1_PLUS_RUNNER",
        "TM_FIXED_0_5R",
        "TM_FIXED_1R",
        "TM_FIXED_1_5R",
        "TM_FIXED_2R",
        "TM_HALF_0_5R_RUNNER",
        "TM_HALF_1R_RUNNER",
        "TM_STRUCTURE_TARGETS",
    )

    PHASE4B2_MANAGEMENT_VARIANTS = (
        "M0_CURRENT_MANAGEMENT",
        "M1_HALF_0_5R_RUNNER",
        "M2_HALF_0_7R_RUNNER",
        "M3_PROTECT_AFTER_1R_NO_PARTIAL",
        "M4_STRUCTURE_TRAIL_NO_IMMEDIATE_BE",
    )

    CORE_MANAGEMENT_VARIANTS = ("TM_V0_CURRENT", "TM_V3_TP1_PLUS_RUNNER")

    STOP_VARIANTS: dict[str, float | None] = {
        "STOP_A_CURRENT_STRUCTURAL": None,
        "STOP_B_STRUCTURE_PLUS_0_15_ATR": 0.15,
        "STOP_C_STRUCTURE_PLUS_0_30_ATR": 0.30,
        "STOP_D_STRUCTURE_PLUS_0_50_ATR": 0.50,
        "STOP_E_LEVEL_ZONE_INVALIDATION": 0.0,
    }

    PHASE4B2_STOP_VARIANTS: dict[str, float | None] = {
        "S0_CANONICAL_STOP": None,
        "S1_FULL_OPTIONS_LEVEL_ZONE_INVALIDATION": 0.0,
        # S2/S3 are intentionally not ATR proxies.  Their actual prices are
        # derived from confirmed, completed-bar structure for each event.
        "S2_15M_STRUCTURAL_INVALIDATION": None,
        "S3_LAST_CONFIRMED_HL_LH_INVALIDATION": None,
    }

    PHASE4B2_VARIANT_SPECS: dict[str, dict[str, Any]] = {
        "P4B2_E1_INVALIDATION_STOP": {
            "timeframe_context": "canonical_event",
            "confirmation_tf": "canonical",
            "execution_tf": "canonical",
            "requires_persistent_level": False,
            "requires_15m_confirmation": False,
            "requires_30m_context": False,
            "requires_1m_entry": False,
        },
        "P4B2_E2_PROFIT_PROTECTION": {
            "timeframe_context": "canonical_event",
            "confirmation_tf": "canonical",
            "execution_tf": "canonical",
            "requires_persistent_level": False,
            "requires_15m_confirmation": False,
            "requires_30m_context": False,
            "requires_1m_entry": False,
        },
        "P4B2_E3_OPTIONS_VALUE_P0_STRUCTURE_ONLY": {
            "timeframe_context": "price_structure_only",
            "confirmation_tf": "5m",
            "execution_tf": "5m",
            "requires_persistent_level": False,
            "requires_15m_confirmation": False,
            "requires_30m_context": False,
            "requires_1m_entry": False,
            "requires_price_structure": True,
        },
        "P4B2_E3_OPTIONS_VALUE_P1_STRUCTURE_PLUS_STRONG_OPTIONS": {
            "timeframe_context": "price_structure_plus_options",
            "confirmation_tf": "5m",
            "execution_tf": "5m",
            "requires_strong_level": True,
            "requires_persistent_level": False,
            "requires_15m_confirmation": False,
            "requires_30m_context": False,
            "requires_1m_entry": False,
            "requires_price_structure": True,
        },
        "P4B2_E3_OPTIONS_VALUE_P2_PERSISTENT_OPTIONS": {
            "timeframe_context": "price_structure_plus_persistent_options",
            "confirmation_tf": "5m",
            "execution_tf": "5m",
            "requires_strong_level": True,
            "requires_persistent_level": True,
            "requires_15m_confirmation": False,
            "requires_30m_context": False,
            "requires_1m_entry": False,
            "requires_price_structure": True,
        },
        "P4B2_E3_OPTIONS_VALUE_P3_DIRECTION_CLASSIFIER": {
            "timeframe_context": "options_direction_classifier",
            "confirmation_tf": "5m",
            "execution_tf": "5m",
            "requires_strong_level": True,
            "requires_persistent_level": False,
            "requires_direction_classifier": True,
            "requires_15m_confirmation": False,
            "requires_30m_context": False,
            "requires_1m_entry": False,
            "requires_price_structure": True,
        },
        "P4B2_E3_OPTIONS_VALUE_P4_DIRECTION_15M_CONFIRM": {
            "timeframe_context": "options_direction_classifier_15m",
            "confirmation_tf": "15m",
            "execution_tf": "5m",
            "requires_strong_level": True,
            "requires_persistent_level": False,
            "requires_direction_classifier": True,
            "requires_15m_confirmation": True,
            "requires_30m_context": False,
            "requires_1m_entry": False,
            "requires_price_structure": True,
        },
    }

    CONTROL_VARIANTS = (
        "CONTROL_RANDOM_NEARBY_LEVEL",
        "CONTROL_PREVIOUS_DAY_HIGH",
        "CONTROL_PREVIOUS_DAY_LOW",
        "CONTROL_ROUND_NUMBER_LEVEL",
        "CONTROL_VWAP_INTERACTION",
        "CONTROL_RANDOM_CLUSTERED_PRICE_ZONE",
    )

    RESOLVED_STATUSES = {"closed", "censored"}
    ACTIVE_STATUSES = {"pending", "open", "partial"}

    def __init__(self, repository: Repository, settings: Any, watchlist: Any, output_root: Path):
        self.repository = repository
        self.settings = settings
        self.watchlist = watchlist
        self.output_root = output_root
        self.enabled = bool(settings.get("phase4a.enabled", True))
        self.level_score_version = str(settings.get("phase4a.level_strength_model_version", self.LEVEL_SCORE_VERSION))
        self.branch_matrix_version = str(settings.get("phase4a.branch_matrix_version", self.BRANCH_MATRIX_VERSION))
        self.cluster_widths = [float(value) for value in settings.get("phase4a.clustering_atr_widths", [0.10, 0.20, 0.30, 0.50])]
        self.default_cluster_width = float(settings.get("phase4a.default_cluster_atr_width", 0.30))
        self.minimum_persistence = int(settings.get("phase4a.minimum_persistence_snapshots", 3))
        self.episode_reset_bars = int(settings.get("phase4a.episode_reset_bars", 6))
        self.episode_reset_distance_atr = float(settings.get("phase4a.episode_reset_distance_atr", 0.25))
        self.tier_thresholds = settings.get("phase4a.strength_tiers", {"S": 0.85, "A": 0.70, "B": 0.55, "C": 0.0})
        self.phase4b2_enabled = bool(settings.get("phase4b2.enabled", True))
        if self.enabled:
            self.activate()
        if self.phase4b2_enabled:
            self.activate_phase4b2()

    @staticmethod
    def _stable_id(prefix: str, *parts: Any) -> str:
        digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:24]
        return f"{prefix}_{digest}"

    @staticmethod
    def _safe_float(value: Any, default: float | None = 0.0) -> float | None:
        try:
            if value is None:
                return default
            number = float(value)
            if math.isnan(number) or math.isinf(number):
                return default
            return number
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _parse_time(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None

    @staticmethod
    def _bar_dict(value: Bar | dict[str, Any]) -> dict[str, Any]:
        return value.model_dump(mode="json") if hasattr(value, "model_dump") else dict(value)

    @staticmethod
    def _level_dict(value: Level | dict[str, Any]) -> dict[str, Any]:
        return value.model_dump(mode="json") if hasattr(value, "model_dump") else dict(value)

    def activation(self) -> dict[str, Any] | None:
        rows = self.repository.list_json("phase4a_activation", "WHERE id=?", (self.PHASE_ID,), 1)
        return rows[0] if rows else None

    def activate(self, *, force: bool = False, activated_at: datetime | None = None) -> dict[str, Any]:
        existing = self.activation()
        if existing and not force:
            return existing
        now = activated_at or datetime.now(timezone.utc)
        record = {
            "id": self.PHASE_ID,
            "activated_at_utc": now.isoformat(),
            "discovery_cutoff_utc": now.isoformat(),
            "phase": "4A_MULTITIMEFRAME_INTRADAY_OPTIONS_LEVEL_EDGE_DISCOVERY",
            "strategy_state_source": "LIVE_INTRADAY_OPTIONS_RESEARCH_BRANCHES",
            "prospective_only": True,
            "research_only": True,
            "canonical_strategy_unchanged": True,
            "live_trading_disabled": True,
            "portfolio_os_isolated": True,
            "level_strength_model_version": self.level_score_version,
            "branch_matrix_version": self.branch_matrix_version,
            "accounting_integrity_version": self.ACCOUNTING_INTEGRITY_VERSION,
            "forward_instrumentation_version": self.FORWARD_INSTRUMENTATION_VERSION,
            "persistence_model_version": "snapshot_timestamp_horizons_v2",
            "timeframe_confirmation_version": "completed_15m_interaction_v1",
            "structural_invalidation_version": "confirmed_swing_2x2_completed_bars_v1",
            "prior_activation_cutoff_utc": existing.get("activated_at_utc") if existing else None,
            "clean_forward_cutoff_utc": now.isoformat(),
            "milestone_days": self.settings.get("phase4a.milestone_days", [5, 10, 20]),
        }
        self.repository.store_phase4a_activation(record)
        return record

    def phase4b2_activation(self) -> dict[str, Any] | None:
        rows = self.repository.list_json("phase4a_activation", "WHERE id=?", (self.PHASE4B2_ID,), 1)
        return rows[0] if rows else None

    def activate_phase4b2(self, *, force: bool = False, activated_at: datetime | None = None) -> dict[str, Any]:
        existing = self.phase4b2_activation()
        if existing and not force:
            return existing
        now = activated_at or datetime.now(timezone.utc)
        record = {
            "id": self.PHASE4B2_ID,
            "activated_at_utc": now.isoformat(),
            "discovery_cutoff_utc": now.isoformat(),
            "phase": "4B2_PROSPECTIVE_EXECUTION_OPTIONS_VALUE_VALIDATION",
            "strategy_state_source": "LIVE_INTRADAY_OPTIONS_RESEARCH_BRANCHES",
            "prospective_only": True,
            "research_only": True,
            "canonical_strategy_unchanged": True,
            "live_trading_disabled": True,
            "portfolio_os_isolated": True,
            "branch_matrix_version": self.PHASE4B2_BRANCH_MATRIX_VERSION,
            "accounting_integrity_version": self.ACCOUNTING_INTEGRITY_VERSION,
            "forward_instrumentation_version": self.FORWARD_INSTRUMENTATION_VERSION,
            "persistence_model_version": "snapshot_timestamp_horizons_v2",
            "timeframe_confirmation_version": "completed_15m_interaction_v1",
            "structural_invalidation_version": "confirmed_swing_2x2_completed_bars_v1",
            "prior_activation_cutoff_utc": existing.get("activated_at_utc") if existing else None,
            "clean_forward_cutoff_utc": now.isoformat(),
            "experiments": {
                "EXPERIMENT_1_INVALIDATION_STOP": list(self.PHASE4B2_STOP_VARIANTS),
                "EXPERIMENT_2_PROFIT_PROTECTION": list(self.PHASE4B2_MANAGEMENT_VARIANTS),
                "EXPERIMENT_3_OPTIONS_VALUE": [
                    name for name in self.PHASE4B2_VARIANT_SPECS if "E3_OPTIONS_VALUE" in name
                ],
            },
            "milestone_days": [5, 10, 20],
            "automatic_promotion": False,
        }
        self.repository.store_phase4a_activation(record)
        return record

    def _eligible(self, source_mode: str, eligibility: EligibilityContext | dict[str, Any] | None,
                  bar: dict[str, Any]) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        if not self.enabled:
            reasons.append("phase4a disabled")
        if not str(source_mode or "").startswith("REAL_"):
            reasons.append("non-real source mode is not eligible for Phase 4A forward research")
        if eligibility is not None:
            payload = eligibility.model_dump(mode="json") if hasattr(eligibility, "model_dump") else dict(eligibility)
            if not payload.get("real_data"):
                reasons.append("real_data=false")
            if payload.get("synthetic_present"):
                reasons.append("synthetic data is excluded")
            if not (payload.get("free_validation_session_valid") if payload.get("free_validation_session_valid") is not None else payload.get("session_valid")):
                reasons.append("session is not eligible for forward research")
        if not bar.get("closed", True):
            reasons.append("latest bar is not closed")
        activation = self.activate()
        activated_at = self._parse_time(activation.get("activated_at_utc"))
        bar_end = self._parse_time(bar.get("bar_end_utc"))
        if activated_at and bar_end and bar_end < activated_at:
            reasons.append("bar predates Phase 4A activation cutoff")
        return not reasons, reasons

    def _cluster_levels(self, levels: list[Level | dict[str, Any]], atr: float, width_atr: float) -> list[dict[str, Any]]:
        payloads = sorted([self._level_dict(level) for level in levels], key=lambda item: self._safe_float(item.get("price"), 0) or 0)
        if not payloads:
            return []
        width = max(0.01, atr * width_atr)
        clusters: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        last_price: float | None = None
        for level in payloads:
            price = self._safe_float(level.get("price"))
            if price is None:
                continue
            if current and last_price is not None and abs(price - last_price) > width:
                clusters.append(current)
                current = []
            current.append(level)
            last_price = price
        if current:
            clusters.append(current)
        result = []
        for items in clusters:
            weights = [max(0.01, self._safe_float(item.get("strength_score"), 0.5) or 0.5) for item in items]
            prices = [self._safe_float(item.get("price"), 0.0) or 0.0 for item in items]
            center = sum(price * weight for price, weight in zip(prices, weights)) / sum(weights)
            low = min(self._safe_float(item.get("zone_low"), item.get("price")) or center for item in items)
            high = max(self._safe_float(item.get("zone_high"), item.get("price")) or center for item in items)
            level_types = [str(item.get("level_type") or "UNKNOWN").upper() for item in items]
            primary_type = self._primary_level_type(level_types)
            component_signature = ",".join(
                f"{str(item.get('level_type') or 'UNKNOWN').upper()}:{round(self._safe_float(item.get('price'), 0.0) or 0.0, 4)}"
                for item in sorted(items, key=lambda item: (
                    str(item.get("level_type") or "UNKNOWN").upper(),
                    self._safe_float(item.get("price"), 0.0) or 0.0,
                ))
            )
            result.append({
                "cluster_id": self._stable_id("econlvl", items[0].get("ticker"), primary_type,
                                              round(center, 4), component_signature),
                "economic_level_cluster_id": self._stable_id("econlvl", items[0].get("ticker"), primary_type,
                                                             round(center, 4), component_signature),
                "cluster_center": round(center, 6),
                "cluster_low": round(low, 6),
                "cluster_high": round(high, 6),
                "width_atr": width_atr,
                "cluster_width_role": "ECONOMIC_PARENT_CLUSTER" if abs(width_atr - self.default_cluster_width) < 1e-9 else "RESEARCH_CLUSTER_VARIANT",
                "component_strikes": [round(price, 6) for price in prices],
                "component_level_ids": [item.get("level_id") for item in items],
                "component_level_types": level_types,
                "primary_level_type": primary_type,
                "combined_GEX": round(sum(self._safe_float((item.get("metadata") or {}).get("gex"), 0.0) or 0.0 for item in items), 6),
                "combined_OI": round(sum(self._safe_float((item.get("metadata") or {}).get("open_interest"), 0.0) or 0.0 for item in items), 6),
                "component_levels": items,
            })
        return result

    @staticmethod
    def _primary_level_type(level_types: list[str]) -> str:
        priority = ["GAMMA_FLIP", "CALL_WALL", "PUT_WALL", "GEX_OI_CLUSTER", "MULTI_LEVEL_CLUSTER", "GEX_NODE", "OI_NODE"]
        for item in priority:
            if item in level_types:
                return item
        return level_types[0] if level_types else "UNKNOWN"

    def _persistence(self, ticker: str, cluster: dict[str, Any], prior_levels: list[Level | dict[str, Any]],
                     atr: float, observed_at: datetime | None) -> dict[str, Any]:
        prior = [self._level_dict(item) for item in prior_levels]
        tolerance = max(0.01, atr * float(cluster.get("width_atr") or self.default_cluster_width))
        center = float(cluster["cluster_center"])
        matches = [item for item in prior if abs((self._safe_float(item.get("price"), center) or center) - center) <= tolerance]
        observed_at = observed_at or datetime.now(timezone.utc)
        current_strength = max((self._safe_float(item.get("strength_score"), 0.0) or 0.0 for item in cluster["component_levels"]), default=0.0)
        snapshots: dict[datetime, float] = {}
        for item in matches:
            stamp = self._parse_time(item.get("known_at_utc"))
            if not stamp or stamp > observed_at:
                continue
            snapshots[stamp] = max(snapshots.get(stamp, 0.0), self._safe_float(item.get("strength_score"), 0.0) or 0.0)
        current_times = [
            self._parse_time(item.get("known_at_utc"))
            for item in cluster.get("component_levels", [])
        ]
        current_times = [stamp for stamp in current_times if stamp and stamp <= observed_at]
        current_snapshot_at = max(current_times) if current_times else observed_at
        snapshots[current_snapshot_at] = max(snapshots.get(current_snapshot_at, 0.0), current_strength)
        times = sorted(snapshots)
        count = len(times)
        age_minutes = round((observed_at - times[0]).total_seconds() / 60, 2) if times else None

        def change_for(minutes: int) -> float | None:
            cutoff = observed_at - timedelta(minutes=minutes)
            eligible = [stamp for stamp in times if stamp <= cutoff]
            if not eligible:
                return None
            baseline = snapshots[max(eligible)]
            return round(current_strength - baseline, 4)

        change_5m = change_for(5)
        change_15m = change_for(15)
        change_30m = change_for(30)
        state_change = change_15m if change_15m is not None else change_5m
        if count == 0:
            state = "NEW"
        elif count >= self.minimum_persistence and state_change is not None and state_change > 0.05:
            state = "STRENGTHENING"
        elif count >= self.minimum_persistence and state_change is not None and state_change < -0.05:
            state = "WEAKENING"
        elif count >= self.minimum_persistence:
            state = "PERSISTENT"
        else:
            state = "NEW"
        return {
            "persistence_state": state,
            "level_state": state,
            "snapshot_persistence_count": count,
            "level_age_minutes": age_minutes,
            "strength_change_5m": change_5m,
            "strength_change_15m": change_15m,
            "strength_change_30m": change_30m,
            "wall_migration": None,
            "gamma_flip_migration": None,
            "level_first_seen": times[0].isoformat() if times else None,
            "level_last_seen": times[-1].isoformat() if times else None,
            "persistence_fields_complete": bool(
                times and count >= self.minimum_persistence
                and change_5m is not None and change_15m is not None and change_30m is not None
            ),
            "persistence_model_version": "snapshot_timestamp_horizons_v2",
        }

    def _level_strength(self, cluster: dict[str, Any], gex: GexMap | dict[str, Any] | None, state: TickerState | dict[str, Any],
                        bar: dict[str, Any], prior_levels: list[Level | dict[str, Any]]) -> dict[str, Any]:
        ticker = str((state.ticker if hasattr(state, "ticker") else state.get("ticker")) or "").upper()
        spot = self._safe_float((state.spot_price if hasattr(state, "spot_price") else state.get("spot_price")), bar.get("close")) or self._safe_float(bar.get("close"), 0) or 0
        atr = max(0.01, self._safe_float(bar.get("atr"), 0.01) or 0.01)
        persistence = self._persistence(ticker, cluster, prior_levels, atr, self._parse_time(bar.get("bar_end_utc")))
        levels_sorted = sorted([self._level_dict(item) for item in prior_levels] + cluster["component_levels"],
                               key=lambda item: self._safe_float(item.get("strength_score"), 0.0) or 0.0,
                               reverse=True)
        component_ids = set(cluster.get("component_level_ids") or [])
        rank = next((index + 1 for index, item in enumerate(levels_sorted) if item.get("level_id") in component_ids), 10)
        abs_rank_score = max(0.0, 1.0 - min(rank - 1, 9) / 9)
        local_concentration = min(1.0, len(cluster["component_levels"]) / 4)
        level_types = set(cluster["component_level_types"])
        wall_or_flip = 1.0 if level_types & {"GAMMA_FLIP", "CALL_WALL", "PUT_WALL"} else 0.0
        multi_type = 1.0 if len(level_types) >= 2 else 0.0
        persistence_score = min(1.0, persistence["snapshot_persistence_count"] / max(1, self.minimum_persistence))
        strengthening_score = 1.0 if persistence["persistence_state"] == "STRENGTHENING" else 0.5 if persistence["persistence_state"] == "PERSISTENT" else 0.0
        distance_atr = abs(spot - float(cluster["cluster_center"])) / atr
        distance_score = max(0.0, 1.0 - min(distance_atr, 5.0) / 5.0)
        source_strength = max((self._safe_float(item.get("strength_score"), 0.0) or 0.0 for item in cluster["component_levels"]), default=0.0)
        score = (
            0.22 * abs_rank_score
            + 0.18 * local_concentration
            + 0.14 * wall_or_flip
            + 0.10 * multi_type
            + 0.16 * persistence_score
            + 0.08 * strengthening_score
            + 0.07 * distance_score
            + 0.05 * source_strength
        )
        tier = "C"
        for label, threshold in sorted(self.tier_thresholds.items(), key=lambda item: float(item[1]), reverse=True):
            if score >= float(threshold):
                tier = label
                break
        return {
            "level_strength_score": round(score, 4),
            "level_strength_tier": f"LEVEL_TIER_{tier}",
            "model_version": self.level_score_version,
            "components": {
                "absolute_GEX_rank": round(abs_rank_score, 4),
                "local_GEX_concentration": round(local_concentration, 4),
                "OI_concentration": round(min(1.0, (self._safe_float(cluster.get("combined_OI"), 0.0) or 0.0) / 100000), 4),
                "multi_level_cluster": round(multi_type, 4),
                "wall_or_gamma_flip_proximity": round(wall_or_flip, 4),
                "persistence_score": round(persistence_score, 4),
                "strengthening_score": round(strengthening_score, 4),
                "distance_from_spot_score": round(distance_score, 4),
                "source_strength": round(source_strength, 4),
            },
            "distance_to_level_ATR": round(distance_atr, 4),
            **persistence,
        }

    def _aggregate_bars(self, bars: list[dict[str, Any]], count: int) -> dict[str, Any] | None:
        if len(bars) < count:
            return None
        rows = bars[-count:]
        return {
            "ticker": rows[-1].get("ticker"),
            "timeframe": f"{count * 5}m",
            "bar_start_utc": rows[0].get("bar_start_utc"),
            "bar_end_utc": rows[-1].get("bar_end_utc"),
            "open": self._safe_float(rows[0].get("open"), 0.0),
            "high": max(self._safe_float(row.get("high"), 0.0) or 0.0 for row in rows),
            "low": min(self._safe_float(row.get("low"), 0.0) or 0.0 for row in rows),
            "close": self._safe_float(rows[-1].get("close"), 0.0),
            "volume": sum(self._safe_float(row.get("volume"), 0.0) or 0.0 for row in rows),
            "vwap": self._safe_float(rows[-1].get("vwap"), None),
            "atr": self._safe_float(rows[-1].get("atr"), 0.0),
            "relative_volume": self._safe_float(rows[-1].get("relative_volume"), 1.0),
            "closed": True,
        }

    def _completed_timeframe_bars(self, bars: list[dict[str, Any]], minutes: int) -> list[dict[str, Any]]:
        """Aggregate completed 5m bars into exchange-aligned completed bars.

        A partial 15m/30m bucket is never returned.  This matters for the
        prospective confirmation branches: a 10:00-10:15 bar only becomes
        usable after its 10:15 ET close is known.
        """
        if minutes <= 0 or minutes % 5:
            return []
        required = minutes // 5
        normalized: list[tuple[datetime, datetime, dict[str, Any]]] = []
        seen: set[tuple[str, str]] = set()
        for raw in bars:
            if raw.get("closed") is False:
                continue
            start = self._parse_time(raw.get("bar_start_utc"))
            end = self._parse_time(raw.get("bar_end_utc"))
            if not start or not end or end <= start:
                continue
            key = (start.isoformat(), end.isoformat())
            if key in seen:
                continue
            seen.add(key)
            normalized.append((start, end, raw))
        normalized.sort(key=lambda item: item[0])
        buckets: dict[datetime, list[tuple[datetime, datetime, dict[str, Any]]]] = defaultdict(list)
        for start, end, row in normalized:
            local_start = start.astimezone(EASTERN)
            minute = (local_start.minute // minutes) * minutes
            bucket_local = local_start.replace(minute=minute, second=0, microsecond=0)
            buckets[bucket_local.astimezone(timezone.utc)].append((start, end, row))

        result: list[dict[str, Any]] = []
        for bucket_start, items in sorted(buckets.items()):
            bucket_end = bucket_start + timedelta(minutes=minutes)
            expected_starts = {bucket_start + timedelta(minutes=5 * index) for index in range(required)}
            actual = {item[0] for item in items if item[0] in expected_starts and item[1] <= bucket_end}
            if actual != expected_starts:
                continue
            ordered = sorted((item for item in items if item[0] in expected_starts), key=lambda item: item[0])
            rows = [item[2] for item in ordered]
            result.append({
                "ticker": rows[-1].get("ticker"),
                "timeframe": f"{minutes}m",
                "bar_start_utc": bucket_start.isoformat(),
                "bar_end_utc": bucket_end.isoformat(),
                "open": self._safe_float(rows[0].get("open"), 0.0),
                "high": max(self._safe_float(row.get("high"), 0.0) or 0.0 for row in rows),
                "low": min(self._safe_float(row.get("low"), 0.0) or 0.0 for row in rows),
                "close": self._safe_float(rows[-1].get("close"), 0.0),
                "volume": sum(self._safe_float(row.get("volume"), 0.0) or 0.0 for row in rows),
                "vwap": self._safe_float(rows[-1].get("vwap"), None),
                "atr": self._safe_float(rows[-1].get("atr"), 0.0),
                "relative_volume": self._safe_float(rows[-1].get("relative_volume"), 1.0),
                "closed": True,
                "aggregation_version": "exchange_aligned_completed_bars_v1",
            })
        return result

    def _confirmed_swing_pivots(self, bars: list[dict[str, Any]], *, left: int = 2,
                                right: int = 2) -> dict[str, list[dict[str, Any]]]:
        """Return pivots confirmed only after right-side completed bars exist."""
        highs: list[dict[str, Any]] = []
        lows: list[dict[str, Any]] = []
        if len(bars) < left + right + 1:
            return {"highs": highs, "lows": lows}
        for index in range(left, len(bars) - right):
            window = bars[index - left:index + right + 1]
            current_high = self._safe_float(bars[index].get("high"), None)
            current_low = self._safe_float(bars[index].get("low"), None)
            other_highs = [self._safe_float(row.get("high"), None) for offset, row in enumerate(window) if offset != left]
            other_lows = [self._safe_float(row.get("low"), None) for offset, row in enumerate(window) if offset != left]
            other_highs = [value for value in other_highs if value is not None]
            other_lows = [value for value in other_lows if value is not None]
            if current_high is not None and other_highs and current_high > max(other_highs):
                highs.append({"price": current_high, "bar_end_utc": bars[index].get("bar_end_utc"), "index": index})
            if current_low is not None and other_lows and current_low < min(other_lows):
                lows.append({"price": current_low, "bar_end_utc": bars[index].get("bar_end_utc"), "index": index})
        return {"highs": highs, "lows": lows}

    def _structural_invalidation_diagnostics(self, bars: list[dict[str, Any]], direction: str) -> dict[str, Any]:
        completed_5m = sorted(
            [row for row in bars if row.get("closed") is not False and self._parse_time(row.get("bar_end_utc"))],
            key=lambda row: row.get("bar_end_utc") or "",
        )
        completed_15m = self._completed_timeframe_bars(completed_5m, 15)
        pivots_5m = self._confirmed_swing_pivots(completed_5m)
        pivots_15m = self._confirmed_swing_pivots(completed_15m)
        is_long = direction == "LONG"
        relevant_15m = pivots_15m["lows" if is_long else "highs"]
        relevant_5m = pivots_5m["lows" if is_long else "highs"]
        structural_15m = relevant_15m[-1] if relevant_15m else None
        hl_lh = None
        if len(relevant_5m) >= 2:
            previous, latest = relevant_5m[-2], relevant_5m[-1]
            confirmed = latest["price"] > previous["price"] if is_long else latest["price"] < previous["price"]
            if confirmed:
                hl_lh = latest
        return {
            "structural_invalidation_model_version": "confirmed_swing_2x2_completed_bars_v1",
            "completed_15m_bar_count": len(completed_15m),
            "confirmed_15m_swing_count": len(relevant_15m),
            "confirmed_5m_directional_swing_count": len(relevant_5m),
            "structural_invalidation_15m": round(float(structural_15m["price"]), 6) if structural_15m else None,
            "structural_invalidation_15m_pivot_at": structural_15m.get("bar_end_utc") if structural_15m else None,
            "last_confirmed_hl_lh_invalidation": round(float(hl_lh["price"]), 6) if hl_lh else None,
            "last_confirmed_hl_lh_at": hl_lh.get("bar_end_utc") if hl_lh else None,
            "has_15m_structure_invalidation": structural_15m is not None,
            "has_hl_lh_structure": hl_lh is not None,
        }

    def _fifteen_minute_confirmation(self, event: dict[str, Any], bars: list[dict[str, Any]]) -> dict[str, Any]:
        completed = self._completed_timeframe_bars(bars, 15)
        event_at = self._parse_time(event.get("created_at_utc"))
        if event_at:
            event_date = event_at.astimezone(EASTERN).date()
            completed = [
                row for row in completed
                if (self._parse_time(row.get("bar_end_utc"))
                    and self._parse_time(row.get("bar_end_utc")).astimezone(EASTERN).date() == event_date)
            ]
        if len(completed) < 2:
            return {
                "confirmed": False,
                "reason": "AWAITING_COMPLETED_15M_CONFIRMATION",
                "completed_15m_bar_count": len(completed),
                "model_version": "completed_15m_interaction_v1",
            }
        interactions = self._detect_interactions(event["cluster"], completed[-2], completed[-1])
        match = next((item for item in interactions if item["direction"] == event["direction"]
                      and item["structural_family"] == event["structural_family"]), None)
        return {
            "confirmed": match is not None,
            "reason": None if match else "COMPLETED_15M_BAR_DID_NOT_CONFIRM_INTERACTION",
            "completed_15m_bar_count": len(completed),
            "confirmation_bar_start_utc": completed[-1].get("bar_start_utc"),
            "confirmation_bar_end_utc": completed[-1].get("bar_end_utc"),
            "matched_interaction": match,
            "model_version": "completed_15m_interaction_v1",
        }

    @staticmethod
    def _price_zone_position(close: float, low: float, high: float) -> str:
        if close > high:
            return "ABOVE"
        if close < low:
            return "BELOW"
        return "INSIDE"

    @staticmethod
    def _bar_overlaps_zone(bar_low: float, bar_high: float, low: float, high: float) -> bool:
        return bar_low <= high and bar_high >= low

    def _detect_interactions(self, cluster: dict[str, Any], previous_bar: dict[str, Any], bar: dict[str, Any]) -> list[dict[str, str]]:
        low = float(cluster["cluster_low"])
        high = float(cluster["cluster_high"])
        center = float(cluster["cluster_center"])
        prev_close = self._safe_float(previous_bar.get("close"), center) or center
        close = self._safe_float(bar.get("close"), center) or center
        bar_low = self._safe_float(bar.get("low"), center) or center
        bar_high = self._safe_float(bar.get("high"), center) or center
        prev_low = self._safe_float(previous_bar.get("low"), center) or center
        prev_high = self._safe_float(previous_bar.get("high"), center) or center
        interactions: list[dict[str, str]] = []
        prev_position = self._price_zone_position(prev_close, low, high)
        close_position = self._price_zone_position(close, low, high)
        current_overlaps = self._bar_overlaps_zone(bar_low, bar_high, low, high)
        previous_overlaps = self._bar_overlaps_zone(prev_low, prev_high, low, high)
        interacted = current_overlaps or previous_overlaps
        swept_below = min(prev_low, bar_low) < low
        swept_above = max(prev_high, bar_high) > high

        if swept_below and close_position == "ABOVE" and prev_position in {"BELOW", "INSIDE"}:
            interactions.append({
                "direction": "LONG",
                "structural_family": "RECLAIM",
                "interaction_type": "RECLAIM",
                "approach_direction": "FROM_BELOW",
                "confirmation_state": "LONG_RECLAIM",
            })
        if swept_above and close_position == "BELOW" and prev_position in {"ABOVE", "INSIDE"}:
            interactions.append({
                "direction": "SHORT",
                "structural_family": "RECLAIM",
                "interaction_type": "RECLAIM",
                "approach_direction": "FROM_ABOVE",
                "confirmation_state": "SHORT_RECLAIM",
            })
        if current_overlaps and prev_position == "ABOVE" and close_position == "ABOVE" and not any(
            item["direction"] == "LONG" and item["structural_family"] == "RECLAIM" for item in interactions
        ):
            interactions.append({
                "direction": "LONG",
                "structural_family": "REJECTION",
                "interaction_type": "REJECTION",
                "approach_direction": "FROM_ABOVE",
                "confirmation_state": "LONG_REJECTION",
            })
        if current_overlaps and prev_position == "BELOW" and close_position == "BELOW" and not any(
            item["direction"] == "SHORT" and item["structural_family"] == "RECLAIM" for item in interactions
        ):
            interactions.append({
                "direction": "SHORT",
                "structural_family": "REJECTION",
                "interaction_type": "REJECTION",
                "approach_direction": "FROM_BELOW",
                "confirmation_state": "SHORT_REJECTION",
            })
        if interacted and prev_position in {"BELOW", "INSIDE"} and close_position == "ABOVE" and not any(
            item["direction"] == "LONG" for item in interactions
        ):
            interactions.append({
                "direction": "LONG",
                "structural_family": "LEVEL_BREAKOUT",
                "interaction_type": "BREAKOUT",
                "approach_direction": "FROM_BELOW",
                "confirmation_state": "BREAKOUT_LONG",
            })
        if interacted and prev_position in {"ABOVE", "INSIDE"} and close_position == "BELOW" and not any(
            item["direction"] == "SHORT" for item in interactions
        ):
            interactions.append({
                "direction": "SHORT",
                "structural_family": "LEVEL_BREAKOUT",
                "interaction_type": "BREAKDOWN",
                "approach_direction": "FROM_ABOVE",
                "confirmation_state": "BREAKDOWN_SHORT",
            })
        return interactions

    def _time_bucket(self, at: datetime | None) -> str:
        if not at:
            return "UNKNOWN"
        local = at.astimezone(EASTERN).time()
        buckets = [
            (time(9, 40), time(10, 0), "09:40-10:00"),
            (time(10, 0), time(10, 30), "10:00-10:30"),
            (time(10, 30), time(11, 30), "10:30-11:30"),
            (time(11, 30), time(13, 0), "11:30-13:00"),
            (time(13, 0), time(14, 30), "13:00-14:30"),
            (time(14, 30), time(15, 30), "14:30-15:30"),
            (time(15, 30), time(16, 1), "15:30-close"),
        ]
        for start, end, label in buckets:
            if start <= local < end:
                return label
        return "OUTSIDE_RTH_RESEARCH_EXCLUDED"

    def _trend_from_bars(self, bars: list[dict[str, Any]], lookback: int) -> str:
        if len(bars) < lookback + 1:
            return "UNKNOWN"
        latest = self._safe_float(bars[-1].get("close"), None)
        earlier = self._safe_float(bars[-lookback - 1].get("close"), None)
        if latest is None or earlier in {None, 0}:
            return "UNKNOWN"
        change = (latest - earlier) / earlier
        threshold = 0.0015 if lookback <= 3 else 0.003
        if change > threshold:
            return "BULLISH"
        if change < -threshold:
            return "BEARISH"
        return "NEUTRAL"

    @staticmethod
    def _alignment(direction: str, trend: str) -> str:
        if trend == "UNKNOWN":
            return "UNKNOWN"
        if trend == "NEUTRAL":
            return "NEUTRAL"
        return "WITH_MARKET_TREND" if (direction == "LONG" and trend == "BULLISH") or (direction == "SHORT" and trend == "BEARISH") else "AGAINST_MARKET_TREND"

    def _context_features(self, ticker: str, direction: str, cluster: dict[str, Any], bars: list[dict[str, Any]],
                          bar: dict[str, Any], state: TickerState | dict[str, Any], gex: GexMap | dict[str, Any] | None,
                          guard: GuardStatus | dict[str, Any] | None, providers: dict[str, Any],
                          strength: dict[str, Any]) -> dict[str, Any]:
        at = self._parse_time(bar.get("bar_end_utc"))
        close = self._safe_float(bar.get("close"), 0.0) or 0.0
        atr = max(0.01, self._safe_float(bar.get("atr"), 0.01) or 0.01)
        vwap = self._safe_float(bar.get("vwap"), None)
        watch = self.watchlist.entry(ticker) if self.watchlist else None
        tier = watch.tier if watch else "UNKNOWN"
        gex_payload = gex.model_dump(mode="json") if hasattr(gex, "model_dump") else (gex or {})
        gamma_flip = self._safe_float(gex_payload.get("gamma_flip"), None)
        spy_bars = bars if ticker == "SPY" else self._recent_bars_for("SPY", at, 100)
        qqq_bars = bars if ticker == "QQQ" else self._recent_bars_for("QQQ", at, 100)
        spy_15m = self._trend_from_bars(spy_bars, 3)
        qqq_15m = self._trend_from_bars(qqq_bars, 3)
        spy_1h = self._trend_from_bars(spy_bars, 12)
        qqq_1h = self._trend_from_bars(qqq_bars, 12)
        market_trend = qqq_15m if ticker in {"QQQ", "NVDA", "AMD", "TSLA", "AAPL", "MSFT", "META", "AMZN", "PLTR", "HOOD"} else spy_15m
        return {
            "ticker": ticker,
            "direction": direction,
            "trade_date": at.astimezone(EASTERN).date().isoformat() if at else None,
            "created_at_utc": at.isoformat() if at else datetime.now(timezone.utc).isoformat(),
            "time_bucket": self._time_bucket(at),
            "watchlist_tier": tier,
            "asset_class": "ETF_INDEX_PROXY" if ticker in {"SPY", "QQQ", "IWM", "DIA"} else "SINGLE_STOCK",
            "trend_1m": "UNKNOWN",
            "trend_5m": self._trend_from_bars(bars, 1),
            "trend_15m": self._trend_from_bars(bars, 3),
            "trend_30m": self._trend_from_bars(bars, 6),
            "trend_1h": self._trend_from_bars(bars, 12),
            "market_alignment": self._alignment(direction, market_trend),
            "broader_market_trend_used": market_trend,
            "SPY_15m_trend": spy_15m,
            "QQQ_15m_trend": qqq_15m,
            "SPY_1h_trend": spy_1h,
            "QQQ_1h_trend": qqq_1h,
            "SPY_15m_alignment": self._alignment(direction, spy_15m),
            "QQQ_15m_alignment": self._alignment(direction, qqq_15m),
            "vwap": vwap,
            "vwap_position": "ABOVE" if vwap is not None and close > vwap else "BELOW" if vwap is not None and close < vwap else "UNKNOWN",
            "distance_from_vwap_ATR": round(abs(close - vwap) / atr, 4) if vwap is not None else None,
            "previous_day_high": self._previous_day_extreme(ticker, at, "high") if at else None,
            "previous_day_low": self._previous_day_extreme(ticker, at, "low") if at else None,
            "opening_range": self._opening_range(ticker, at) if at else None,
            "short_term_ATR": atr,
            "realized_volatility_proxy": round((self._safe_float(bar.get("high"), close) - self._safe_float(bar.get("low"), close)) / max(close, 1), 6),
            "volume_regime": "HIGH" if (self._safe_float(bar.get("relative_volume"), 1.0) or 1.0) >= 1.25 else "NORMAL",
            "gamma_regime": str(gex_payload.get("gamma_regime") or "UNKNOWN").upper(),
            "gamma_flip": gamma_flip,
            "distance_to_gamma_flip_ATR": round(abs(close - gamma_flip) / atr, 4) if gamma_flip is not None else None,
            "candle_provider": providers.get("price") or (providers.get("candle_router") or {}).get("selected_candle_provider"),
            "data_quality": providers.get("candle_router", {}).get("data_quality") if isinstance(providers.get("candle_router"), dict) else None,
            "macro_guard_blocked": bool((guard.model_dump(mode="json") if hasattr(guard, "model_dump") else (guard or {})).get("blocked")),
            "level_strength": strength,
            "cluster": {key: value for key, value in cluster.items() if key != "component_levels"},
            "branch_matrix_version": self.branch_matrix_version,
            "counts_as_empirical_setup": False,
            "parent_event_counts_once": True,
        }

    def _recent_bars_for(self, ticker: str, at: datetime | None, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.repository.list_json("market_bars", "WHERE ticker=? AND timeframe=?", (ticker.upper(), "5m"), limit)
        result = []
        for row in rows:
            stamp = self._parse_time(row.get("bar_end_utc"))
            if stamp and at and stamp <= at:
                result.append(row)
        return sorted(result, key=lambda item: item.get("bar_end_utc") or "")

    def _previous_day_extreme(self, ticker: str, at: datetime | None, field: str) -> float | None:
        if not at:
            return None
        local_date = at.astimezone(EASTERN).date()
        rows = self.repository.list_json("market_bars", "WHERE ticker=? AND timeframe=?", (ticker, "5m"), 100000)
        values = []
        for row in rows:
            stamp = self._parse_time(row.get("bar_end_utc"))
            if stamp and stamp.astimezone(EASTERN).date() < local_date:
                value = self._safe_float(row.get(field), None)
                if value is not None:
                    values.append((stamp, value))
        if not values:
            return None
        latest_day = max(stamp.astimezone(EASTERN).date() for stamp, _ in values)
        day_values = [value for stamp, value in values if stamp.astimezone(EASTERN).date() == latest_day]
        return max(day_values) if field == "high" else min(day_values) if field == "low" else None

    def _opening_range(self, ticker: str, at: datetime | None) -> dict[str, float] | None:
        if not at:
            return None
        local_date = at.astimezone(EASTERN).date()
        rows = self.repository.list_json("market_bars", "WHERE ticker=? AND timeframe=?", (ticker, "5m"), 100000)
        highs, lows = [], []
        for row in rows:
            stamp = self._parse_time(row.get("bar_end_utc"))
            if not stamp or stamp.astimezone(EASTERN).date() != local_date:
                continue
            local_time = stamp.astimezone(EASTERN).time()
            if time(9, 30) <= local_time <= time(10, 0):
                high = self._safe_float(row.get("high"), None)
                low = self._safe_float(row.get("low"), None)
                if high is not None:
                    highs.append(high)
                if low is not None:
                    lows.append(low)
        return {"high": max(highs), "low": min(lows)} if highs and lows else None

    def _episode_metadata(self, cluster: dict[str, Any], bars: list[dict[str, Any]]) -> dict[str, Any]:
        low = float(cluster["cluster_low"])
        high = float(cluster["cluster_high"])
        latest_atr = max(0.01, self._safe_float((bars[-1] if bars else {}).get("atr"), 0.01) or 0.01)
        reset_buffer = latest_atr * self.episode_reset_distance_atr

        def far_from_zone(row: dict[str, Any]) -> bool:
            row_low = self._safe_float(row.get("low"), low) or low
            row_high = self._safe_float(row.get("high"), high) or high
            return row_high < low - reset_buffer or row_low > high + reset_buffer

        anchor_index = max(0, len(bars) - 1)
        far_run = 0
        reset_seen = False
        for index in range(len(bars) - 1, -1, -1):
            if far_from_zone(bars[index]):
                far_run += 1
                if far_run >= self.episode_reset_bars:
                    anchor_index = min(len(bars) - 1, index + self.episode_reset_bars)
                    reset_seen = True
                    break
            else:
                far_run = 0
                anchor_index = index
        anchor_bar = bars[anchor_index] if bars else {}
        anchor_time = self._parse_time(anchor_bar.get("bar_end_utc")) or datetime.now(timezone.utc)
        return {
            "interaction_episode": anchor_time.isoformat(),
            "episode_anchor_utc": anchor_time.isoformat(),
            "episode_reset_condition": f"{self.episode_reset_bars}_bars_farther_than_{self.episode_reset_distance_atr}_ATR_from_zone",
            "episode_reset_seen": reset_seen,
        }

    def _event_identity(self, ticker: str, trade_date: str, cluster_id: str, direction: str,
                        family: str, episode: str) -> str:
        return self._stable_id("phase4event", ticker, trade_date, cluster_id, direction, family, episode)

    def _phase4b1_instrumentation(self, *, event_seed: dict[str, Any], context: dict[str, Any],
                                  strength: dict[str, Any], cluster: dict[str, Any],
                                  bars: list[dict[str, Any]]) -> dict[str, Any]:
        """Prospective research-only diagnostics for Phase 4B.1.

        These fields are passive metadata. They do not affect setup generation,
        entry qualification, paper orders, stops, targets, gates, or alerts.
        """
        try:
            from .phase4b1 import classify_direction, classify_structure, interaction_role
            row = {
                **event_seed,
                "level_tier": strength.get("level_strength_tier"),
                "level_strength": strength.get("level_strength_score"),
                "intraday_persistence_state": strength.get("persistence_state"),
                "trend_5m": context.get("trend_5m"),
                "trend_15m": context.get("trend_15m"),
                "trend_30m": context.get("trend_30m"),
                "trend_1h": context.get("trend_1h"),
                "SPY_15m_trend": context.get("SPY_15m_trend"),
                "QQQ_15m_trend": context.get("QQQ_15m_trend"),
                "market_alignment": context.get("market_alignment"),
                "distance_to_level_ATR": strength.get("distance_to_level_ATR"),
            }
            structure = classify_structure(row)
            direction = classify_direction({**row, **structure})
            role = interaction_role({**row, **structure, **direction})
            invalidation = self._structural_invalidation_diagnostics(bars, str(event_seed.get("direction") or ""))
            confirmation_15m = self._fifteen_minute_confirmation(
                {**event_seed, "cluster": cluster}, bars)
            return {
                "phase4b1_instrumentation_version": "phase4b1_forward_metadata_v2",
                "research_only": True,
                "canonical_behavior_changed": False,
                "level_role_before": role.get("level_role_before"),
                "level_role_after": role.get("level_role_after"),
                "role_transition": role.get("role_transition"),
                "direction_class": direction.get("direction_class"),
                "direction_confidence_0_100": direction.get("direction_confidence_0_100"),
                "predicted_direction": direction.get("predicted_direction"),
                "direction_evidence": direction.get("direction_evidence"),
                "direction_conflicts": direction.get("direction_conflicts"),
                "structure_5m": structure.get("structure_5m"),
                "structure_15m": structure.get("structure_15m"),
                "structure_30m": structure.get("structure_30m"),
                "structure_1h": structure.get("structure_1h"),
                "structure_alignment": structure.get("structure_alignment"),
                "has_15m_structure": invalidation["has_15m_structure_invalidation"],
                "has_15m_structure_invalidation": invalidation["has_15m_structure_invalidation"],
                "has_hl_lh_structure": invalidation["has_hl_lh_structure"],
                "structural_invalidation_15m": invalidation["structural_invalidation_15m"],
                "structural_invalidation_15m_pivot_at": invalidation["structural_invalidation_15m_pivot_at"],
                "last_confirmed_hl_lh_invalidation": invalidation["last_confirmed_hl_lh_invalidation"],
                "last_confirmed_hl_lh_at": invalidation["last_confirmed_hl_lh_at"],
                "structural_invalidation_model_version": invalidation["structural_invalidation_model_version"],
                "confirmation_15m": confirmation_15m,
                "has_completed_15m_confirmation": confirmation_15m["confirmed"],
                "entry_timing_diagnostics": {
                    "distance_to_level_ATR": strength.get("distance_to_level_ATR"),
                    "entry_delay_bars": 0,
                    "entry_delay_minutes": 0,
                    "classification": "ON_TIME_ENTRY",
                },
                "raw_path_tracking_required": True,
                "ordered_threshold_tracking_required": True,
                "stop_diagnostics_tracking_required": True,
                "target_diagnostics_tracking_required": True,
                "giveback_tracking_required": True,
                "breakeven_diagnostics_tracking_required": True,
                "path_shape_tracking_required": True,
                "data_quality_attribution_required": True,
                "level_identity": {
                    "cluster_center": cluster.get("cluster_center"),
                    "cluster_low": cluster.get("cluster_low"),
                    "cluster_high": cluster.get("cluster_high"),
                    "component_level_ids": cluster.get("component_level_ids"),
                    "component_level_types": cluster.get("component_level_types"),
                    "combined_GEX": cluster.get("combined_GEX"),
                    "combined_OI": cluster.get("combined_OI"),
                },
            }
        except Exception as exc:
            return {
                "phase4b1_instrumentation_version": "phase4b1_forward_metadata_v2",
                "research_only": True,
                "canonical_behavior_changed": False,
                "instrumentation_error": str(exc),
            }

    def _variant_spec(self, name: str) -> dict[str, Any]:
        return self.VARIANT_SPECS.get(name) or self.PHASE4B2_VARIANT_SPECS.get(name) or {
            "timeframe_context": "matched_control",
            "confirmation_tf": "5m",
            "execution_tf": "5m",
            "requires_persistent_level": False,
            "requires_15m_confirmation": False,
            "requires_30m_context": False,
            "requires_1m_entry": False,
        }

    def _stop_for_variant(self, event: dict[str, Any], stop_variant: str) -> float | None:
        direction = event["direction"]
        atr = max(0.01, self._safe_float(event["context"]["short_term_ATR"], 0.01) or 0.01)
        low = self._safe_float(event["cluster"]["cluster_low"], event["level_price"]) or event["level_price"]
        high = self._safe_float(event["cluster"]["cluster_high"], event["level_price"]) or event["level_price"]
        current_structural = self._safe_float(event.get("structural_stop"), None)
        if stop_variant in {"STOP_A_CURRENT_STRUCTURAL", "S0_CANONICAL_STOP"} and current_structural is not None:
            return current_structural
        if stop_variant in {"STOP_E_LEVEL_ZONE_INVALIDATION", "S1_FULL_OPTIONS_LEVEL_ZONE_INVALIDATION"}:
            return low if direction == "LONG" else high
        if stop_variant == "S2_15M_STRUCTURAL_INVALIDATION":
            return self._safe_float((event.get("phase4b1_diagnostics") or {}).get("structural_invalidation_15m"), None)
        if stop_variant == "S3_LAST_CONFIRMED_HL_LH_INVALIDATION":
            return self._safe_float((event.get("phase4b1_diagnostics") or {}).get("last_confirmed_hl_lh_invalidation"), None)
        buffer_atr = self.STOP_VARIANTS.get(stop_variant)
        if buffer_atr is None:
            buffer_atr = self.PHASE4B2_STOP_VARIANTS.get(stop_variant)
        if buffer_atr is None:
            buffer_atr = float(self.settings.get("stops.baseline_atr_buffer", 0.30))
        return round(low - atr * float(buffer_atr), 6) if direction == "LONG" else round(high + atr * float(buffer_atr), 6)

    def _target_prices(self, entry: float, stop: float, direction: str) -> list[float]:
        risk = abs(entry - stop)
        if risk <= 0:
            return []
        mult = 1 if direction == "LONG" else -1
        return [round(entry + mult * risk * multiple, 6) for multiple in (0.5, 1.0, 1.5, 2.0)]

    def _entry_ready(self, entry_variant: str, event: dict[str, Any], variant: dict[str, Any],
                     bars: list[dict[str, Any]]) -> tuple[str, list[str]]:
        reasons: list[str] = []
        persistence_payload = event["context"]["level_strength"]
        persistence = persistence_payload.get("persistence_state") or persistence_payload.get("level_state")
        persistence_complete = bool(
            persistence_payload.get("persistence_fields_complete")
            and persistence_payload.get("level_first_seen")
            and persistence_payload.get("level_last_seen")
            and persistence_payload.get("snapshot_persistence_count") is not None
            and persistence_payload.get("level_age_minutes") is not None
            and persistence_payload.get("strength_change_5m") is not None
            and persistence_payload.get("strength_change_15m") is not None
            and persistence_payload.get("strength_change_30m") is not None
        )
        if variant.get("requires_strong_level") and event.get("level_tier") not in {"LEVEL_TIER_S", "LEVEL_TIER_A"}:
            reasons.append("Phase 4B.2 requires strong options level tier S/A")
        if variant.get("requires_price_structure"):
            diagnostics = event.get("phase4b1_diagnostics") or {}
            structure_5m = str(diagnostics.get("structure_5m") or "UNKNOWN").upper()
            if structure_5m != str(event.get("direction") or "").upper():
                reasons.append("price-structure-only base requires aligned deterministic 5m structure")
        if variant.get("requires_persistent_level"):
            if not persistence_complete:
                reasons.append("NOT_QUALIFIED_MISSING_PERSISTENCE")
            elif persistence not in {"PERSISTENT", "STRENGTHENING"}:
                reasons.append("level is not persistent or strengthening")
        if variant.get("requires_direction_classifier"):
            diagnostics = event.get("phase4b1_diagnostics") or {}
            direction_class = diagnostics.get("direction_class")
            predicted = diagnostics.get("predicted_direction")
            confidence = self._safe_float(diagnostics.get("direction_confidence_0_100"), 0.0) or 0.0
            if direction_class in {None, "DIRECTION_UNCERTAIN", "NEUTRAL_REACTION_ZONE"}:
                reasons.append("NOT_QUALIFIED_MISSING_DIRECTION_CLASSIFIER")
            if predicted not in {None, "UNKNOWN", event.get("direction")}:
                reasons.append("level direction classifier conflicts with event direction")
            if confidence < 60:
                reasons.append("level direction classifier confidence below 60")
        if variant.get("requires_15m_confirmation"):
            confirmation = self._fifteen_minute_confirmation(event, bars)
            if not confirmation["confirmed"]:
                event_at = self._parse_time(event.get("created_at_utc"))
                latest_completed = self._parse_time(confirmation.get("confirmation_bar_end_utc"))
                if not latest_completed or (event_at and latest_completed <= event_at):
                    reasons.append("AWAITING_COMPLETED_15M_CONFIRMATION")
                else:
                    reasons.append("completed 15m bar did not confirm same interaction family/direction")
        if variant.get("requires_30m_context") and len(bars) < 6:
            reasons.append("30m context unavailable")
        if variant.get("requires_1m_entry"):
            reasons.append("1m execution-refinement feed is not available in current free pipeline")
        if entry_variant == "ENTRY_2" and event["structural_family"] not in {"RECLAIM", "REJECTION"}:
            reasons.append("retest variant requires reclaim/rejection family")
        if entry_variant == "ENTRY_3" and event["structural_family"] != "RECLAIM":
            reasons.append("sweep + reclaim + retest requires RECLAIM family")
        if entry_variant == "ENTRY_4" and event["context"].get("volume_regime") != "HIGH":
            reasons.append("volume confirmation missing")
        if entry_variant == "ENTRY_5" and event["context"].get("market_alignment") == "AGAINST_MARKET_TREND":
            reasons.append("market alignment confirmation missing")
        waiting = any(reason.startswith("AWAITING_") for reason in reasons)
        hard_reasons = [reason for reason in reasons if not reason.startswith("AWAITING_")]
        if hard_reasons:
            return "not_qualified", reasons
        return ("registered" if waiting else "pending"), reasons

    def _branch_prerequisite_status(self, blueprint: dict[str, Any], event: dict[str, Any],
                                    base_status: str, base_reasons: list[str]) -> tuple[str, list[str]]:
        reasons = list(base_reasons)
        diagnostics = event.get("phase4b1_diagnostics") or {}
        if blueprint.get("stop_variant") == "S2_15M_STRUCTURAL_INVALIDATION" and not diagnostics.get("has_15m_structure_invalidation"):
            reasons.append("S2 requires valid 15m structural invalidation")
        if blueprint.get("stop_variant") == "S3_LAST_CONFIRMED_HL_LH_INVALIDATION" and not diagnostics.get("has_hl_lh_structure"):
            reasons.append("S3 requires deterministic HL/LH structural invalidation")
        if blueprint.get("phase4b2_branch") == "P2":
            persistence_payload = event["context"]["level_strength"]
            if not persistence_payload.get("persistence_fields_complete"):
                reasons.append("P2 requires trustworthy persistence fields")
        if blueprint.get("phase4b2_branch") == "P3" and not diagnostics.get("predicted_direction"):
            reasons.append("P3 requires direction classifier output")
        if blueprint.get("phase4b2_branch") == "P4":
            if not diagnostics.get("predicted_direction"):
                reasons.append("P4 requires direction classifier output")
        hard_reasons = [reason for reason in reasons if not reason.startswith("AWAITING_")]
        if hard_reasons:
            return "not_qualified", reasons
        if base_status in {"pending", "registered"}:
            return base_status, reasons
        return "not_qualified", reasons

    @staticmethod
    def _lifecycle_state(status: str) -> str:
        return {
            "not_qualified": "NOT_QUALIFIED",
            "registered": "REGISTERED_AWAITING_CONFIRMATION",
            "pending": "PENDING_ENTRY",
            "open": "ACTIVE",
            "partial": "ACTIVE",
            "closed": "RESOLVED",
            "censored": "CENSORED",
            "qa_pre_fix": "QA_PRE_FIX",
            "accounting_invalid_pre_fix": "ACCOUNTING_INVALID_PRE_FIX",
        }.get(str(status or "").lower(), "REGISTERED")

    def _phase4b2_branch_blueprints(self) -> list[dict[str, Any]]:
        if not self.phase4b2_enabled:
            return []
        rows: list[dict[str, Any]] = []
        for stop_variant in self.PHASE4B2_STOP_VARIANTS:
            rows.append({
                "strategy_variant": "P4B2_E1_INVALIDATION_STOP",
                "entry_variant": "P4B2_CANONICAL_ENTRY",
                "management_variant": "M0_CURRENT_MANAGEMENT",
                "stop_variant": stop_variant,
                "is_control": False,
                "control_type": None,
                "phase4b2_experiment_id": "EXPERIMENT_1_INVALIDATION_STOP",
                "phase4b2_branch": stop_variant.split("_", 1)[0],
                "phase4b2_hypothesis": "BAD_STOP may be causal rather than merely associated.",
            })
        for management in self.PHASE4B2_MANAGEMENT_VARIANTS:
            rows.append({
                "strategy_variant": "P4B2_E2_PROFIT_PROTECTION",
                "entry_variant": "P4B2_CANONICAL_ENTRY",
                "management_variant": management,
                "stop_variant": "S0_CANONICAL_STOP",
                "is_control": False,
                "control_type": None,
                "phase4b2_experiment_id": "EXPERIMENT_2_PROFIT_PROTECTION",
                "phase4b2_branch": management.split("_", 1)[0],
                "phase4b2_hypothesis": "Profitable excursion may be lost by current management and breakeven/target handling.",
            })
        option_value = [
            ("P0", "P4B2_E3_OPTIONS_VALUE_P0_STRUCTURE_ONLY", "P4B2_P0_PRICE_STRUCTURE_ONLY", True, "P4B2_PRICE_STRUCTURE_ONLY"),
            ("P1", "P4B2_E3_OPTIONS_VALUE_P1_STRUCTURE_PLUS_STRONG_OPTIONS", "P4B2_P1_STRONG_OPTIONS_LEVEL", False, None),
            ("P2", "P4B2_E3_OPTIONS_VALUE_P2_PERSISTENT_OPTIONS", "P4B2_P2_PERSISTENT_OPTIONS_LEVEL", False, None),
            ("P3", "P4B2_E3_OPTIONS_VALUE_P3_DIRECTION_CLASSIFIER", "P4B2_P3_DIRECTION_CLASSIFIER", False, None),
            ("P4", "P4B2_E3_OPTIONS_VALUE_P4_DIRECTION_15M_CONFIRM", "P4B2_P4_DIRECTION_15M_CONFIRM", False, None),
        ]
        for branch, strategy, entry_variant, is_control, control_type in option_value:
            rows.append({
                "strategy_variant": strategy,
                "entry_variant": entry_variant,
                "management_variant": "M0_CURRENT_MANAGEMENT",
                "stop_variant": "S0_CANONICAL_STOP",
                "is_control": is_control,
                "control_type": control_type,
                "phase4b2_experiment_id": "EXPERIMENT_3_OPTIONS_VALUE",
                "phase4b2_branch": branch,
                "phase4b2_hypothesis": "Options plus structure should outperform price-structure-only matched controls if options data adds edge.",
            })
        return rows

    def _branch_blueprints(self) -> list[dict[str, Any]]:
        """Return the frozen, focused forward matrix.

        A parent interaction should feed a small number of predefined hypotheses,
        not a Cartesian product of every historical research setting.  Broader
        retrospective entry/stop/management grids remain available in the
        historical pipeline; forward collection keeps only A-D with the two
        frozen management baselines plus the Phase 4B.2 H1/H3/P0-P4 branches.
        """
        rows: list[dict[str, Any]] = []
        for variant in list(self.VARIANT_SPECS)[:4]:
            for management in self.CORE_MANAGEMENT_VARIANTS:
                rows.append({"strategy_variant": variant, "entry_variant": "ENTRY_1",
                             "management_variant": management, "stop_variant": "STOP_A_CURRENT_STRUCTURAL",
                             "is_control": False, "control_type": None})
        rows.extend(self._phase4b2_branch_blueprints())
        deduped = []
        seen = set()
        for row in rows:
            key = (row["strategy_variant"], row["entry_variant"], row["management_variant"], row["stop_variant"])
            if key not in seen:
                seen.add(key)
                deduped.append(row)
        return deduped

    def _control_level(self, control: str, event: dict[str, Any]) -> dict[str, Any] | None:
        entry = float(event["planned_entry"])
        atr = max(0.01, self._safe_float(event["context"]["short_term_ATR"], 0.01) or 0.01)
        width = float(event["cluster"].get("cluster_high", entry)) - float(event["cluster"].get("cluster_low", entry))
        digest = int(hashlib.sha256(f"{event['parent_event_id']}|{control}".encode()).hexdigest()[:8], 16)
        sign = 1 if digest % 2 else -1
        if control == "CONTROL_RANDOM_NEARBY_LEVEL":
            center = entry + sign * atr * (0.10 + (digest % 35) / 100)
        elif control == "CONTROL_RANDOM_CLUSTERED_PRICE_ZONE":
            center = entry + sign * atr * (0.25 + (digest % 50) / 100)
        elif control == "CONTROL_ROUND_NUMBER_LEVEL":
            increment = 5 if entry >= 100 else 1
            center = round(entry / increment) * increment
        elif control == "CONTROL_VWAP_INTERACTION":
            center = self._safe_float(event["context"].get("vwap"), None)
            if center is None:
                return None
        elif control == "CONTROL_PREVIOUS_DAY_HIGH":
            center = self._safe_float(event["context"].get("previous_day_high"), None)
            if center is None:
                return None
        elif control == "CONTROL_PREVIOUS_DAY_LOW":
            center = self._safe_float(event["context"].get("previous_day_low"), None)
            if center is None:
                return None
        elif control == "P4B2_PRICE_STRUCTURE_ONLY":
            opening_range = event["context"].get("opening_range") or {}
            candidates = [
                self._safe_float(event["context"].get("vwap"), None),
                self._safe_float(event["context"].get("previous_day_high"), None),
                self._safe_float(event["context"].get("previous_day_low"), None),
                self._safe_float(opening_range.get("high") if isinstance(opening_range, dict) else None, None),
                self._safe_float(opening_range.get("low") if isinstance(opening_range, dict) else None, None),
            ]
            candidates = [candidate for candidate in candidates if candidate is not None]
            if not candidates:
                return None
            center = min(candidates, key=lambda candidate: abs(candidate - entry))
        else:
            return None
        return {"center": round(center, 6), "low": round(center - max(width / 2, atr * 0.025), 6),
                "high": round(center + max(width / 2, atr * 0.025), 6)}

    def _create_branches(self, event: dict[str, Any], bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        entry = float(event["planned_entry"])
        now = datetime.now(timezone.utc).isoformat()
        for blueprint in self._branch_blueprints():
            spec = self._variant_spec(blueprint["strategy_variant"])
            event_for_branch = event
            control_level = None
            if blueprint.get("control_type") == "P4B2_PRICE_STRUCTURE_ONLY":
                # P0 is a nested, same-event ablation.  It removes options
                # qualifiers but keeps direction, entry, stop, management and
                # the observed price path identical to P1-P4.
                control_level = {
                    "center": event.get("level_price"),
                    "low": event["cluster"].get("cluster_low"),
                    "high": event["cluster"].get("cluster_high"),
                    "role": "MATCHED_SAME_ENTRY_PRICE_STRUCTURE_ONLY",
                    "options_identity_masked": True,
                    "control_scope": "incremental_options_metadata_not_level_location",
                }
                status, reasons = self._entry_ready(blueprint["entry_variant"], event, spec, bars)
            elif blueprint["is_control"]:
                control_level = self._control_level(blueprint["control_type"], event)
                if control_level is None:
                    status, reasons = "not_qualified", [f"{blueprint['control_type']} unavailable from stored data"]
                else:
                    event_for_branch = {**event, "cluster": {**event["cluster"], "cluster_center": control_level["center"],
                                                              "cluster_low": control_level["low"], "cluster_high": control_level["high"]},
                                        "level_price": control_level["center"]}
                    status, reasons = "pending", []
            else:
                status, reasons = self._entry_ready(blueprint["entry_variant"], event, spec, bars)
            status, reasons = self._branch_prerequisite_status(blueprint, event, status, reasons)
            stop = self._stop_for_variant(event_for_branch, blueprint["stop_variant"])
            direction = event["direction"]
            stop_valid = stop is not None and (
                (direction == "LONG" and stop < entry) or (direction == "SHORT" and stop > entry)
            )
            risk = abs(entry - stop) if stop_valid and stop is not None else 0.0
            if stop is None:
                status, reasons = "not_qualified", reasons + [f"{blueprint['stop_variant']} structural price unavailable"]
            elif not stop_valid or risk <= 0:
                status, reasons = "not_qualified", reasons + ["structural stop is not beyond entry in invalidation direction"]
            entry_zone_half = max(0.01, (self._safe_float(event_for_branch["context"]["short_term_ATR"], 0.01) or 0.01) * 0.05)
            branch = {
                "id": self._stable_id("phase4branch", event["parent_event_id"], blueprint["strategy_variant"],
                                      blueprint["entry_variant"], blueprint["management_variant"], blueprint["stop_variant"]),
                "parent_event_id": event["parent_event_id"],
                "ticker": event["ticker"],
                "strategy_variant": blueprint["strategy_variant"],
                "timeframe_context": spec["timeframe_context"],
                "confirmation_tf": spec["confirmation_tf"],
                "execution_tf": spec["execution_tf"],
                "entry_variant": blueprint["entry_variant"],
                "entry_variant_description": self.ENTRY_VARIANTS.get(blueprint["entry_variant"]),
                "management_variant": blueprint["management_variant"],
                "stop_variant": blueprint["stop_variant"],
                "status": status,
                "lifecycle_state": self._lifecycle_state(status),
                "qualification_state": (
                    "QUALIFIED" if status == "pending" else
                    "AWAITING_CONFIRMATION" if status == "registered" else
                    "NOT_QUALIFIED"
                ),
                "counts_as_empirical_branch": status == "pending",
                "created_at_utc": event["created_at_utc"],
                "updated_at_utc": now,
                "direction": direction,
                "structural_family": event["structural_family"],
                "interaction_type": event.get("interaction_type"),
                "level_type": event["level_type"],
                "level_tier": event["level_tier"],
                "is_control": blueprint["is_control"],
                "control_type": blueprint.get("control_type"),
                "entry_prerequisite_failures": reasons,
                "planned_entry": round(entry, 6),
                "entry_zone_low": round(entry - entry_zone_half, 6),
                "entry_zone_high": round(entry + entry_zone_half, 6),
                "actual_fill_price": None,
                "opened_at_utc": None,
                "closed_at_utc": None,
                "stop_initial": round(stop, 6) if stop is not None else None,
                "stop_current": round(stop, 6) if stop is not None else None,
                "initial_risk": round(risk, 6),
                "targets": self._target_prices(entry, stop, direction) if stop is not None and risk > 0 else [],
                "remaining_size": 1.0,
                "realized_R": None,
                "result_R": None,
                "result_R_components": [],
                "MFE": 0.0,
                "MAE": 0.0,
                "time_to_MFE_minutes": None,
                "time_to_0_5R_minutes": None,
                "time_to_1R_minutes": None,
                "time_to_1_5R_minutes": None,
                "time_to_2R_minutes": None,
                "holding_horizon_results_R": {"15m": None, "30m": None, "60m": None, "120m": None, "240m": None, "end_of_RTH": None},
                "holding_time_minutes": None,
                "exit_reason": None,
                "events": [],
                "context": event["context"],
                "phase4b1_diagnostics": event.get("phase4b1_diagnostics"),
                "level_cluster": event["cluster"],
                "control_level": control_level,
                "research_only": True,
                "canonical_strategy_unchanged": True,
                "live_trading_disabled": True,
                "branch_matrix_version": blueprint.get("branch_matrix_version") or (
                    self.PHASE4B2_BRANCH_MATRIX_VERSION if blueprint.get("phase4b2_experiment_id") else self.branch_matrix_version),
                "phase4b2_experiment_id": blueprint.get("phase4b2_experiment_id"),
                "phase4b2_branch": blueprint.get("phase4b2_branch"),
                "phase4b2_hypothesis": blueprint.get("phase4b2_hypothesis"),
                "phase4b2_research_only": bool(blueprint.get("phase4b2_experiment_id")),
                "phase4b2_activation_id": self.PHASE4B2_ID if blueprint.get("phase4b2_experiment_id") else None,
                "phase4b2_activation_cutoff_utc": (self.phase4b2_activation() or {}).get("activated_at_utc") if blueprint.get("phase4b2_experiment_id") else None,
                "phase4b2_same_parent_event": bool(blueprint.get("phase4b2_experiment_id")),
                "phase4b2_pairing_key": event["parent_event_id"] if blueprint.get("phase4b2_experiment_id") else None,
                "phase4b2_same_entry_stop_management_pair": blueprint.get("phase4b2_experiment_id") == "EXPERIMENT_3_OPTIONS_VALUE",
                "options_value_test_scope": (
                    "same_zone_price_structure_with_options_identity_masked_vs_options_qualified_branches"
                    if blueprint.get("phase4b2_experiment_id") == "EXPERIMENT_3_OPTIONS_VALUE" else None
                ),
                "phase4b2_no_canonical_change": bool(blueprint.get("phase4b2_experiment_id")),
                "qa_integrity_version": self.QA_INTEGRITY_VERSION,
                "qa_status": "POST_FIX",
                "accounting_integrity_version": self.ACCOUNTING_INTEGRITY_VERSION,
                "accounting_integrity_status": "PENDING_NO_FILL",
                "forward_instrumentation_version": self.FORWARD_INSTRUMENTATION_VERSION,
            }
            rows.append(branch)
        self.repository.store_intraday_edge_branches(rows)
        return rows

    def register_scan(self, *, run_id: str, observation_id: str, ticker: str, source_mode: str,
                      gex: GexMap | dict[str, Any] | None, current_levels: list[Level | dict[str, Any]],
                      prior_levels: list[Level | dict[str, Any]], bars: list[Bar | dict[str, Any]],
                      state: TickerState | dict[str, Any], guard: GuardStatus | dict[str, Any] | None,
                      eligibility: EligibilityContext | dict[str, Any] | None, providers: dict[str, Any],
                      setup: SetupEvent | dict[str, Any] | None = None, outcome: str | None = None) -> dict[str, Any]:
        bar_payloads = [self._bar_dict(bar) for bar in bars]
        if len(bar_payloads) < 2:
            return {"status": "skipped", "reason": "not enough bars"}
        latest = bar_payloads[-1]
        eligible, reasons = self._eligible(source_mode, eligibility, latest)
        if not eligible:
            return {"status": "skipped", "reasons": reasons}
        atr = max(0.01, self._safe_float(latest.get("atr"), 0.01) or 0.01)
        created_at = self._parse_time(latest.get("bar_end_utc")) or datetime.now(timezone.utc)
        trade_date = created_at.astimezone(EASTERN).date().isoformat()
        events_created = 0
        branches_created = 0
        interactions_seen = 0
        dedup_suppressions = 0
        setup_payload = setup.model_dump(mode="json") if hasattr(setup, "model_dump") else setup
        cluster_audit = [
            {"width_atr": width, "clusters": len(self._cluster_levels(current_levels, atr, width))}
            for width in self.cluster_widths
        ]
        economic_clusters = self._cluster_levels(current_levels, atr, self.default_cluster_width)
        for cluster in economic_clusters:
            strength = self._level_strength(cluster, gex, state, latest, prior_levels)
            interactions = self._detect_interactions(cluster, bar_payloads[-2], latest)
            interactions_seen += len(interactions)
            if not interactions:
                continue
            episode_meta = self._episode_metadata(cluster, bar_payloads)
            for interaction in interactions:
                direction = interaction["direction"]
                family = interaction["structural_family"]
                parent_id = self._event_identity(
                    ticker, trade_date, cluster["economic_level_cluster_id"], direction, family,
                    episode_meta["interaction_episode"],
                )
                low = float(cluster["cluster_low"])
                high = float(cluster["cluster_high"])
                structural_stop = round(low - atr * float(self.settings.get("stops.baseline_atr_buffer", 0.30)), 6) if direction == "LONG" else round(high + atr * float(self.settings.get("stops.baseline_atr_buffer", 0.30)), 6)
                context = self._context_features(ticker, direction, cluster, bar_payloads, latest, state, gex,
                                                 guard, providers, strength)
                context.update({
                    "economic_level_cluster_id": cluster["economic_level_cluster_id"],
                    "cluster_widths_audited": cluster_audit,
                    "parent_cluster_width_atr": self.default_cluster_width,
                    "interaction_type": interaction.get("interaction_type"),
                    "approach_direction": interaction.get("approach_direction"),
                    "qa_integrity_version": self.QA_INTEGRITY_VERSION,
                })
                event_seed = {
                    "parent_event_id": parent_id,
                    "symbol": ticker,
                    "trade_date": trade_date,
                    "direction": direction,
                    "structural_family": family,
                    "interaction_type": interaction.get("interaction_type"),
                    "level_type": cluster["primary_level_type"],
                    "level_price": cluster["cluster_center"],
                }
                phase4b1 = self._phase4b1_instrumentation(
                    event_seed=event_seed, context=context, strength=strength, cluster=cluster,
                    bars=bar_payloads)
                event = {
                    "id": parent_id,
                    "parent_event_id": parent_id,
                    "ticker": ticker,
                    "trade_date": trade_date,
                    "created_at_utc": created_at.isoformat(),
                    "level_cluster_id": cluster["economic_level_cluster_id"],
                    "economic_level_cluster_id": cluster["economic_level_cluster_id"],
                    "direction": direction,
                    "structural_family": family,
                    "interaction_type": interaction.get("interaction_type"),
                    "approach_direction": interaction.get("approach_direction"),
                    "confirmation_state": interaction.get("confirmation_state"),
                    "level_tier": strength["level_strength_tier"],
                    "level_type": cluster["primary_level_type"],
                    "level_price": cluster["cluster_center"],
                    "interaction_episode": episode_meta["interaction_episode"],
                    **episode_meta,
                    "source_setup_id": setup_payload.get("setup_event_id") if setup_payload else None,
                    "source_observation_id": observation_id,
                    "source_run_id": run_id,
                    "source_mode": source_mode,
                    "source_outcome": outcome,
                    "raw_level_candidates": len(current_levels),
                    "cluster_widths_audited": cluster_audit,
                    "economic_zones": len(economic_clusters),
                    "cluster": {key: value for key, value in cluster.items() if key != "component_levels"},
                    "level_strength": strength,
                    "level_state": strength.get("level_state"),
                    "level_first_seen": strength.get("level_first_seen"),
                    "level_last_seen": strength.get("level_last_seen"),
                    "snapshot_count": strength.get("snapshot_persistence_count"),
                    "age_minutes": strength.get("level_age_minutes"),
                    "strength_now": strength.get("level_strength_score"),
                    "strength_5m": strength.get("strength_change_5m"),
                    "strength_15m": strength.get("strength_change_15m"),
                    "strength_30m": strength.get("strength_change_30m"),
                    "context": context,
                    "phase4b1_diagnostics": phase4b1,
                    "phase4b1_instrumentation_version": phase4b1.get("phase4b1_instrumentation_version"),
                    "direction_class": phase4b1.get("direction_class"),
                    "direction_confidence_0_100": phase4b1.get("direction_confidence_0_100"),
                    "level_role_before": phase4b1.get("level_role_before"),
                    "level_role_after": phase4b1.get("level_role_after"),
                    "structure_alignment": phase4b1.get("structure_alignment"),
                    "planned_entry": self._safe_float(latest.get("close"), 0.0),
                    "structural_stop": structural_stop,
                    "research_only": True,
                    "canonical_setup_count_increment": 0,
                    "parent_event_counts_once": True,
                    "counts_as_empirical_parent": True,
                    "qa_valid_parent_event": True,
                    "qa_status": "POST_FIX",
                    "qa_integrity_version": self.QA_INTEGRITY_VERSION,
                    "forward_instrumentation_version": self.FORWARD_INSTRUMENTATION_VERSION,
                    "strategy_state_source": "LIVE_INTRADAY_OPTIONS",
                }
                existing = self.repository.list_json("intraday_options_edge_events", "WHERE parent_event_id=?",
                                                     (parent_id,), 1)
                if existing:
                    dedup_suppressions += 1
                    continue
                self.repository.store_intraday_edge_event(event)
                events_created += 1
                branches = self._create_branches(event, bar_payloads)
                branches_created += len(branches)
        return {"status": "recorded", "events_created": events_created, "branches_created": branches_created,
                "interactions_seen": interactions_seen, "dedup_suppressions": dedup_suppressions,
                "raw_level_candidates": len(current_levels), "economic_zones": len(economic_clusters),
                "cluster_widths_audited": cluster_audit, "qa_integrity_version": self.QA_INTEGRITY_VERSION}

    def _r_multiple(self, branch: dict[str, Any], price: float) -> float:
        # A planned order is not a fill.  Using planned_entry here caused expired
        # retest orders to manufacture large P/L without ever entering a branch.
        fill = self._safe_float(branch.get("actual_fill_price"), None)
        risk = self._safe_float(branch.get("initial_risk"), None)
        if fill is None or risk in {None, 0}:
            return 0.0
        side = 1 if branch.get("direction") == "LONG" else -1
        return ((price - fill) * side) / risk

    def _append_branch_event(self, branch: dict[str, Any], event_type: str, bar: dict[str, Any],
                             price: float, fraction: float, realized: float, reason: str) -> None:
        branch.setdefault("events", []).append({
            "event_type": event_type,
            "timestamp": bar.get("bar_end_utc"),
            "execution_price": round(price, 6),
            "quantity_fraction": round(fraction, 6),
            "realized_r_event": round(realized, 6),
            "cumulative_r": round((self._safe_float(branch.get("realized_R"), 0.0) or 0.0) + realized, 6),
            "remaining_size": round(max(0.0, (self._safe_float(branch.get("remaining_size"), 0.0) or 0.0) - fraction), 6),
            "reason": reason,
        })
        branch["realized_R"] = branch["events"][-1]["cumulative_r"]
        branch["remaining_size"] = branch["events"][-1]["remaining_size"]
        branch.setdefault("result_R_components", []).append(branch["events"][-1])

    def _management_spec(self, branch: dict[str, Any]) -> dict[str, Any]:
        variant = branch["management_variant"]
        if variant == "M0_CURRENT_MANAGEMENT":
            return {"targets": [(1.0, 0.33, "TP1_PARTIAL"), (1.5, 0.33, "TP2_PARTIAL"), (2.0, 0.34, "TP3_PARTIAL")],
                    "be_after_first": True}
        if variant == "M1_HALF_0_5R_RUNNER":
            return {"targets": [(0.5, 0.5, "M1_HALF_0_5R"), (2.0, 0.5, "M1_RUNNER_EXIT")], "be_after_first": True}
        if variant == "M2_HALF_0_7R_RUNNER":
            return {"targets": [(0.7, 0.5, "M2_HALF_0_7R"), (2.0, 0.5, "M2_RUNNER_EXIT")], "be_after_first": True}
        if variant == "M3_PROTECT_AFTER_1R_NO_PARTIAL":
            return {"targets": [(2.0, 1.0, "M3_RUNNER_EXIT")], "be_after_first": False,
                    "protect_after_R": 1.0}
        if variant == "M4_STRUCTURE_TRAIL_NO_IMMEDIATE_BE":
            return {"targets": [(1.0, 0.33, "M4_STRUCTURE_TP1"), (1.5, 0.33, "M4_STRUCTURE_TP2"), (2.0, 0.34, "M4_STRUCTURE_TP3")],
                    "be_after_first": False, "structure_trail_after_R": 1.0}
        if variant == "TM_FIXED_0_5R":
            return {"targets": [(0.5, 1.0, "FIXED_0_5R")], "be_after_first": False}
        if variant == "TM_FIXED_1R":
            return {"targets": [(1.0, 1.0, "FIXED_1R")], "be_after_first": False}
        if variant == "TM_FIXED_1_5R":
            return {"targets": [(1.5, 1.0, "FIXED_1_5R")], "be_after_first": False}
        if variant == "TM_FIXED_2R":
            return {"targets": [(2.0, 1.0, "FIXED_2R")], "be_after_first": False}
        if variant == "TM_HALF_0_5R_RUNNER":
            return {"targets": [(0.5, 0.5, "HALF_0_5R"), (2.0, 0.5, "RUNNER_2R")], "be_after_first": True}
        if variant == "TM_HALF_1R_RUNNER":
            return {"targets": [(1.0, 0.5, "HALF_1R"), (2.0, 0.5, "RUNNER_2R")], "be_after_first": True}
        if variant == "TM_V3_TP1_PLUS_RUNNER":
            return {"targets": [(1.0, 0.5, "TP1_PARTIAL"), (2.0, 0.5, "RUNNER_EXIT")], "be_after_first": True}
        if variant == "TM_STRUCTURE_TARGETS":
            return {"targets": [(1.0, 0.33, "STRUCTURE_TP1"), (1.5, 0.33, "STRUCTURE_TP2"), (2.0, 0.34, "STRUCTURE_TP3")],
                    "be_after_first": True}
        return {"targets": [(1.0, 0.33, "TP1_PARTIAL"), (1.5, 0.33, "TP2_PARTIAL"), (2.0, 0.34, "TP3_PARTIAL")],
                "be_after_first": True}

    def _mark_stop_tracking(self, branch: dict[str, Any], bar: dict[str, Any], exit_price: float) -> None:
        if not branch.get("phase4b2_experiment_id"):
            return
        bar_end = self._parse_time(bar.get("bar_end_utc"))
        if not bar_end:
            return
        branch["phase4b2_stop_hit_at_utc"] = bar.get("bar_end_utc")
        branch["phase4b2_stop_exit_price"] = round(exit_price, 6)
        branch["phase4b2_post_stop_tracking_active"] = True
        branch["phase4b2_post_stop_track_until_utc"] = (
            bar_end + timedelta(minutes=120)
        ).isoformat()
        branch["phase4b2_after_stop_max_favorable_R"] = 0.0
        branch["phase4b2_after_stop_reached_0_5R"] = False
        branch["phase4b2_after_stop_reached_1R"] = False

    def _update_post_stop_tracking(self, branch: dict[str, Any], bar: dict[str, Any]) -> bool:
        if not branch.get("phase4b2_post_stop_tracking_active"):
            return False
        bar_end = self._parse_time(bar.get("bar_end_utc"))
        until = self._parse_time(branch.get("phase4b2_post_stop_track_until_utc"))
        if not bar_end or not until:
            branch["phase4b2_post_stop_tracking_active"] = False
            return True
        if bar_end > until:
            branch["phase4b2_post_stop_tracking_active"] = False
            return True
        high = self._safe_float(bar.get("high"), 0.0) or 0.0
        low = self._safe_float(bar.get("low"), 0.0) or 0.0
        favorable_price = high if branch.get("direction") == "LONG" else low
        favorable_r = self._r_multiple(branch, favorable_price)
        prior = self._safe_float(branch.get("phase4b2_after_stop_max_favorable_R"), 0.0) or 0.0
        branch["phase4b2_after_stop_max_favorable_R"] = round(max(prior, favorable_r), 6)
        branch["phase4b2_after_stop_reached_0_5R"] = bool(branch.get("phase4b2_after_stop_reached_0_5R") or favorable_r >= 0.5)
        branch["phase4b2_after_stop_reached_1R"] = bool(branch.get("phase4b2_after_stop_reached_1R") or favorable_r >= 1.0)
        return True

    def _apply_phase4b2_protection(self, branch: dict[str, Any], spec: dict[str, Any], bar: dict[str, Any],
                                   favorable_r: float) -> None:
        if not branch.get("phase4b2_experiment_id"):
            return
        fill = self._safe_float(branch.get("actual_fill_price"), None)
        if fill is None:
            return
        if spec.get("protect_after_R") is not None and favorable_r >= float(spec["protect_after_R"]):
            current = self._safe_float(branch.get("stop_current"), branch.get("stop_initial")) or 0.0
            if (branch.get("direction") == "LONG" and current < fill) or (branch.get("direction") == "SHORT" and current > fill):
                branch["stop_current"] = round(fill, 6)
                branch.setdefault("events", []).append({
                    "event_type": "PROTECT_STOP",
                    "timestamp": bar.get("bar_end_utc"),
                    "execution_price": round(fill, 6),
                    "quantity_fraction": 0.0,
                    "realized_r_event": 0.0,
                    "cumulative_r": self._safe_float(branch.get("realized_R"), 0.0) or 0.0,
                    "remaining_size": self._safe_float(branch.get("remaining_size"), 0.0) or 0.0,
                    "reason": "phase4b2_protect_after_1R_no_partial",
                })
        if spec.get("structure_trail_after_R") is not None and favorable_r >= float(spec["structure_trail_after_R"]):
            atr = self._safe_float((branch.get("context") or {}).get("short_term_ATR"), 0.01) or 0.01
            close = self._safe_float(bar.get("close"), fill) or fill
            candidate = round(close - atr * 0.15, 6) if branch.get("direction") == "LONG" else round(close + atr * 0.15, 6)
            current = self._safe_float(branch.get("stop_current"), branch.get("stop_initial")) or candidate
            improved = (branch.get("direction") == "LONG" and candidate > current and candidate < close) or (
                branch.get("direction") == "SHORT" and candidate < current and candidate > close)
            if improved:
                branch["stop_current"] = candidate
                branch.setdefault("events", []).append({
                    "event_type": "STRUCTURE_TRAIL",
                    "timestamp": bar.get("bar_end_utc"),
                    "execution_price": candidate,
                    "quantity_fraction": 0.0,
                    "realized_r_event": 0.0,
                    "cumulative_r": self._safe_float(branch.get("realized_R"), 0.0) or 0.0,
                    "remaining_size": self._safe_float(branch.get("remaining_size"), 0.0) or 0.0,
                    "reason": "phase4b2_structure_based_trailing_no_immediate_be",
                })

    def _close_branch(self, branch: dict[str, Any], bar: dict[str, Any], price: float, reason: str) -> None:
        if self._safe_float(branch.get("actual_fill_price"), None) is None:
            self._censor_unfilled_branch(branch, bar, reason)
            return
        remaining = self._safe_float(branch.get("remaining_size"), 0.0) or 0.0
        if remaining > 0:
            realized = self._r_multiple(branch, price) * remaining
            self._append_branch_event(branch, "EXIT", bar, price, remaining, realized, reason)
        branch["status"] = "closed" if reason not in {"end_of_rth_censor", "pending_order_expiry"} else "censored"
        branch["lifecycle_state"] = self._lifecycle_state(branch["status"])
        branch["qualification_state"] = "QUALIFIED"
        branch["closed_at_utc"] = bar.get("bar_end_utc")
        branch["exit_reason"] = reason
        branch["result_R"] = round(self._safe_float(branch.get("realized_R"), 0.0) or 0.0, 6)
        branch["accounting_integrity_status"] = "VALID_FILLED_RESOLVED"
        opened = self._parse_time(branch.get("opened_at_utc") or branch.get("created_at_utc"))
        closed = self._parse_time(branch.get("closed_at_utc"))
        if opened and closed:
            branch["holding_time_minutes"] = round((closed - opened).total_seconds() / 60, 2)

    def _censor_unfilled_branch(self, branch: dict[str, Any], bar: dict[str, Any], reason: str) -> None:
        """End an unfilled research order without inventing an execution or P/L."""
        branch.setdefault("events", []).append({
            "event_type": "ORDER_EXPIRED_NO_FILL",
            "timestamp": bar.get("bar_end_utc"),
            "execution_price": None,
            "quantity_fraction": 0.0,
            "realized_r_event": None,
            "cumulative_r": None,
            "remaining_size": 0.0,
            "reason": reason,
        })
        branch["status"] = "censored"
        branch["lifecycle_state"] = "CENSORED_NO_ENTRY"
        branch["qualification_state"] = "QUALIFIED_NO_ENTRY"
        branch["counts_as_empirical_branch"] = False
        branch["closed_at_utc"] = bar.get("bar_end_utc")
        branch["exit_reason"] = reason
        branch["remaining_size"] = 0.0
        branch["actual_fill_price"] = None
        branch["realized_R"] = None
        branch["result_R"] = None
        branch["result_R_components"] = []
        branch["MFE"] = None
        branch["MAE"] = None
        branch["holding_time_minutes"] = None
        branch["accounting_integrity_status"] = "VALID_CENSORED_NO_FILL"
        branch["accounting_integrity_version"] = self.ACCOUNTING_INTEGRITY_VERSION

    def _censor_unconfirmed_branch(self, branch: dict[str, Any], bar: dict[str, Any], reason: str) -> None:
        """Close a research registration that never became a qualified setup."""
        branch.setdefault("events", []).append({
            "event_type": "CONFIRMATION_WINDOW_EXPIRED",
            "timestamp": bar.get("bar_end_utc"),
            "execution_price": None,
            "quantity_fraction": 0.0,
            "realized_r_event": None,
            "cumulative_r": None,
            "remaining_size": 0.0,
            "reason": reason,
        })
        branch.update({
            "status": "censored",
            "lifecycle_state": "CENSORED_NOT_QUALIFIED",
            "qualification_state": "NOT_QUALIFIED",
            "counts_as_empirical_branch": False,
            "closed_at_utc": bar.get("bar_end_utc"),
            "exit_reason": reason,
            "remaining_size": 0.0,
            "actual_fill_price": None,
            "realized_R": None,
            "result_R": None,
            "result_R_components": [],
            "MFE": None,
            "MAE": None,
            "holding_time_minutes": None,
            "accounting_integrity_status": "VALID_CENSORED_NOT_QUALIFIED",
            "accounting_integrity_version": self.ACCOUNTING_INTEGRITY_VERSION,
        })

    def _bars_through(self, ticker: str, payload: dict[str, Any], limit: int = 100) -> list[dict[str, Any]]:
        rows = self._recent_bars_for(ticker, self._parse_time(payload.get("bar_end_utc")), limit)
        payload_key = (payload.get("bar_start_utc"), payload.get("bar_end_utc"))
        if payload_key not in {(row.get("bar_start_utc"), row.get("bar_end_utc")) for row in rows}:
            rows.append(payload)
        return sorted(rows, key=lambda row: row.get("bar_end_utc") or "")[-limit:]

    def _update_waiting_confirmation(self, branch: dict[str, Any], payload: dict[str, Any]) -> None:
        bars = self._bars_through(branch["ticker"], payload)
        event = {
            "created_at_utc": branch.get("created_at_utc"),
            "direction": branch.get("direction"),
            "structural_family": branch.get("structural_family"),
            "cluster": branch.get("level_cluster") or {},
        }
        confirmation = self._fifteen_minute_confirmation(event, bars)
        branch["confirmation_15m_latest"] = confirmation
        branch["confirmation_wait_bars"] = int(branch.get("confirmation_wait_bars") or 0) + 1
        if confirmation["confirmed"]:
            branch["status"] = "pending"
            branch["lifecycle_state"] = "PENDING_ENTRY"
            branch["qualification_state"] = "QUALIFIED"
            branch["counts_as_empirical_branch"] = True
            branch["qualified_at_utc"] = confirmation.get("confirmation_bar_end_utc")
            branch["entry_prerequisite_failures"] = [
                reason for reason in branch.get("entry_prerequisite_failures", [])
                if not str(reason).startswith("AWAITING_")
            ]
            branch.setdefault("events", []).append({
                "event_type": "QUALIFIED_15M_CONFIRMATION",
                "timestamp": confirmation.get("confirmation_bar_end_utc"),
                "execution_price": None,
                "quantity_fraction": 0.0,
                "realized_r_event": None,
                "cumulative_r": None,
                "remaining_size": 1.0,
                "reason": "completed exchange-aligned 15m interaction confirmed",
            })
            return
        created = self._parse_time(branch.get("created_at_utc"))
        completed_at = self._parse_time(confirmation.get("confirmation_bar_end_utc"))
        if created and completed_at and completed_at > created:
            self._censor_unconfirmed_branch(branch, payload, "completed_15m_bar_did_not_confirm_interaction")
        elif int(branch.get("confirmation_wait_bars") or 0) >= 4:
            self._censor_unconfirmed_branch(branch, payload, "completed_15m_confirmation_unavailable_within_20m")

    def update_for_bar(self, ticker: str, bar: Bar | dict[str, Any]) -> list[dict[str, Any]]:
        payload = self._bar_dict(bar)
        rows = self.repository.list_json(
            "intraday_options_edge_branches",
            "WHERE ticker=? AND (status IN ('registered','pending','open','partial') OR exit_reason='stop_or_breakeven')",
            (ticker.upper(),),
            10000,
        )
        updates: list[dict[str, Any]] = []
        bar_end = self._parse_time(payload.get("bar_end_utc"))
        if not bar_end:
            return updates
        for branch in rows:
            if branch.get("status") in {"closed", "censored"}:
                if self._update_post_stop_tracking(branch, payload):
                    self.repository.store_intraday_edge_branch(branch)
                    updates.append(branch)
                continue
            created = self._parse_time(branch.get("created_at_utc"))
            if created and created >= bar_end:
                continue
            branch["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
            if branch["status"] == "registered":
                self._update_waiting_confirmation(branch, payload)
                self.repository.store_intraday_edge_branch(branch)
                updates.append(branch)
                # Qualification is known only at this completed bar's close;
                # entry is evaluated on the next completed 5m bar.
                continue
            if branch["status"] == "pending":
                branch["bars_pending"] = int(branch.get("bars_pending") or 0) + 1
                if branch["entry_variant"] in {"ENTRY_1", "ENTRY_4", "ENTRY_5"}:
                    fill = self._safe_float(payload.get("open"), branch.get("planned_entry")) or self._safe_float(branch.get("planned_entry"), 0.0)
                    branch["actual_fill_price"] = round(fill, 6)
                    branch["opened_at_utc"] = payload.get("bar_start_utc") or payload.get("bar_end_utc")
                    branch["status"] = "open"
                    branch["lifecycle_state"] = self._lifecycle_state("open")
                    branch["accounting_integrity_status"] = "VALID_FILLED"
                    branch.setdefault("events", []).append({"event_type": "ENTRY", "timestamp": branch["opened_at_utc"],
                                                            "execution_price": branch["actual_fill_price"],
                                                            "quantity_fraction": 1.0, "realized_r_event": 0.0,
                                                            "cumulative_r": 0.0, "remaining_size": 1.0,
                                                            "reason": "research_next_bar_entry"})
                else:
                    low = self._safe_float(payload.get("low"), 0.0) or 0.0
                    high = self._safe_float(payload.get("high"), 0.0) or 0.0
                    if low <= (self._safe_float(branch.get("entry_zone_high"), 0.0) or 0.0) and high >= (self._safe_float(branch.get("entry_zone_low"), 0.0) or 0.0):
                        fill = self._safe_float(branch.get("planned_entry"), 0.0) or 0.0
                        branch["actual_fill_price"] = round(fill, 6)
                        branch["opened_at_utc"] = payload.get("bar_end_utc")
                        branch["status"] = "open"
                        branch["lifecycle_state"] = self._lifecycle_state("open")
                        branch["accounting_integrity_status"] = "VALID_FILLED"
                        branch.setdefault("events", []).append({"event_type": "ENTRY", "timestamp": branch["opened_at_utc"],
                                                                "execution_price": branch["actual_fill_price"],
                                                                "quantity_fraction": 1.0, "realized_r_event": 0.0,
                                                                "cumulative_r": 0.0, "remaining_size": 1.0,
                                                                "reason": "research_retest_entry"})
                    elif branch["bars_pending"] >= int(self.settings.get("execution.pending_order_expiry_bars", 3)):
                        self._censor_unfilled_branch(branch, payload, "pending_order_expiry")
            if branch["status"] in {"open", "partial"}:
                high = self._safe_float(payload.get("high"), 0.0) or 0.0
                low = self._safe_float(payload.get("low"), 0.0) or 0.0
                close = self._safe_float(payload.get("close"), 0.0) or 0.0
                favorable_price = high if branch.get("direction") == "LONG" else low
                adverse_price = low if branch.get("direction") == "LONG" else high
                favorable_r = self._r_multiple(branch, favorable_price)
                adverse_r = -self._r_multiple(branch, adverse_price)
                if favorable_r > (self._safe_float(branch.get("MFE"), 0.0) or 0.0):
                    branch["MFE"] = round(favorable_r, 6)
                    opened = self._parse_time(branch.get("opened_at_utc"))
                    if opened:
                        branch["time_to_MFE_minutes"] = round((bar_end - opened).total_seconds() / 60, 2)
                branch["MAE"] = round(max(self._safe_float(branch.get("MAE"), 0.0) or 0.0, adverse_r), 6)
                opened = self._parse_time(branch.get("opened_at_utc"))
                if opened:
                    elapsed = (bar_end - opened).total_seconds() / 60
                    for key, target in (("time_to_0_5R_minutes", 0.5), ("time_to_1R_minutes", 1.0),
                                        ("time_to_1_5R_minutes", 1.5), ("time_to_2R_minutes", 2.0)):
                        if branch.get(key) is None and favorable_r >= target:
                            branch[key] = round(elapsed, 2)
                    for label, minutes in (("15m", 15), ("30m", 30), ("60m", 60), ("120m", 120), ("240m", 240)):
                        if elapsed >= minutes and branch["holding_horizon_results_R"].get(label) is None:
                            branch["holding_horizon_results_R"][label] = round(self._r_multiple(branch, close), 6)
                stop = self._safe_float(branch.get("stop_current"), branch.get("stop_initial")) or 0.0
                stop_hit = low <= stop if branch.get("direction") == "LONG" else high >= stop
                if stop_hit:
                    self._mark_stop_tracking(branch, payload, stop)
                    self._close_branch(branch, payload, stop, "stop_or_breakeven")
                else:
                    spec = self._management_spec(branch)
                    targets_hit = {event.get("event_type") for event in branch.get("events", [])}
                    for target_r, fraction, event_type in spec["targets"]:
                        if event_type in targets_hit:
                            continue
                        target_price = branch["targets"][0] if target_r == 0.5 and branch.get("targets") else None
                        fill = target_price if target_price is not None and event_type == "FIXED_0_5R" else None
                        if fill is None:
                            fill = (self._safe_float(branch.get("actual_fill_price"), 0.0) or 0.0) + (
                                (1 if branch.get("direction") == "LONG" else -1)
                                * (self._safe_float(branch.get("initial_risk"), 0.0) or 0.0)
                                * target_r
                            )
                        target_touched = high >= fill if branch.get("direction") == "LONG" else low <= fill
                        if not target_touched:
                            continue
                        remaining = self._safe_float(branch.get("remaining_size"), 0.0) or 0.0
                        qty = min(remaining, fraction)
                        if qty <= 0:
                            continue
                        realized = target_r * qty
                        self._append_branch_event(branch, event_type, payload, fill, qty, realized, "research_target")
                        branch["status"] = "partial" if branch["remaining_size"] > 0 else "closed"
                        branch["lifecycle_state"] = self._lifecycle_state(branch["status"])
                        if spec.get("be_after_first"):
                            branch["stop_current"] = branch.get("actual_fill_price")
                        if branch["remaining_size"] <= 0:
                            branch["closed_at_utc"] = payload.get("bar_end_utc")
                            branch["exit_reason"] = event_type
                            branch["result_R"] = round(self._safe_float(branch.get("realized_R"), 0.0) or 0.0, 6)
                            break
                    if branch["status"] in {"open", "partial"}:
                        self._apply_phase4b2_protection(branch, spec, payload, favorable_r)
                local_time = bar_end.astimezone(EASTERN).time()
                if branch["status"] in {"open", "partial"} and local_time >= time(15, 55):
                    branch["holding_horizon_results_R"]["end_of_RTH"] = round(self._r_multiple(branch, close), 6)
                    self._close_branch(branch, payload, close, "end_of_rth_censor")
            self.repository.store_intraday_edge_branch(branch)
            updates.append(branch)
        return updates

    def _summary(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        resolved = [row for row in rows if row.get("status") in self.RESOLVED_STATUSES and row.get("result_R") is not None]
        values = [self._safe_float(row.get("result_R"), 0.0) or 0.0 for row in resolved]
        wins = [value for value in values if value > 0]
        losses = [value for value in values if value < 0]
        days = sorted({(row.get("context") or {}).get("trade_date") or row.get("created_at_utc", "")[:10] for row in resolved})
        curve = []
        total = 0.0
        for value in values:
            total += value
            curve.append(total)
        peak, max_dd = 0.0, 0.0
        for value in curve:
            peak = max(peak, value)
            max_dd = min(max_dd, value - peak)
        pf = None if not losses else round(sum(wins) / abs(sum(losses)), 4)
        if wins and not losses:
            pf = "infinite"
        status = self._sample_status(len(values), len(days))
        return {
            "N": len(values),
            "unique_trading_days": len(days),
            "expectancy": round(sum(values) / len(values), 4) if values else 0.0,
            "median_R": round(median(values), 4) if values else 0.0,
            "profit_factor": pf,
            "win_rate": round(len(wins) / len(values), 4) if values else 0.0,
            "avg_winner": round(sum(wins) / len(wins), 4) if wins else 0.0,
            "avg_loser": round(sum(losses) / len(losses), 4) if losses else 0.0,
            "MFE": round(sum((self._safe_float(row.get("MFE"), 0.0) or 0.0) for row in resolved) / len(resolved), 4) if resolved else 0.0,
            "MAE": round(sum((self._safe_float(row.get("MAE"), 0.0) or 0.0) for row in resolved) / len(resolved), 4) if resolved else 0.0,
            "max_DD": round(max_dd, 4),
            "P_0_5R_before_minus_1R": round(sum(1 for row in resolved if (self._safe_float(row.get("MFE"), 0.0) or 0.0) >= 0.5) / len(resolved), 4) if resolved else 0.0,
            "P_1R_before_minus_1R": round(sum(1 for row in resolved if (self._safe_float(row.get("MFE"), 0.0) or 0.0) >= 1.0) / len(resolved), 4) if resolved else 0.0,
            "P_1_5R_before_minus_1R": round(sum(1 for row in resolved if (self._safe_float(row.get("MFE"), 0.0) or 0.0) >= 1.5) / len(resolved), 4) if resolved else 0.0,
            "sample_status": status,
        }

    @staticmethod
    def _sample_status(n: int, days: int) -> str:
        if days < 5:
            return "INSUFFICIENT_DAYS"
        if n < 30:
            return "INSUFFICIENT_SAMPLE"
        if days < 10 or n < 75:
            return "EXPLORATORY"
        if days < 20 or n < 150:
            return "PRELIMINARY"
        return "STATISTICALLY_USEFUL"

    def _grouped(self, rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            value = row.get(key)
            if value is None and key in {"direction", "structural_family", "level_type", "level_tier"}:
                value = row.get("context", {}).get(key)
            groups[str(value or "UNKNOWN")].append(row)
        result = []
        for label, items in sorted(groups.items()):
            result.append({"bucket": label, **self._summary(items)})
        return result

    def _filter_by_report_date(self, rows: list[dict[str, Any]], report_date: str | None) -> list[dict[str, Any]]:
        if not report_date:
            return rows
        result = []
        for row in rows:
            context = row.get("context") or {}
            row_date = context.get("trade_date") or row.get("trade_date")
            if not row_date:
                created = self._parse_time(row.get("created_at_utc"))
                row_date = created.astimezone(EASTERN).date().isoformat() if created else None
            if row_date == report_date:
                result.append(row)
        return result

    @staticmethod
    def _not_qa_pre_fix(row: dict[str, Any]) -> bool:
        labels = {
            str(row.get("qa_status") or "").upper(),
            str(row.get("status") or "").upper(),
            str(row.get("accounting_integrity_status") or "").upper(),
        }
        return not labels.intersection({
            "QA_PRE_FIX",
            "ACCOUNTING_INVALID_PRE_FIX",
            "INVALID_NO_FILL_REPORTED_RESULT",
        })

    def _after_activation_cutoff(self, row: dict[str, Any], activation: dict[str, Any] | None) -> bool:
        if not activation:
            return True
        cutoff = self._parse_time(
            activation.get("clean_forward_cutoff_utc") or activation.get("activated_at_utc")
        )
        created = self._parse_time(row.get("created_at_utc"))
        return not cutoff or not created or created >= cutoff

    def status(self, report_date: str | None = None) -> dict[str, Any]:
        activation = self.activate()
        cutoff = (activation or {}).get("clean_forward_cutoff_utc") or (activation or {}).get("activated_at_utc")
        where = "WHERE created_at_utc>=?" if cutoff else ""
        params = (cutoff,) if cutoff else ()
        events = self._filter_by_report_date(
            self.repository.list_json("intraday_options_edge_events", where, params, limit=100000), report_date)
        events = [row for row in events if self._not_qa_pre_fix(row) and self._after_activation_cutoff(row, activation)]
        branches = self._filter_by_report_date(
            self.repository.list_json("intraday_options_edge_branches", where, params, limit=100000), report_date)
        branches = [row for row in branches if self._not_qa_pre_fix(row) and self._after_activation_cutoff(row, activation)]
        branches = [row for row in branches if not row.get("phase4b2_experiment_id")]
        resolved = [row for row in branches if row.get("status") in self.RESOLVED_STATUSES and row.get("result_R") is not None]
        options_rows = [row for row in branches if not row.get("is_control")]
        control_rows = [row for row in branches if row.get("is_control")]
        variant_summaries = []
        for variant, items in sorted(defaultdict(list, {
            variant: [row for row in options_rows if row.get("strategy_variant") == variant]
            for variant in self.VARIANT_SPECS
        }).items()):
            variant_summaries.append({"strategy_variant": variant, **self._summary(items)})
        control_summary = self._summary(control_rows)
        options_summary = self._summary(options_rows)
        core = [
            row for row in branches
            if row.get("entry_variant") == "ENTRY_1"
            and row.get("management_variant") in self.CORE_MANAGEMENT_VARIANTS
            and row.get("stop_variant") == "STOP_A_CURRENT_STRUCTURAL"
        ]
        def summary_for(**criteria: Any) -> dict[str, Any]:
            return self._summary([row for row in core if all(row.get(key) == value for key, value in criteria.items())])
        dashboard = {
            "variant_A_expectancy": summary_for(strategy_variant="VARIANT_A_5M_BASELINE")["expectancy"],
            "variant_B_expectancy": summary_for(strategy_variant="VARIANT_B_15M_CONFIRM_5M_ENTRY")["expectancy"],
            "variant_C_expectancy": summary_for(strategy_variant="VARIANT_C_PERSISTENT_5M")["expectancy"],
            "variant_D_expectancy": summary_for(strategy_variant="VARIANT_D_PERSISTENT_15M_5M")["expectancy"],
            "five_min_confirmation": self._summary([row for row in core if row.get("confirmation_tf") == "5m" and not row.get("is_control")]),
            "fifteen_min_confirmation": self._summary([row for row in core if row.get("confirmation_tf") == "15m" and not row.get("is_control")]),
            "persistent_levels": self._summary([row for row in core if row.get("strategy_variant") in {"VARIANT_C_PERSISTENT_5M", "VARIANT_D_PERSISTENT_15M_5M"}]),
            "raw_levels": self._summary([row for row in core if row.get("strategy_variant") in {"VARIANT_A_5M_BASELINE", "VARIANT_B_15M_CONFIRM_5M_ENTRY"}]),
            "long": self._summary([row for row in core if row.get("direction") == "LONG" and not row.get("is_control")]),
            "short": self._summary([row for row in core if row.get("direction") == "SHORT" and not row.get("is_control")]),
            "reclaim": self._summary([row for row in core if row.get("structural_family") == "RECLAIM" and not row.get("is_control")]),
            "rejection": self._summary([row for row in core if row.get("structural_family") == "REJECTION" and not row.get("is_control")]),
            "breakout": self._summary([row for row in core if row.get("structural_family") == "LEVEL_BREAKOUT" and not row.get("is_control")]),
            "options_vs_controls": {"options": options_summary, "matched_controls": control_summary},
        }
        best = max(variant_summaries, key=lambda item: (item["N"] > 0, item["expectancy"]), default=None)
        dashboard["best_research_variant"] = best["strategy_variant"] if best else None
        dashboard["best_research_variant_expectancy"] = best["expectancy"] if best else 0.0
        dashboard["unique_trading_days"] = len({row.get("trade_date") for row in events})
        dashboard["sample_status"] = self._sample_status(len(resolved), dashboard["unique_trading_days"])
        return {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "report_date": report_date,
            "activation": activation,
            "research_only": True,
            "canonical_strategy_unchanged": True,
            "live_trading_disabled": True,
            "portfolio_os_isolated": True,
            "counts": {
                "parent_events": len(events),
                "branches": len(branches),
                "resolved_branches": len(resolved),
                "active_branches": sum(row.get("status") in self.ACTIVE_STATUSES for row in branches),
                "registered_awaiting_confirmation": sum(row.get("status") == "registered" for row in branches),
                "not_qualified_branches": sum(row.get("status") == "not_qualified" for row in branches),
                "qualified_branches": sum(row.get("qualification_state") == "QUALIFIED" for row in branches),
                "lifecycle": dict(Counter(row.get("lifecycle_state") or self._lifecycle_state(row.get("status")) for row in branches)),
                "control_branches": len(control_rows),
            },
            "dashboard": dashboard,
            "variant_summaries": variant_summaries,
            "by_direction": self._grouped(core, "direction"),
            "by_structural_family": self._grouped(core, "structural_family"),
            "by_level_type": self._grouped(core, "level_type"),
            "by_level_tier": self._grouped(core, "level_tier"),
            "by_management": self._grouped(core, "management_variant"),
            "by_stop_variant": self._grouped([row for row in branches if row.get("strategy_variant") == "VARIANT_D_PERSISTENT_15M_5M"], "stop_variant"),
        }

    def _phase4b2_rows(self, report_date: str | None = None) -> list[dict[str, Any]]:
        activation = self.phase4b2_activation()
        cutoff = (activation or {}).get("clean_forward_cutoff_utc") or (activation or {}).get("activated_at_utc")
        where = "WHERE created_at_utc>=?" if cutoff else ""
        params = (cutoff,) if cutoff else ()
        rows = self._filter_by_report_date(
            self.repository.list_json("intraday_options_edge_branches", where, params, limit=100000),
            report_date,
        )
        rows = [
            row for row in rows
            if self._not_qa_pre_fix(row) and self._after_activation_cutoff(row, activation)
        ]
        return [row for row in rows if row.get("phase4b2_experiment_id")]

    def _phase4b2_summary(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        base = self._summary(rows)
        resolved = [row for row in rows if row.get("status") in self.RESOLVED_STATUSES and row.get("result_R") is not None]
        stopped = [row for row in resolved if "stop" in str(row.get("exit_reason") or "").lower()]
        stopped_recovered_05 = [row for row in stopped if row.get("phase4b2_after_stop_reached_0_5R")]
        stopped_recovered_1 = [row for row in stopped if row.get("phase4b2_after_stop_reached_1R")]
        mfe_positive_losses = [row for row in resolved if (self._safe_float(row.get("result_R"), 0.0) or 0.0) < 0]
        capture_values = []
        givebacks = []
        be_exits = 0
        runner_r = 0.0
        tp1_hits = 0
        for row in resolved:
            result = self._safe_float(row.get("result_R"), None)
            mfe = self._safe_float(row.get("MFE"), 0.0) or 0.0
            if result is not None and mfe > 0:
                capture_values.append(result / mfe)
                givebacks.append(max(0.0, mfe - result))
            events = row.get("events") or []
            if any("BE" in str(event.get("reason") or event.get("event_type") or "").upper() or "BREAKEVEN" in str(event.get("reason") or "").upper() for event in events):
                be_exits += 1
            if any("RUNNER" in str(event.get("event_type") or "") for event in events):
                runner_r += sum(self._safe_float(event.get("realized_r_event"), 0.0) or 0.0 for event in events if "RUNNER" in str(event.get("event_type") or ""))
            if any("TP1" in str(event.get("event_type") or "") or "0_5R" in str(event.get("event_type") or "") or "0_7R" in str(event.get("event_type") or "") for event in events):
                tp1_hits += 1
        base.update({
            "stop_frequency": round(len(stopped) / len(resolved), 4) if resolved else 0.0,
            "stop_then_recovery": round(len([row for row in stopped if (self._safe_float(row.get("phase4b2_after_stop_max_favorable_R"), 0.0) or 0.0) > 0]) / len(stopped), 4) if stopped else 0.0,
            "stopped_later_reached_0_5R": round(len(stopped_recovered_05) / len(stopped), 4) if stopped else 0.0,
            "stopped_later_reached_1R": round(len(stopped_recovered_1) / len(stopped), 4) if stopped else 0.0,
            "reached_0_5R_then_negative": round(sum(1 for row in mfe_positive_losses if (self._safe_float(row.get("MFE"), 0.0) or 0.0) >= 0.5) / len(mfe_positive_losses), 4) if mfe_positive_losses else 0.0,
            "reached_0_7R_then_negative": round(sum(1 for row in mfe_positive_losses if (self._safe_float(row.get("MFE"), 0.0) or 0.0) >= 0.7) / len(mfe_positive_losses), 4) if mfe_positive_losses else 0.0,
            "reached_1R_then_negative": round(sum(1 for row in mfe_positive_losses if (self._safe_float(row.get("MFE"), 0.0) or 0.0) >= 1.0) / len(mfe_positive_losses), 4) if mfe_positive_losses else 0.0,
            "capture_efficiency": round(sum(capture_values) / len(capture_values), 4) if capture_values else 0.0,
            "giveback_R": round(sum(givebacks) / len(givebacks), 4) if givebacks else 0.0,
            "BE_frequency": round(be_exits / len(resolved), 4) if resolved else 0.0,
            "runner_contribution_R": round(runner_r, 4),
            "TP1_frequency": round(tp1_hits / len(resolved), 4) if resolved else 0.0,
        })
        return base

    def _phase4b2_grouped(self, rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            groups[str(row.get(key) or "UNKNOWN")].append(row)
        result = []
        for label, items in sorted(groups.items()):
            result.append({"bucket": label, **self._phase4b2_summary(items)})
        return result

    def _phase4b2_paired(self, rows: list[dict[str, Any]], left_branch: str,
                         right_branch: str) -> dict[str, Any]:
        resolved = [
            row for row in rows
            if row.get("result_R") is not None and row.get("status") in self.RESOLVED_STATUSES
        ]
        left = {row.get("parent_event_id"): row for row in resolved if row.get("phase4b2_branch") == left_branch}
        right = {row.get("parent_event_id"): row for row in resolved if row.get("phase4b2_branch") == right_branch}
        parent_ids = sorted(set(left).intersection(right) - {None})
        left_rows = [left[parent_id] for parent_id in parent_ids]
        right_rows = [right[parent_id] for parent_id in parent_ids]
        left_summary = self._phase4b2_summary(left_rows)
        right_summary = self._phase4b2_summary(right_rows)
        return {
            "left_branch": left_branch,
            "right_branch": right_branch,
            "paired_parent_N": len(parent_ids),
            "unique_trading_days": len({
                (left[parent_id].get("context") or {}).get("trade_date")
                or left[parent_id].get("created_at_utc", "")[:10]
                for parent_id in parent_ids
            }),
            "left": left_summary,
            "right": right_summary,
            "expectancy_delta_right_minus_left": round(
                float(right_summary["expectancy"]) - float(left_summary["expectancy"]), 4
            ) if parent_ids else None,
            "pairing_rule": "same_parent_event_resolved_in_both_branches",
        }

    def phase4b2_status(self, report_date: str | None = None) -> dict[str, Any]:
        activation = self.activate_phase4b2()
        rows = self._phase4b2_rows(report_date)
        resolved = [row for row in rows if row.get("status") in self.RESOLVED_STATUSES and row.get("result_R") is not None]
        parent_ids = {row.get("parent_event_id") for row in rows if row.get("parent_event_id")}
        resolved_parent_ids = {row.get("parent_event_id") for row in resolved if row.get("parent_event_id")}
        resolved_days = {(row.get("context") or {}).get("trade_date") or row.get("created_at_utc", "")[:10] for row in resolved}
        collection_days = {
            (row.get("context") or {}).get("trade_date") or row.get("created_at_utc", "")[:10]
            for row in rows
        }
        collection_days.discard("")
        by_experiment = self._phase4b2_grouped(rows, "phase4b2_experiment_id")
        stop = [row for row in rows if row.get("phase4b2_experiment_id") == "EXPERIMENT_1_INVALIDATION_STOP"]
        management = [row for row in rows if row.get("phase4b2_experiment_id") == "EXPERIMENT_2_PROFIT_PROTECTION"]
        options_value = [row for row in rows if row.get("phase4b2_experiment_id") == "EXPERIMENT_3_OPTIONS_VALUE"]
        stop_by_branch = self._phase4b2_grouped(stop, "stop_variant")
        management_by_branch = self._phase4b2_grouped(management, "management_variant")
        options_by_branch = self._phase4b2_grouped(options_value, "phase4b2_branch")
        p0 = next((row for row in options_by_branch if row["bucket"] == "P0"), None)
        p1 = next((row for row in options_by_branch if row["bucket"] == "P1"), None)
        p3 = next((row for row in options_by_branch if row["bucket"] == "P3"), None)
        p4 = next((row for row in options_by_branch if row["bucket"] == "P4"), None)
        p4_vs_p0 = self._phase4b2_paired(options_value, "P0", "P4")
        p4_vs_p0_expectancy_delta = p4_vs_p0["expectancy_delta_right_minus_left"]
        milestone_status = "INSTRUMENTATION_PENDING"
        if len(collection_days) >= 20:
            milestone_status = "PRIMARY_DECISION_POINT_READY"
        elif len(collection_days) >= 10:
            milestone_status = "PRELIMINARY_10_DAY"
        elif len(collection_days) >= 5:
            milestone_status = "EXPLORATORY_5_DAY"
        best_stop = max((item for item in stop_by_branch if item["N"] > 0),
                        key=lambda item: (item["N"], item["expectancy"]), default=None)
        best_management = max((item for item in management_by_branch if item["N"] > 0),
                              key=lambda item: (item["N"], item["expectancy"]), default=None)
        dashboard = {
            "milestone_status": milestone_status,
            "parent_events": len(parent_ids),
            "resolved_parent_events": len(resolved_parent_ids),
            "unique_trading_days": len(collection_days),
            "resolved_trading_days": len(resolved_days),
            "S0_expectancy": next((row["expectancy"] for row in stop_by_branch if row["bucket"] == "S0_CANONICAL_STOP"), 0.0),
            "S1_expectancy": next((row["expectancy"] for row in stop_by_branch if row["bucket"] == "S1_FULL_OPTIONS_LEVEL_ZONE_INVALIDATION"), 0.0),
            "S2_expectancy": next((row["expectancy"] for row in stop_by_branch if row["bucket"] == "S2_15M_STRUCTURAL_INVALIDATION"), 0.0),
            "S3_expectancy": next((row["expectancy"] for row in stop_by_branch if row["bucket"] == "S3_LAST_CONFIRMED_HL_LH_INVALIDATION"), 0.0),
            "best_stop_branch": best_stop["bucket"] if best_stop else "NONE_YET",
            "M0_expectancy": next((row["expectancy"] for row in management_by_branch if row["bucket"] == "M0_CURRENT_MANAGEMENT"), 0.0),
            "M1_expectancy": next((row["expectancy"] for row in management_by_branch if row["bucket"] == "M1_HALF_0_5R_RUNNER"), 0.0),
            "M2_expectancy": next((row["expectancy"] for row in management_by_branch if row["bucket"] == "M2_HALF_0_7R_RUNNER"), 0.0),
            "M3_expectancy": next((row["expectancy"] for row in management_by_branch if row["bucket"] == "M3_PROTECT_AFTER_1R_NO_PARTIAL"), 0.0),
            "M4_expectancy": next((row["expectancy"] for row in management_by_branch if row["bucket"] == "M4_STRUCTURE_TRAIL_NO_IMMEDIATE_BE"), 0.0),
            "best_management_branch": best_management["bucket"] if best_management else "NONE_YET",
            "P0_expectancy": p0["expectancy"] if p0 else 0.0,
            "P4_expectancy": p4["expectancy"] if p4 else 0.0,
            "P4_vs_P0_expectancy_delta": p4_vs_p0_expectancy_delta,
            "options_value_adds_edge": bool(
                p4_vs_p0["paired_parent_N"] >= 30
                and p4_vs_p0["unique_trading_days"] >= 5
                and p4_vs_p0_expectancy_delta is not None
                and p4_vs_p0_expectancy_delta > 0
            ),
            "options_value_test_scope": "incremental_options_metadata_on_same_zone",
            "options_level_location_edge_proven": False,
            "BAD_STOP_causality_status": "INSUFFICIENT_FORWARD_SAMPLE" if len(collection_days) < 5 else "EXPLORATORY",
            "profit_protection_status": "INSUFFICIENT_FORWARD_SAMPLE" if len(collection_days) < 5 else "EXPLORATORY",
            "options_value_status": "INSUFFICIENT_FORWARD_SAMPLE" if len(collection_days) < 5 else "EXPLORATORY",
        }
        answers = {
            "is_BAD_STOP_causal": "INSUFFICIENT_FORWARD_SAMPLE" if len(collection_days) < 5 else "EXPLORATORY_ASSOCIATION_ONLY",
            "which_invalidation_preserves_winners": dashboard["best_stop_branch"],
            "are_excursions_given_back_systematically": "INSUFFICIENT_FORWARD_SAMPLE" if len(collection_days) < 5 else "SEE_PROFIT_PROTECTION_BRANCHES",
            "does_profit_protection_improve_expectancy": "INSUFFICIENT_FORWARD_SAMPLE" if len(collection_days) < 5 else dashboard["best_management_branch"],
            "does_15m_structure_improve_entries": "INSUFFICIENT_FORWARD_SAMPLE"
            if not (p3 and p4 and p3["N"] >= 30 and p4["N"] >= 30 and len(collection_days) >= 5)
            else p4["expectancy"] > p3["expectancy"],
            "does_direction_classifier_improve_selection": "INSUFFICIENT_FORWARD_SAMPLE"
            if not (p1 and p3 and p1["N"] >= 30 and p3["N"] >= 30 and len(collection_days) >= 5)
            else p3["expectancy"] > p1["expectancy"],
            "does_options_plus_structure_outperform_structure_only": "INSUFFICIENT_FORWARD_SAMPLE"
            if p4_vs_p0["paired_parent_N"] < 30 or p4_vs_p0["unique_trading_days"] < 5
            else p4_vs_p0_expectancy_delta > 0,
            "options_value_interpretation_limit": (
                "P0 masks options identity on the same zone; P0-P4 tests incremental options metadata/qualification, "
                "not whether options-selected zone locations beat independently matched non-options zones."
            ),
        }
        return {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "report_date": report_date,
            "activation": activation,
            "phase": "4B2_PROSPECTIVE_EXECUTION_OPTIONS_VALUE_VALIDATION",
            "research_only": True,
            "canonical_strategy_unchanged": True,
            "live_trading_disabled": True,
            "portfolio_os_isolated": True,
            "counts": {
                "branches": len(rows),
                "resolved_branches": len(resolved),
                "parent_events": len(parent_ids),
                "resolved_parent_events": len(resolved_parent_ids),
                "unique_trading_days": len(collection_days),
                "resolved_trading_days": len(resolved_days),
                "active_branches": sum(row.get("status") in self.ACTIVE_STATUSES for row in rows),
                "registered_awaiting_confirmation": sum(row.get("status") == "registered" for row in rows),
                "not_qualified_branches": sum(row.get("status") == "not_qualified" for row in rows),
                "qualified_branches": sum(row.get("qualification_state") == "QUALIFIED" for row in rows),
                "lifecycle": dict(Counter(row.get("lifecycle_state") or self._lifecycle_state(row.get("status")) for row in rows)),
            },
            "dashboard": dashboard,
            "answers": answers,
            "by_experiment": by_experiment,
            "stop_experiment": stop_by_branch,
            "profit_protection_experiment": management_by_branch,
            "options_value_experiment": options_by_branch,
            "options_value_paired_P0_vs_P4": p4_vs_p0,
        }

    def generate_phase4b2_report(self, report_date: str | None = None) -> dict[str, Any]:
        status = self.phase4b2_status(report_date)
        rows = self._phase4b2_rows(report_date)
        if report_date:
            output_dir = self.output_root / "reports" / report_date
            report_path = output_dir / "phase4b2_prospective_execution_options_value.md"
        else:
            output_dir = self.output_root
            report_path = output_dir / "PHASE_4B2_PROSPECTIVE_EXECUTION_OPTIONS_VALUE.md"
        output_dir.mkdir(parents=True, exist_ok=True)
        stop_csv = output_dir / "phase4b2_stop_experiment.csv"
        management_csv = output_dir / "phase4b2_profit_protection.csv"
        options_csv = output_dir / "phase4b2_options_value.csv"
        branches_csv = output_dir / "phase4b2_research_branches.csv"
        self._write_csv(branches_csv, [self._compact_branch_export(row) for row in rows])
        self._write_csv(stop_csv, status["stop_experiment"])
        self._write_csv(management_csv, status["profit_protection_experiment"])
        self._write_csv(options_csv, status["options_value_experiment"])

        def table(items: list[dict[str, Any]]) -> str:
            if not items:
                return "| - | 0 | 0 | 0 | 0 | 0 | 0 | 0 |\n"
            return "\n".join(
                f"| {item.get('bucket')} | {item['N']} | {item['unique_trading_days']} | "
                f"{item['expectancy']} | {item['profit_factor']} | {item['win_rate']:.1%} | "
                f"{item.get('stop_frequency', 0):.1%} | {item['sample_status']} |"
                for item in items
            )

        answers = status["answers"]
        dashboard = status["dashboard"]
        markdown = f"""# Phase 4B.2 Prospective Execution & Options-Value Validation

Generated: {status['generated_at_utc']}

Activation cutoff: {status['activation']['activated_at_utc']}

This is prospective research only. Canonical strategy logic, score thresholds, stops, targets, management, watchlist, provider gates, Production Paper rules, live-trading disabled state, and Portfolio OS isolation were not changed.

## Milestone status

- Unique parent events: {status['counts']['parent_events']}
- Resolved parent events: {status['counts']['resolved_parent_events']}
- Research branches: {status['counts']['branches']}
- Resolved/censored branches: {status['counts']['resolved_branches']}
- Unique RTH days: {status['counts']['unique_trading_days']}
- Milestone: {dashboard['milestone_status']}

## Required milestone questions

1. Is BAD_STOP causal or merely associated? `{answers['is_BAD_STOP_causal']}`
2. Which invalidation preserves winners without exploding losses? `{answers['which_invalidation_preserves_winners']}`
3. Are +0.5/+0.7/+1R excursions being given back systematically? `{answers['are_excursions_given_back_systematically']}`
4. Does profit protection improve expectancy? `{answers['does_profit_protection_improve_expectancy']}`
5. Does 15m structure improve entries? `{answers['does_15m_structure_improve_entries']}`
6. Does the level-direction classifier improve direction selection? `{answers['does_direction_classifier_improve_selection']}`
7. Does OPTIONS + STRUCTURE outperform STRUCTURE ONLY? `{answers['does_options_plus_structure_outperform_structure_only']}`

## Experiment 1 — invalidation / stop

| branch | N | days | expectancy | PF | win rate | stop freq | status |
|---|---:|---:|---:|---:|---:|---:|---|
{table(status['stop_experiment'])}

## Experiment 2 — profit protection

| branch | N | days | expectancy | PF | win rate | stop freq | status |
|---|---:|---:|---:|---:|---:|---:|---|
{table(status['profit_protection_experiment'])}

## Experiment 3 — options value

Primary comparison: P4 versus P0.

- P0 expectancy: {dashboard['P0_expectancy']}
- P4 expectancy: {dashboard['P4_expectancy']}
- P4 - P0 delta: {dashboard['P4_vs_P0_expectancy_delta']}
- Options value status: {dashboard['options_value_status']}

| branch | N | days | expectancy | PF | win rate | stop freq | status |
|---|---:|---:|---:|---:|---:|---:|---|
{table(status['options_value_experiment'])}

## Safety

- No automatic promotion.
- No canonical changes.
- Live trading remains disabled.
- Portfolio OS remains isolated.
- Branches share parent event IDs and do not create duplicate empirical setup counts.
"""
        report_path.write_text(markdown, encoding="utf-8")
        return {
            "generated_at_utc": status["generated_at_utc"],
            "markdown_path": str(report_path),
            "branch_csv": str(branches_csv),
            "stop_csv": str(stop_csv),
            "profit_protection_csv": str(management_csv),
            "options_value_csv": str(options_csv),
            "report": status,
        }

    def _rth_window_for_date(self, report_date: str) -> tuple[str, str]:
        local_date = datetime.fromisoformat(report_date).date()
        start = datetime.combine(local_date, time(9, 30), EASTERN).astimezone(timezone.utc)
        end = datetime.combine(local_date, time(16, 0), EASTERN).astimezone(timezone.utc)
        return start.isoformat(), end.isoformat()

    def _fetch_sql_rows(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        with self.repository.connect() as connection:
            return [dict(row) for row in connection.execute(sql, params).fetchall()]

    def _count_sql(self, sql: str, params: tuple[Any, ...]) -> int:
        with self.repository.connect() as connection:
            return int(connection.execute(sql, params).fetchone()[0])

    def _mark_phase4_research_prefix(self, start_utc: str, end_utc: str) -> dict[str, int]:
        marked_at = datetime.now(timezone.utc).isoformat()

        def mark_payload(payload: str, *, branch: bool) -> str:
            try:
                data = json.loads(payload or "{}")
            except json.JSONDecodeError:
                data = {"unparseable_pre_fix_payload": True}
            data["qa_status"] = "QA_PRE_FIX"
            data["qa_marked_at_utc"] = marked_at
            data["qa_reason"] = "Phase 4B.2-QA identified pre-fix research event/branch inflation risk."
            data["qa_integrity_version"] = self.QA_INTEGRITY_VERSION
            if branch:
                data["status"] = "qa_pre_fix"
                data["lifecycle_state"] = "QA_PRE_FIX"
                data["qualification_state"] = "NOT_QUALIFIED"
                data["counts_as_empirical_branch"] = False
            else:
                data["counts_as_empirical_parent"] = False
                data["qa_valid_parent_event"] = False
            return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)

        def op(connection) -> dict[str, int]:
            event_rows = connection.execute(
                """SELECT id, normalized_json FROM intraday_options_edge_events
                   WHERE created_at_utc>=? AND created_at_utc<?
                   AND normalized_json NOT LIKE '%"qa_status":"QA_PRE_FIX"%'""",
                (start_utc, end_utc),
            ).fetchall()
            branch_rows = connection.execute(
                """SELECT id, normalized_json FROM intraday_options_edge_branches
                   WHERE created_at_utc>=? AND created_at_utc<?
                   AND status!='qa_pre_fix'""",
                (start_utc, end_utc),
            ).fetchall()
            connection.executemany(
                "UPDATE intraday_options_edge_events SET normalized_json=? WHERE id=?",
                [(mark_payload(row["normalized_json"], branch=False), row["id"]) for row in event_rows],
            )
            connection.executemany(
                "UPDATE intraday_options_edge_branches SET status='qa_pre_fix', updated_at_utc=?, normalized_json=? WHERE id=?",
                [(marked_at, mark_payload(row["normalized_json"], branch=True), row["id"]) for row in branch_rows],
            )
            return {"events_marked": len(event_rows), "branches_marked": len(branch_rows)}

        return self.repository._write_with_retry(op)

    def reconcile_no_fill_accounting(self) -> dict[str, Any]:
        """Quarantine pre-fix branches that reported P/L without an actual fill.

        The original values are retained inside the JSON audit envelope.  These
        rows remain in SQLite, but are excluded from every empirical statistic.
        Canonical paper trades and parent events are not touched.
        """
        marked_at = datetime.now(timezone.utc).isoformat()

        def op(connection) -> dict[str, int]:
            rows = connection.execute(
                """SELECT id, status, result_R, MFE, MAE, holding_time_minutes,
                          exit_reason, normalized_json
                   FROM intraday_options_edge_branches
                   WHERE status!='qa_pre_fix'
                     AND exit_reason='pending_order_expiry'
                     AND json_extract(normalized_json,'$.actual_fill_price') IS NULL
                     AND result_R IS NOT NULL"""
            ).fetchall()
            updates = []
            for row in rows:
                try:
                    data = json.loads(row["normalized_json"] or "{}")
                except json.JSONDecodeError:
                    data = {"unparseable_accounting_pre_fix_payload": True}
                data["accounting_pre_fix_original"] = {
                    "status": row["status"],
                    "result_R": row["result_R"],
                    "realized_R": data.get("realized_R"),
                    "MFE": row["MFE"],
                    "MAE": row["MAE"],
                    "holding_time_minutes": row["holding_time_minutes"],
                    "exit_reason": row["exit_reason"],
                }
                data.update({
                    "status": "accounting_invalid_pre_fix",
                    "lifecycle_state": "ACCOUNTING_INVALID_PRE_FIX",
                    "qualification_state": "EXCLUDED_ACCOUNTING_INVALID",
                    "counts_as_empirical_branch": False,
                    "accounting_integrity_status": "INVALID_NO_FILL_REPORTED_RESULT",
                    "accounting_integrity_version": self.ACCOUNTING_INTEGRITY_VERSION,
                    "accounting_marked_at_utc": marked_at,
                    "actual_fill_price": None,
                    "realized_R": None,
                    "result_R": None,
                    "MFE": None,
                    "MAE": None,
                    "holding_time_minutes": None,
                    "remaining_size": 0.0,
                })
                updates.append((
                    "accounting_invalid_pre_fix", marked_at, None, None, None, None,
                    row["exit_reason"],
                    json.dumps(data, sort_keys=True, separators=(",", ":"), default=str),
                    row["id"],
                ))
            connection.executemany(
                """UPDATE intraday_options_edge_branches
                   SET status=?, updated_at_utc=?, result_R=?, MFE=?, MAE=?,
                       holding_time_minutes=?, exit_reason=?, normalized_json=?
                   WHERE id=?""",
                updates,
            )
            return {"accounting_invalid_branches_marked": len(updates)}

        result = self.repository._write_with_retry(op)
        return {
            **result,
            "marked_at_utc": marked_at,
            "accounting_integrity_version": self.ACCOUNTING_INTEGRITY_VERSION,
            "canonical_paper_history_changed": False,
        }

    def start_clean_forward_validation(self, *, activated_at: datetime | None = None) -> dict[str, Any]:
        """Start a clean forward cohort after reconciling known research-only defects."""
        cutoff = activated_at or datetime.now(timezone.utc)
        reconciliation = self.reconcile_no_fill_accounting()
        phase4a = self.activate(force=True, activated_at=cutoff)
        phase4b2 = self.activate_phase4b2(force=True, activated_at=cutoff)
        return {
            "clean_forward_cutoff_utc": cutoff.isoformat(),
            "reconciliation": reconciliation,
            "phase4a_activation": phase4a,
            "phase4b2_activation": phase4b2,
            "focused_branches_per_parent": len(self._branch_blueprints()),
            "canonical_strategy_unchanged": True,
            "live_trading_disabled": True,
            "portfolio_os_isolated": True,
        }

    def generate_phase4b2_integrity_qa_report(self, report_date: str, *, mark_pre_fix: bool = True) -> dict[str, Any]:
        start_utc, end_utc = self._rth_window_for_date(report_date)
        scan_count = self._count_sql(
            "SELECT COUNT(*) FROM scan_observations WHERE observed_at_utc>=? AND observed_at_utc<?",
            (start_utc, end_utc),
        )
        setup_count = self._count_sql(
            "SELECT COUNT(*) FROM setup_events WHERE created_at_utc>=? AND created_at_utc<?",
            (start_utc, end_utc),
        )
        event_count = self._count_sql(
            "SELECT COUNT(*) FROM intraday_options_edge_events WHERE created_at_utc>=? AND created_at_utc<?",
            (start_utc, end_utc),
        )
        branch_count = self._count_sql(
            "SELECT COUNT(*) FROM intraday_options_edge_branches WHERE created_at_utc>=? AND created_at_utc<?",
            (start_utc, end_utc),
        )
        grouped = {
            "events_by_symbol": self._fetch_sql_rows(
                """SELECT ticker, COUNT(*) AS parent_events
                   FROM intraday_options_edge_events
                   WHERE created_at_utc>=? AND created_at_utc<?
                   GROUP BY ticker ORDER BY parent_events DESC""",
                (start_utc, end_utc),
            ),
            "events_by_family": self._fetch_sql_rows(
                """SELECT structural_family, COUNT(*) AS parent_events
                   FROM intraday_options_edge_events
                   WHERE created_at_utc>=? AND created_at_utc<?
                   GROUP BY structural_family ORDER BY parent_events DESC""",
                (start_utc, end_utc),
            ),
            "events_by_level_type": self._fetch_sql_rows(
                """SELECT level_type, COUNT(*) AS parent_events
                   FROM intraday_options_edge_events
                   WHERE created_at_utc>=? AND created_at_utc<?
                   GROUP BY level_type ORDER BY parent_events DESC""",
                (start_utc, end_utc),
            ),
            "parents_by_scan": self._fetch_sql_rows(
                """SELECT source_observation_id, ticker, COUNT(*) AS parent_events
                   FROM intraday_options_edge_events
                   WHERE created_at_utc>=? AND created_at_utc<?
                   GROUP BY source_observation_id, ticker
                   ORDER BY parent_events DESC LIMIT 20""",
                (start_utc, end_utc),
            ),
            "branches_by_status": self._fetch_sql_rows(
                """SELECT status, COUNT(*) AS branches
                   FROM intraday_options_edge_branches
                   WHERE created_at_utc>=? AND created_at_utc<?
                   GROUP BY status ORDER BY branches DESC""",
                (start_utc, end_utc),
            ),
        }
        branch_per_parent = [
            row["branches"] for row in self._fetch_sql_rows(
                """SELECT parent_event_id, COUNT(*) AS branches
                   FROM intraday_options_edge_branches
                   WHERE created_at_utc>=? AND created_at_utc<?
                   GROUP BY parent_event_id""",
                (start_utc, end_utc),
            )
        ]
        breakout_sample = self._fetch_sql_rows(
            """SELECT parent_event_id, ticker, trade_date, structural_family, level_type, normalized_json
               FROM intraday_options_edge_events
               WHERE created_at_utc>=? AND created_at_utc<? AND structural_family='LEVEL_BREAKOUT'
               ORDER BY parent_event_id LIMIT 100""",
            (start_utc, end_utc),
        )
        breakout_audit = Counter()
        for row in breakout_sample:
            payload = json.loads(row["normalized_json"])
            interaction_type = payload.get("interaction_type")
            confirmation_state = payload.get("confirmation_state")
            has_episode = bool(payload.get("interaction_episode") and payload.get("episode_reset_condition"))
            if interaction_type in {"BREAKOUT", "BREAKDOWN"} and confirmation_state and has_episode:
                breakout_audit["has_post_fix_sequence_metadata"] += 1
            else:
                breakout_audit["missing_strict_sequence_metadata"] += 1
        mark_result = {"events_marked": 0, "branches_marked": 0}
        if mark_pre_fix:
            mark_result = self._mark_phase4_research_prefix(start_utc, end_utc)

        ratio = {
            "parents_per_scan": round(event_count / scan_count, 4) if scan_count else None,
            "branches_per_parent_avg": round(branch_count / event_count, 4) if event_count else None,
            "branches_per_parent_median": median(branch_per_parent) if branch_per_parent else None,
            "branches_per_scan": round(branch_count / scan_count, 4) if scan_count else None,
        }
        report = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "report_date": report_date,
            "rth_window_utc": [start_utc, end_utc],
            "qa_integrity_version": self.QA_INTEGRITY_VERSION,
            "canonical_strategy_unchanged": True,
            "live_trading_disabled": True,
            "portfolio_os_isolated": True,
            "counts": {
                "market_scans": scan_count,
                "natural_setups": setup_count,
                "research_parent_events_pre_fix": event_count,
                "research_branches_pre_fix": branch_count,
                "qa_pre_fix_events_marked": mark_result["events_marked"],
                "qa_pre_fix_branches_marked": mark_result["branches_marked"],
            },
            "ratios": ratio,
            "multiplication_waterfall": grouped,
            "breakout_audit_sample_size": len(breakout_sample),
            "breakout_audit": dict(breakout_audit),
            "root_causes": [
                "Pre-fix parent generation iterated all configured cluster widths as empirical parents.",
                "Pre-fix LEVEL_BREAKOUT accepted price already above/below a zone as breakout without requiring a fresh interaction.",
                "Pre-fix branch writer opened one SQLite transaction per branch, increasing lock risk.",
                "Pre-fix persistence state lived inside nested level_strength payload and was not exposed consistently as trusted parent fields.",
            ],
            "post_fix_rules": [
                "Only the default ATR width creates economic parent zones; alternate widths are metadata.",
                "Breakout/breakdown requires zone interaction plus close/acceptance beyond the zone.",
                "Episode identity persists until price has reset away from the zone for the configured reset bars.",
                "C/D/P2 require complete persistence fields or become NOT_QUALIFIED_MISSING_PERSISTENCE.",
                "S2/S3/P3/P4 require their structure/classifier prerequisites before becoming pending.",
                "Branches carry lifecycle_state separate from raw DB status.",
                "Pre-fix records are marked QA_PRE_FIX and excluded from future research status/report statistics.",
            ],
        }
        output_path = self.output_root / "PHASE_4B2_RESEARCH_EVENT_INTEGRITY.md"

        def table(rows: list[dict[str, Any]], columns: list[str]) -> str:
            if not rows:
                return "| " + " | ".join(columns) + " |\n| " + " | ".join("---" for _ in columns) + " |\n"
            header = "| " + " | ".join(columns) + " |"
            sep = "| " + " | ".join("---" for _ in columns) + " |"
            body = "\n".join("| " + " | ".join(str(row.get(col, "")) for col in columns) + " |" for row in rows)
            return "\n".join([header, sep, body])

        markdown = f"""# Phase 4B.2-QA — Research Event Integrity

Generated: {report['generated_at_utc']}

RTH date: {report_date}

Scope: research instrumentation only. Canonical strategy logic, thresholds, weights, stops, targets, provider gates, watchlist, live-execution settings, and Portfolio OS boundaries were not changed.

## Top-line answers

1. Why did 18 scans produce 3,901 parent events? Pre-fix code multiplied each scan across all cluster widths and treated price already above/below many levels as `LEVEL_BREAKOUT`.
2. Was research event/branch inflation present? Yes. The pre-fix ratios were `{ratio['parents_per_scan']}` parents/scan and `{ratio['branches_per_scan']}` branches/scan.
3. Were all 3,901 parents valid economic interactions? No. They are marked `QA_PRE_FIX` and excluded from future edge statistics.
4. Was 99% breakout suspicious? Yes. The sampled pre-fix breakout rows lacked strict sequence metadata in `{dict(breakout_audit).get('missing_strict_sequence_metadata', 0)}` / {len(breakout_sample)} sampled rows.
5. Were persistence fields reliable enough for C/D/P2? Not as top-level trusted fields in pre-fix rows. Post-fix rows now expose required persistence fields and gate missing persistence.
6. Were branches actual setups? No. Registered combinations must be read through `lifecycle_state`; only `PENDING_ENTRY` / `ACTIVE` / `RESOLVED` qualified branches count.

## Multiplication waterfall

- Market scans: {scan_count}
- Natural canonical setup events: {setup_count}
- Pre-fix research parent events: {event_count}
- Pre-fix research branches: {branch_count}
- Parents per scan: {ratio['parents_per_scan']}
- Average branches per parent: {ratio['branches_per_parent_avg']}
- Median branches per parent: {ratio['branches_per_parent_median']}

## Events by symbol

{table(grouped['events_by_symbol'], ['ticker', 'parent_events'])}

## Events by structural family

{table(grouped['events_by_family'], ['structural_family', 'parent_events'])}

## Events by level type

{table(grouped['events_by_level_type'], ['level_type', 'parent_events'])}

## Highest parent counts by scan

{table(grouped['parents_by_scan'], ['source_observation_id', 'ticker', 'parent_events'])}

## Branch lifecycle/status before QA marking

{table(grouped['branches_by_status'], ['status', 'branches'])}

## Breakout audit sample

- Sampled breakout parents: {len(breakout_sample)}
- Missing strict sequence metadata: {dict(breakout_audit).get('missing_strict_sequence_metadata', 0)}
- Post-fix sequence metadata present: {dict(breakout_audit).get('has_post_fix_sequence_metadata', 0)}

## QA reconciliation

- Events marked `QA_PRE_FIX`: {mark_result['events_marked']}
- Branches marked `QA_PRE_FIX`: {mark_result['branches_marked']}
- Canonical setup history changed: no
- Canonical paper trade history changed: no

## Post-fix acceptance state

{chr(10).join(f'- {item}' for item in report['post_fix_rules'])}
"""
        output_path.write_text(markdown, encoding="utf-8")
        return {"markdown_path": str(output_path), "report": report}

    def _write_csv(self, path: Path, rows: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not rows:
            path.write_text("", encoding="utf-8")
            return
        flattened = []
        for row in rows:
            flattened.append({
                key: json.dumps(value, sort_keys=True, default=str) if isinstance(value, (dict, list, tuple)) else value
                for key, value in row.items()
            })
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=sorted({key for row in flattened for key in row}))
            writer.writeheader()
            writer.writerows(flattened)

    @staticmethod
    def _compact_event_export(row: dict[str, Any]) -> dict[str, Any]:
        context = row.get("context") or {}
        return {
            key: row.get(key) for key in (
                "parent_event_id", "ticker", "trade_date", "created_at_utc",
                "economic_level_cluster_id", "direction", "structural_family",
                "interaction_type", "approach_direction", "confirmation_state",
                "level_type", "level_tier", "level_price", "zone_low", "zone_high",
                "planned_entry", "structural_stop", "interaction_episode",
                "qa_status", "qa_integrity_version",
            )
        } | {
            "time_bucket": context.get("time_bucket"),
            "market_alignment": context.get("market_alignment"),
            "gamma_regime": context.get("gamma_regime"),
            "candle_provider": context.get("candle_provider"),
            "data_quality": context.get("data_quality"),
            "persistence_state": (context.get("level_strength") or {}).get("persistence_state"),
        }

    @staticmethod
    def _compact_branch_export(row: dict[str, Any]) -> dict[str, Any]:
        context = row.get("context") or {}
        return {
            key: row.get(key) for key in (
                "id", "parent_event_id", "ticker", "strategy_variant",
                "confirmation_tf", "execution_tf", "entry_variant",
                "management_variant", "stop_variant", "status", "lifecycle_state",
                "qualification_state", "created_at_utc", "updated_at_utc",
                "direction", "structural_family", "interaction_type", "level_type",
                "level_tier", "is_control", "control_type", "planned_entry",
                "actual_fill_price", "stop_initial", "stop_current", "initial_risk",
                "result_R", "MFE", "MAE", "holding_time_minutes", "exit_reason",
                "phase4b2_experiment_id", "phase4b2_branch", "qa_status",
                "accounting_integrity_status", "accounting_integrity_version",
            )
        } | {
            "entry_prerequisite_failures": row.get("entry_prerequisite_failures") or [],
            "events_count": len(row.get("events") or []),
            "trade_date": context.get("trade_date"),
            "time_bucket": context.get("time_bucket"),
            "market_alignment": context.get("market_alignment"),
            "gamma_regime": context.get("gamma_regime"),
            "candle_provider": context.get("candle_provider"),
            "data_quality": context.get("data_quality"),
            "persistence_state": (context.get("level_strength") or {}).get("persistence_state"),
        }

    def generate_report(self, report_date: str | None = None) -> dict[str, Any]:
        status = self.status(report_date)
        activation = self.activation()
        events = self._filter_by_report_date(
            self.repository.list_json("intraday_options_edge_events", limit=100000), report_date)
        events = [
            row for row in events
            if self._not_qa_pre_fix(row) and self._after_activation_cutoff(row, activation)
        ]
        branches = self._filter_by_report_date(
            self.repository.list_json("intraday_options_edge_branches", limit=100000), report_date)
        branches = [
            row for row in branches
            if self._not_qa_pre_fix(row) and self._after_activation_cutoff(row, activation)
        ]
        if report_date:
            output_dir = self.output_root / "reports" / report_date
            report_path = output_dir / "phase4a_daily_research_summary.md"
            events_csv = output_dir / "phase4a_intraday_options_edge_events.csv"
            branches_csv = output_dir / "phase4a_intraday_options_edge_branches.csv"
        else:
            report_path = self.output_root / str(self.settings.get("phase4a.report_path", "PHASE_4A_MULTITIMEFRAME_EDGE_REPORT.md"))
            events_csv = self.output_root / "phase4a_intraday_options_edge_events.csv"
            branches_csv = self.output_root / "phase4a_intraday_options_edge_branches.csv"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_csv(events_csv, [self._compact_event_export(row) for row in events])
        self._write_csv(branches_csv, [self._compact_branch_export(row) for row in branches])

        def table(rows: list[dict[str, Any]], label_key: str) -> str:
            if not rows:
                return "| - | 0 | 0 | 0 | 0 | 0 | 0 |\n"
            return "\n".join(
                f"| {row.get(label_key) or row.get('bucket')} | {row['N']} | {row['unique_trading_days']} | "
                f"{row['expectancy']} | {row['profit_factor']} | {row['win_rate']:.1%} | {row['sample_status']} |"
                for row in rows
            )

        dashboard = status["dashboard"]
        questions = [
            ("Does 15m confirmation outperform 5m confirmation?",
             "INSUFFICIENT_SAMPLE" if dashboard["fifteen_min_confirmation"]["N"] < 30 else
             dashboard["fifteen_min_confirmation"]["expectancy"] > dashboard["five_min_confirmation"]["expectancy"]),
            ("Do persistent/strengthening levels outperform raw/static levels?",
             "INSUFFICIENT_SAMPLE" if dashboard["persistent_levels"]["N"] < 30 else
             dashboard["persistent_levels"]["expectancy"] > dashboard["raw_levels"]["expectancy"]),
            ("Does Variant D outperform A/B/C?",
             "INSUFFICIENT_SAMPLE" if status["counts"]["resolved_branches"] < 30 else
             dashboard["best_research_variant"] == "VARIANT_D_PERSISTENT_15M_5M"),
            ("Are LONG setups materially better than SHORT?",
             "INSUFFICIENT_SAMPLE" if min(dashboard["long"]["N"], dashboard["short"]["N"]) < 30 else
             dashboard["long"]["expectancy"] > dashboard["short"]["expectancy"]),
            ("Are reclaim setups better than rejection?",
             "INSUFFICIENT_SAMPLE" if min(dashboard["reclaim"]["N"], dashboard["rejection"]["N"]) < 30 else
             dashboard["reclaim"]["expectancy"] > dashboard["rejection"]["expectancy"]),
            ("Do breakout setups have a separate edge?",
             "INSUFFICIENT_SAMPLE" if dashboard["breakout"]["N"] < 30 else dashboard["breakout"]["expectancy"] > 0),
            ("Which options level type performs best?",
             max(status["by_level_type"], key=lambda row: (row["N"] > 0, row["expectancy"]))["bucket"]
             if status["by_level_type"] else "INSUFFICIENT_SAMPLE"),
            ("Does options structure outperform matched ordinary price levels?",
             "INSUFFICIENT_SAMPLE" if min(dashboard["options_vs_controls"]["options"]["N"],
                                           dashboard["options_vs_controls"]["matched_controls"]["N"]) < 30 else
             dashboard["options_vs_controls"]["options"]["expectancy"] > dashboard["options_vs_controls"]["matched_controls"]["expectancy"]),
            ("What is the natural holding horizon?",
             "Tracked in branch holding_horizon_results_R; insufficient resolved sample for a stable horizon."),
            ("Are current stops too tight for higher-timeframe setups?",
             "Research stop variants recorded; no canonical stop change."),
            ("Which management variant best preserves entry edge?",
             max(status["by_management"], key=lambda row: (row["N"] > 0, row["expectancy"]))["bucket"]
             if status["by_management"] else "INSUFFICIENT_SAMPLE"),
            ("Does any candidate survive multiple days and robustness tests?",
             dashboard["sample_status"]),
        ]
        question_lines = "\n".join(f"{idx}. {question} `{answer}`" for idx, (question, answer) in enumerate(questions, 1))
        markdown = f"""# Phase 4A Multi-Timeframe Intraday Options-Level Edge Report

Generated: {status['generated_at_utc']}

Activation cutoff: {status['activation']['activated_at_utc']}

This report is research-only. Canonical paper behavior, thresholds, score weights, stop/TP logic, provider gates, watchlist, live-execution restrictions, and Portfolio OS isolation were not changed.

## Main questions

{question_lines}

## Progress

- Parent research events: {status['counts']['parent_events']}
- Research branches: {status['counts']['branches']}
- Resolved/censored branches: {status['counts']['resolved_branches']}
- Active branches: {status['counts']['active_branches']}
- Not-qualified branches: {status['counts']['not_qualified_branches']}
- Unique trading days: {dashboard['unique_trading_days']}
- Sample status: {dashboard['sample_status']}

## Primary variants A-G

| variant | N | days | expectancy | PF | win rate | status |
|---|---:|---:|---:|---:|---:|---|
{table(status['variant_summaries'], 'strategy_variant')}

## Direction

| direction | N | days | expectancy | PF | win rate | status |
|---|---:|---:|---:|---:|---:|---|
{table(status['by_direction'], 'bucket')}

## Structural family

| family | N | days | expectancy | PF | win rate | status |
|---|---:|---:|---:|---:|---:|---|
{table(status['by_structural_family'], 'bucket')}

## Level type

| level type | N | days | expectancy | PF | win rate | status |
|---|---:|---:|---:|---:|---:|---|
{table(status['by_level_type'], 'bucket')}

## Matched controls

- Options-level branches: N={dashboard['options_vs_controls']['options']['N']}, expectancy={dashboard['options_vs_controls']['options']['expectancy']}, PF={dashboard['options_vs_controls']['options']['profit_factor']}
- Matched-control branches: N={dashboard['options_vs_controls']['matched_controls']['N']}, expectancy={dashboard['options_vs_controls']['matched_controls']['expectancy']}, PF={dashboard['options_vs_controls']['matched_controls']['profit_factor']}

## Files

- Events CSV: {events_csv.name}
- Branches CSV: {branches_csv.name}
"""
        report_path.write_text(markdown, encoding="utf-8")
        return {"report": status, "markdown_path": str(report_path), "csv_paths": [str(events_csv), str(branches_csv)]}
