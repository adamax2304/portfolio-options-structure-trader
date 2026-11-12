from __future__ import annotations

import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any

import pandas as pd
from zoneinfo import ZoneInfo

from .db import Repository


EASTERN = ZoneInfo("America/New_York")


class EdgeDiscoveryReporter:
    """Read-only loss-attribution and edge-discovery report.

    This class builds derived research artifacts from natural forward-paper setup
    history. It never mutates setup/trade state and never changes strategy
    parameters.
    """

    THRESHOLDS = (0.25, 0.5, 0.75, 1.0, 1.5, 2.0)
    FINAL_TRADE_STATUSES = {"closed", "expired", "censored"}
    INDEX_ETFS = {"SPY", "QQQ", "IWM"}
    SECTOR_ETFS = {"XLK", "XLF", "XLE", "XLI", "XLV", "XLU", "ARKK", "SOXX", "XBI", "KRE"}
    SEMICONDUCTORS = {"NVDA", "AMD", "AVGO", "SMCI", "ARM", "MU", "TSM", "INTC"}
    CRYPTO_RELATED = {"COIN", "MSTR", "MARA", "RIOT", "CLSK"}
    NUCLEAR_ENERGY = {"OKLO", "CEG", "NNE", "SMR"}
    CYBERSECURITY = {"CRWD", "NET", "DDOG"}
    MEGA_CAP = {"AAPL", "MSFT", "META", "AMZN", "GOOGL", "TSLA"}
    SMALL_CAP_SPECULATIVE = {"RKLB", "SOFI", "RIVN", "BE", "CRWV", "IONQ", "RGTI", "QBTS"}

    def __init__(self, repository: Repository, settings: Any, watchlist: Any, output_root: Path):
        self.repository = repository
        self.settings = settings
        self.watchlist = watchlist
        self.output_root = output_root

    @staticmethod
    def _parse_time(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None

    @staticmethod
    def _safe_float(value: Any, default: float | None = None) -> float | None:
        try:
            if value is None:
                return default
            result = float(value)
            return result if math.isfinite(result) else default
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _truth(value: Any) -> bool:
        if isinstance(value, str):
            return value.strip().lower() in {"true", "1", "yes"}
        return bool(value)

    @staticmethod
    def _natural(payload: dict[str, Any]) -> bool:
        text = json.dumps(payload, sort_keys=True, default=str).lower()
        return (
            "demo_fixture" not in text
            and '"synthetic_present": true' not in text
            and '"fixture": true' not in text
        )

    @staticmethod
    def _score_bucket(value: Any) -> str:
        score = EdgeDiscoveryReporter._safe_float(value, -1) or -1
        if score < 50:
            return "<50"
        if score < 55:
            return "50-54"
        if score < 60:
            return "55-59"
        if score < 65:
            return "60-64"
        if score < 70:
            return "65-69"
        if score < 75:
            return "70-74"
        if score < 80:
            return "75-79"
        if score < 85:
            return "80-84"
        return "85+"

    @staticmethod
    def _confidence_bucket(value: Any) -> str:
        confidence = EdgeDiscoveryReporter._safe_float(value, -1) or -1
        if confidence < 0:
            return "UNKNOWN"
        if confidence < 0.40:
            return "LOW"
        if confidence < 0.60:
            return "MEDIUM"
        if confidence < 0.80:
            return "HIGH"
        return "VERY_HIGH"

    @staticmethod
    def _rr_bucket(value: Any) -> str:
        rr = EdgeDiscoveryReporter._safe_float(value, -1) or -1
        if rr < 0:
            return "UNKNOWN"
        if rr < 1.0:
            return "<1.0"
        if rr < 1.25:
            return "1.0-1.25"
        if rr < 1.50:
            return "1.25-1.5"
        if rr < 2.0:
            return "1.5-2"
        return "2+"

    @staticmethod
    def _gamma_distance_bucket(value: Any) -> str:
        distance = EdgeDiscoveryReporter._safe_float(value)
        if distance is None:
            return "UNKNOWN"
        distance = abs(distance)
        if distance < 0.5:
            return "0-0.5R"
        if distance < 1.0:
            return "0.5-1R"
        if distance < 2.0:
            return "1-2R"
        return "2R+"

    @staticmethod
    def _time_bucket(value: datetime | None) -> str:
        if not value:
            return "UNKNOWN"
        local = value.astimezone(EASTERN).time()
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
        return "OUTSIDE_RTH"

    @staticmethod
    def _sample_label(n: int) -> str:
        if n < 20:
            return "INSUFFICIENT_SAMPLE"
        if n < 50:
            return "EXPLORATORY"
        if n < 100:
            return "PRELIMINARY"
        return "STRONGER_EVIDENCE"

    def _asset_class(self, symbol: str, tier: str | None) -> str:
        symbol = symbol.upper()
        if symbol in self.INDEX_ETFS:
            return "INDEX_ETF"
        if symbol in self.SECTOR_ETFS:
            return "SECTOR_ETF"
        if symbol in self.CRYPTO_RELATED:
            return "CRYPTO_RELATED"
        if symbol in self.NUCLEAR_ENERGY:
            return "NUCLEAR_ENERGY"
        if symbol in self.CYBERSECURITY:
            return "CYBERSECURITY"
        if symbol in self.SEMICONDUCTORS:
            return "SEMICONDUCTOR"
        if symbol in self.MEGA_CAP:
            return "MEGA_CAP"
        if symbol in self.SMALL_CAP_SPECULATIVE:
            return "SMALL_CAP_SPECULATIVE"
        if tier == "tier_3_high_beta_theme":
            return "HIGH_BETA_GROWTH"
        return "SINGLE_STOCK"

    def _asset_group(self, symbol: str) -> str:
        return "ETF_INDEX_PROXY" if symbol.upper() in self.INDEX_ETFS | self.SECTOR_ETFS else "SINGLE_STOCK"

    def _setup_key(self, setup: dict[str, Any]) -> str:
        snapshot = setup.get("signal_snapshot") or {}
        key = snapshot.get("reclaim_event_key")
        if key:
            return str(key)
        bar = snapshot.get("confirmation_bar") or {}
        level = snapshot.get("level") or {}
        return "|".join([
            str(setup.get("ticker")),
            str(setup.get("side")),
            str(setup.get("setup_type")),
            str(level.get("level_id") or setup.get("level_id")),
            str(bar.get("bar_end_utc") or setup.get("created_at_utc")),
        ])

    def _load_json_rows(self, table: str) -> list[dict[str, Any]]:
        return self.repository.list_json(table, limit=100000)

    def _levels_index(self) -> dict[str, dict[str, list[dict[str, Any]]]]:
        levels = self._load_json_rows("option_levels")
        index: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for level in levels:
            ticker = str(level.get("ticker", "")).upper()
            level_type = str(level.get("level_type") or "UNKNOWN")
            index.setdefault(ticker, {}).setdefault(level_type, []).append(level)
        for type_map in index.values():
            for rows in type_map.values():
                rows.sort(key=lambda item: item.get("known_at_utc") or "")
        return index

    def _gex_index(self) -> dict[str, list[dict[str, Any]]]:
        rows = self._load_json_rows("options_gex_snapshots")
        index: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            index.setdefault(str(row.get("ticker", "")).upper(), []).append(row)
        for values in index.values():
            values.sort(key=lambda item: item.get("source_timestamp_utc") or "")
        return index

    def _bars_index(self) -> dict[str, list[dict[str, Any]]]:
        rows = self.repository.list_json("market_bars", "WHERE timeframe=?", ("5m",), limit=100000)
        index: dict[str, dict[str, dict[str, Any]]] = {}
        for row in rows:
            ticker = str(row.get("ticker", "")).upper()
            bar_end = str(row.get("bar_end_utc") or row.get("source_timestamp_utc") or "")
            if not ticker or not bar_end:
                continue
            current = index.setdefault(ticker, {}).get(bar_end)
            if current is None or str(row.get("source", "")).lower() == "yfinance":
                index[ticker][bar_end] = row
        return {ticker: [items[key] for key in sorted(items)] for ticker, items in index.items()}

    def _latest_level(self, levels: dict[str, dict[str, list[dict[str, Any]]]], symbol: str,
                      level_type: str, at: datetime | None) -> dict[str, Any] | None:
        rows = levels.get(symbol.upper(), {}).get(level_type, [])
        if not rows:
            return None
        if not at:
            return rows[-1]
        prior = [row for row in rows if (self._parse_time(row.get("known_at_utc")) or datetime.min.replace(tzinfo=timezone.utc)) <= at]
        return prior[-1] if prior else None

    def _latest_gex(self, gex: dict[str, list[dict[str, Any]]], symbol: str,
                    at: datetime | None) -> dict[str, Any] | None:
        rows = gex.get(symbol.upper(), [])
        if not rows:
            return None
        if not at:
            return rows[-1]
        prior = [row for row in rows if (self._parse_time(row.get("source_timestamp_utc")) or datetime.min.replace(tzinfo=timezone.utc)) <= at]
        return prior[-1] if prior else None

    def _trend(self, bars: dict[str, list[dict[str, Any]]], symbol: str, at: datetime | None) -> str:
        if not at:
            return "UNKNOWN"
        rows = [row for row in bars.get(symbol.upper(), []) if (self._parse_time(row.get("bar_end_utc")) or at) <= at]
        if len(rows) < 4:
            return "UNKNOWN"
        latest = self._safe_float(rows[-1].get("close"))
        earlier = self._safe_float(rows[-4].get("close"))
        if latest is None or earlier is None or earlier == 0:
            return "UNKNOWN"
        change = (latest - earlier) / earlier
        if change > 0.001:
            return "BULLISH"
        if change < -0.001:
            return "BEARISH"
        return "NEUTRAL"

    @staticmethod
    def _alignment(direction: str, trend: str) -> str:
        if trend not in {"BULLISH", "BEARISH"}:
            return "UNKNOWN"
        if (direction == "LONG" and trend == "BULLISH") or (direction == "SHORT" and trend == "BEARISH"):
            return "ALIGNED"
        return "COUNTER_TREND"

    def _bars_after(self, bars: dict[str, list[dict[str, Any]]], symbol: str, start: datetime | None) -> list[dict[str, Any]]:
        if not start:
            return []
        local_day = start.astimezone(EASTERN).date()
        close_utc = datetime.combine(local_day, time(16, 0), EASTERN).astimezone(timezone.utc)
        return [
            row for row in bars.get(symbol.upper(), [])
            if (bar_end := self._parse_time(row.get("bar_end_utc"))) and start < bar_end <= close_utc
        ]

    def _r_path_metrics(self, direction: str, entry: float | None, stop: float | None,
                        start: datetime | None, bars: dict[str, list[dict[str, Any]]],
                        symbol: str) -> dict[str, Any]:
        risk = abs((entry or 0) - (stop or 0))
        if not entry or not stop or risk <= 0:
            return {}
        side_mult = 1 if direction == "LONG" else -1
        after = self._bars_after(bars, symbol, start)
        result: dict[str, Any] = {}
        ever_reached = {threshold: False for threshold in self.THRESHOLDS}
        before_stop: dict[float, bool | None] = {threshold: None for threshold in self.THRESHOLDS}
        stopped = False
        for bar in after:
            high = self._safe_float(bar.get("high"), entry) or entry
            low = self._safe_float(bar.get("low"), entry) or entry
            favorable = ((high - entry) if side_mult == 1 else (entry - low)) / risk
            adverse = ((entry - low) if side_mult == 1 else (high - entry)) / risk
            for threshold in self.THRESHOLDS:
                if favorable >= threshold:
                    ever_reached[threshold] = True
                if before_stop[threshold] is None:
                    hit_gain = favorable >= threshold
                    hit_stop = adverse >= 1
                    if hit_gain and not hit_stop:
                        before_stop[threshold] = True
                    elif hit_stop and not hit_gain:
                        before_stop[threshold] = False
                    elif hit_gain and hit_stop:
                        before_stop[threshold] = None
            if adverse >= 1:
                stopped = True
            if stopped and all(value is not None for value in before_stop.values()):
                break
        for threshold in self.THRESHOLDS:
            suffix = str(threshold).replace(".", "_")
            result[f"reached_{suffix}R"] = ever_reached[threshold]
            result[f"hit_{suffix}R_before_minus_1R"] = before_stop[threshold]

        for minutes in (15, 30, 60, 120):
            target_time = start + timedelta(minutes=minutes) if start else None
            eligible = [row for row in after if target_time and self._parse_time(row.get("bar_end_utc")) and
                        self._parse_time(row["bar_end_utc"]) >= target_time]
            close = self._safe_float(eligible[0].get("close")) if eligible else None
            result[f"R_after_{minutes}m"] = round(((close - entry) * side_mult) / risk, 4) if close is not None else None
        if after:
            close = self._safe_float(after[-1].get("close"))
            result["R_at_close"] = round(((close - entry) * side_mult) / risk, 4) if close is not None else None
        else:
            result["R_at_close"] = None
        return result

    def _build_rows(self) -> list[dict[str, Any]]:
        setups = sorted(self._load_json_rows("setup_events"), key=lambda item: item.get("created_at_utc") or "")
        trades = self._load_json_rows("paper_trades")
        branches = self._load_json_rows("trade_management_branches")
        observations = self._load_json_rows("scan_observations")
        levels = self._levels_index()
        gex_index = self._gex_index()
        bars = self._bars_index()

        trade_by_setup: dict[str, dict[str, Any]] = {}
        for trade in sorted(trades, key=lambda item: item.get("created_at_utc") or ""):
            trade_by_setup[trade.get("setup_event_id")] = trade
        branch_by_setup: dict[str, dict[str, dict[str, Any]]] = {}
        for branch in branches:
            branch_by_setup.setdefault(branch.get("parent_setup_id"), {})[branch.get("branch")] = branch
        observation_by_setup: dict[str, dict[str, Any]] = {}
        for observation in sorted(observations, key=lambda item: item.get("observed_at_utc") or ""):
            setup_id = observation.get("setup_event_id")
            if setup_id:
                observation_by_setup[setup_id] = observation

        seen_keys: set[str] = set()
        rows: list[dict[str, Any]] = []
        for setup in setups:
            if not self._natural(setup):
                continue
            if not str(setup.get("source_mode", "")).startswith("REAL_"):
                continue
            setup_key = self._setup_key(setup)
            if setup_key in seen_keys:
                continue
            seen_keys.add(setup_key)

            setup_id = setup["setup_event_id"]
            symbol = str(setup.get("ticker", "")).upper()
            created = self._parse_time(setup.get("created_at_utc"))
            local_created = created.astimezone(EASTERN) if created else None
            trade = trade_by_setup.get(setup_id) or {}
            observation = observation_by_setup.get(setup_id) or {}
            branches_for_setup = branch_by_setup.get(setup_id, {})
            branch_a = branches_for_setup.get("A") or {}
            branch_b = branches_for_setup.get("B") or {}
            snapshot = setup.get("signal_snapshot") or {}
            features = snapshot.get("features") or {}
            raw_features = features.get("raw") or {}
            eligibility = snapshot.get("eligibility") or {}
            guard = snapshot.get("guard") or {}
            level = snapshot.get("level") or {}
            plan = setup.get("trade_plan") or {}
            score = setup.get("score") or {}
            score_raw = score.get("raw_components") or {}
            score_breakdown = score.get("breakdown") or {}
            providers = observation.get("providers") or {}
            router = providers.get("candle_router") or {}
            data_quality = observation.get("data_quality") or {}
            entry = self._safe_float(trade.get("actual_fill_price") or plan.get("planned_entry"))
            planned_entry = self._safe_float(plan.get("planned_entry"))
            stop = self._safe_float(plan.get("stop_initial"))
            risk = abs((entry or planned_entry or 0) - (stop or 0)) if stop is not None else None
            direction = str(setup.get("side") or trade.get("side") or "UNKNOWN")
            watchlist_entry = self.watchlist.entry(symbol)
            tier = data_quality.get("watchlist_tier") or (watchlist_entry.tier if watchlist_entry else None)
            asset_class = self._asset_class(symbol, tier)
            asset_group = self._asset_group(symbol)
            latest_gex = self._latest_gex(gex_index, symbol, created) or {}
            gamma_level = self._latest_level(levels, symbol, "GAMMA_FLIP", created)
            call_wall_level = self._latest_level(levels, symbol, "CALL_WALL", created)
            put_wall_level = self._latest_level(levels, symbol, "PUT_WALL", created)
            gamma_flip = (
                self._safe_float(level.get("price")) if level.get("level_type") == "GAMMA_FLIP"
                else self._safe_float((gamma_level or {}).get("price") or latest_gex.get("gamma_flip"))
            )
            call_wall = self._safe_float((call_wall_level or {}).get("price") or latest_gex.get("call_wall"))
            put_wall = self._safe_float((put_wall_level or {}).get("price") or latest_gex.get("put_wall"))
            strikes = latest_gex.get("strikes") or []
            net_gex = sum(self._safe_float(item.get("net_gex"), 0) or 0 for item in strikes) if strikes else None
            local_gex = None
            if strikes and (entry or planned_entry):
                anchor = entry or planned_entry
                nearest = min(strikes, key=lambda item: abs((self._safe_float(item.get("strike"), anchor) or anchor) - anchor))
                local_gex = self._safe_float(nearest.get("net_gex"))
            gamma_regime = str(raw_features.get("gamma_regime") or latest_gex.get("gamma_regime") or "UNKNOWN").upper()
            if gamma_regime in {"POSITIVE", "POSITIVE_GAMMA"}:
                gamma_regime = "POSITIVE_GAMMA"
            elif gamma_regime in {"NEGATIVE", "NEGATIVE_GAMMA"}:
                gamma_regime = "NEGATIVE_GAMMA"
            elif gamma_flip and entry and abs(entry - gamma_flip) / max(abs(entry), 1) < 0.0025:
                gamma_regime = "NEAR_FLIP"
            else:
                gamma_regime = "UNKNOWN" if gamma_regime == "UNKNOWN" else gamma_regime

            confidence = self._safe_float(score.get("confidence_score") or eligibility.get("confidence_score"))
            initial_rr = self._safe_float(plan.get("primary_rr"))
            canonical_status = trade.get("status")
            canonical_final = canonical_status in self.FINAL_TRADE_STATUSES
            canonical_r = self._safe_float(trade.get("realized_r"), 0.0) if canonical_final else None
            canonical_current_r = self._safe_float(trade.get("realized_r"), 0.0)
            open_time = self._parse_time(trade.get("opened_at_utc") or trade.get("created_at_utc") or setup.get("created_at_utc"))
            mfe = self._safe_float(trade.get("mfe_r"))
            mae = self._safe_float(trade.get("mae_r"))
            spy_trend = self._trend(bars, "SPY", created)
            qqq_trend = self._trend(bars, "QQQ", created)
            market_trend = qqq_trend if asset_class in {"SEMICONDUCTOR", "CYBERSECURITY", "MEGA_CAP", "HIGH_BETA_GROWTH"} else spy_trend
            candle_provider = (router.get("selected_candle_provider") or router.get("selected_provider")
                               or providers.get("price") or eligibility.get("price_provider")
                               or ((snapshot.get("confirmation_bar") or {}).get("source")))
            options_provider = providers.get("structure") or eligibility.get("structure_provider") or level.get("source")
            row = {
                "parent_setup_id": setup_id,
                "dedupe_key": setup_key,
                "symbol": symbol,
                "timestamp": setup.get("created_at_utc"),
                "session_date": local_created.date().isoformat() if local_created else None,
                "direction": direction,
                "tier": tier or "UNKNOWN",
                "asset_class": asset_class,
                "asset_group": asset_group,
                "setup_family": setup.get("setup_type"),
                "reclaimed_level_type": level.get("level_type") or setup.get("level_type") or "UNKNOWN",
                "entry_price": entry,
                "planned_entry": planned_entry,
                "structural_stop": stop,
                "risk_per_share": risk,
                "primary_target": (plan.get("targets") or [None])[0],
                "initial_RR": initial_rr,
                "rr_bucket": self._rr_bucket(initial_rr),
                "gamma_flip": gamma_flip,
                "distance_to_gamma_flip_pct": round(abs((entry or planned_entry or 0) - gamma_flip) / max(abs(entry or planned_entry or 1), 1) * 100, 4)
                if gamma_flip and (entry or planned_entry) else None,
                "distance_to_gamma_flip_R": round(abs((entry or planned_entry or 0) - gamma_flip) / risk, 4)
                if gamma_flip and risk and risk > 0 else None,
                "gamma_distance_bucket": self._gamma_distance_bucket(
                    abs((entry or planned_entry or 0) - gamma_flip) / risk if gamma_flip and risk and risk > 0 else None),
                "call_wall": call_wall,
                "put_wall": put_wall,
                "net_GEX": round(net_gex, 4) if net_gex is not None else None,
                "local_GEX": local_gex,
                "gamma_regime": gamma_regime,
                "GEX_strength": abs(net_gex) if net_gex is not None else None,
                "level_strength": self._safe_float(level.get("strength_score")),
                "directional_flow_score": self._safe_float(features.get("options_flow") or score_raw.get("options_flow")),
                "call_flow": raw_features.get("call_flow"),
                "put_flow": raw_features.get("put_flow"),
                "flow_balance": raw_features.get("flow_balance"),
                "flow_confirmation_available": self._truth(raw_features.get("flow_available")),
                "OI_available": not self._truth(eligibility.get("oi_unavailable")),
                "OI_confirmation": self._safe_float(features.get("oi_confirmation") or score_raw.get("oi_confirmation")),
                "Greeks_available": not self._truth(eligibility.get("greeks_unavailable")),
                "reclaim_strength": self._safe_float(features.get("price_structure") or score_raw.get("price_structure")),
                "sweep_depth": self._sweep_depth(snapshot, level, direction, risk),
                "reclaim_close_distance": self._reclaim_close_distance(snapshot, level, direction, risk),
                "volume_confirmation": self._truth(features.get("volume_expansion")),
                "VWAP_position": self._vwap_position(snapshot),
                "short_term_trend": self._short_term_trend(snapshot),
                "market_structure_state": raw_features.get("market_structure_state") or "UNKNOWN",
                "SPY_trend": spy_trend,
                "QQQ_trend": qqq_trend,
                "market_trend_used": market_trend,
                "market_alignment": self._alignment(direction, market_trend),
                "VIX_volatility_regime": raw_features.get("vix_regime") or "UNKNOWN",
                "macro_event_proximity": guard.get("minutes_to_event") if guard.get("minutes_to_event") is not None
                else guard.get("minutes_since_event"),
                "macro_unknown": self._truth(guard.get("macro_unknown") or eligibility.get("macro_unknown")),
                "time_since_open": self._minutes_since_open(created),
                "time_to_close": self._minutes_to_close(created),
                "time_bucket": self._time_bucket(created),
                "day_of_week": local_created.strftime("%A") if local_created else None,
                "candle_provider": str(candle_provider or "UNKNOWN").upper(),
                "options_provider": str(options_provider or "UNKNOWN").upper(),
                "data_quality_tier": score.get("data_quality_tier") or data_quality.get("data_quality_tier") or "UNKNOWN",
                "stale_flags": self._stale_flags(setup, observation),
                "missing_components": score.get("missing_components") or eligibility.get("missing_components") or [],
                "confidence_penalty": self._truth(eligibility.get("confidence_penalty_applied")
                                                 or data_quality.get("confidence_penalty_applied")),
                "raw_score": self._safe_float(score.get("raw_score")),
                "adjusted_score": self._safe_float(score.get("adjusted_score") or score.get("total")),
                "confidence_score": confidence,
                "score_bucket": self._score_bucket(score.get("adjusted_score") or score.get("total")),
                "confidence_bucket": self._confidence_bucket(confidence),
                "score_model_version": score.get("score_model_version"),
                "canonical_R": canonical_r,
                "canonical_current_R": canonical_current_r,
                "canonical_status": canonical_status,
                "canonical_final": canonical_final,
                "branch_A_R": self._safe_float(branch_a.get("realized_r"), 0.0) if branch_a else None,
                "branch_A_status": branch_a.get("status"),
                "branch_A_final": branch_a.get("status") in self.FINAL_TRADE_STATUSES,
                "branch_A_MFE_R": self._safe_float(branch_a.get("mfe_r")) if branch_a else None,
                "branch_A_MAE_R": self._safe_float(branch_a.get("mae_r")) if branch_a else None,
                "branch_B_R": self._safe_float(branch_b.get("realized_r"), 0.0) if branch_b else None,
                "branch_B_status": branch_b.get("status"),
                "branch_B_final": branch_b.get("status") in self.FINAL_TRADE_STATUSES,
                "branch_B_MFE_R": self._safe_float(branch_b.get("mfe_r")) if branch_b else None,
                "branch_B_MAE_R": self._safe_float(branch_b.get("mae_r")) if branch_b else None,
                "MFE_R": mfe,
                "MAE_R": mae,
                "opened_at": trade.get("opened_at_utc"),
                "closed_at": trade.get("closed_at_utc"),
                "exit_reason": trade.get("exit_reason"),
                "trade_mode": trade.get("mode") or setup.get("recommended_mode"),
            }
            row.update(self._r_path_metrics(direction, entry, stop, open_time, bars, symbol))
            rows.append(row)
        return rows

    def _sweep_depth(self, snapshot: dict[str, Any], level: dict[str, Any], direction: str,
                     risk: float | None) -> float | None:
        if not risk or risk <= 0:
            return None
        previous = snapshot.get("previous_bar") or {}
        level_price = self._safe_float(level.get("price"))
        if level_price is None:
            return None
        if direction == "LONG":
            low = self._safe_float(previous.get("low"))
            return round(max(0.0, level_price - low) / risk, 4) if low is not None else None
        high = self._safe_float(previous.get("high"))
        return round(max(0.0, high - level_price) / risk, 4) if high is not None else None

    def _reclaim_close_distance(self, snapshot: dict[str, Any], level: dict[str, Any], direction: str,
                                risk: float | None) -> float | None:
        if not risk or risk <= 0:
            return None
        confirmation = snapshot.get("confirmation_bar") or {}
        close = self._safe_float(confirmation.get("close"))
        level_price = self._safe_float(level.get("price"))
        if close is None or level_price is None:
            return None
        signed = (close - level_price) if direction == "LONG" else (level_price - close)
        return round(signed / risk, 4)

    def _vwap_position(self, snapshot: dict[str, Any]) -> str:
        confirmation = snapshot.get("confirmation_bar") or {}
        close = self._safe_float(confirmation.get("close"))
        vwap = self._safe_float(confirmation.get("vwap"))
        if close is None or vwap is None:
            return "UNKNOWN"
        return "ABOVE_VWAP" if close >= vwap else "BELOW_VWAP"

    def _short_term_trend(self, snapshot: dict[str, Any]) -> str:
        previous = snapshot.get("previous_bar") or {}
        confirmation = snapshot.get("confirmation_bar") or {}
        prev_close = self._safe_float(previous.get("close"))
        close = self._safe_float(confirmation.get("close"))
        if prev_close is None or close is None:
            return "UNKNOWN"
        if close > prev_close:
            return "UP"
        if close < prev_close:
            return "DOWN"
        return "FLAT"

    def _minutes_since_open(self, value: datetime | None) -> float | None:
        if not value:
            return None
        local = value.astimezone(EASTERN)
        open_at = datetime.combine(local.date(), time(9, 30), EASTERN)
        return round((local - open_at).total_seconds() / 60, 2)

    def _minutes_to_close(self, value: datetime | None) -> float | None:
        if not value:
            return None
        local = value.astimezone(EASTERN)
        close_at = datetime.combine(local.date(), time(16, 0), EASTERN)
        return round((close_at - local).total_seconds() / 60, 2)

    @staticmethod
    def _stale_flags(setup: dict[str, Any], observation: dict[str, Any]) -> list[str]:
        reasons = list(setup.get("blocking_reasons") or []) + list(observation.get("reasons") or [])
        return sorted({reason for reason in reasons if "stale" in str(reason).lower() or "freshness" in str(reason).lower()})

    def _metric_rows(self, df: pd.DataFrame, dimension: str, bucket_col: str,
                     sample_scope: str) -> list[dict[str, Any]]:
        if df.empty or bucket_col not in df:
            return []
        rows = []
        for bucket, group in df.groupby(bucket_col, dropna=False):
            metric = self._stats(group, "canonical_R")
            metric.update({"sample_scope": sample_scope, "dimension": dimension,
                           "bucket": "UNKNOWN" if pd.isna(bucket) else str(bucket)})
            rows.append(metric)
        rows.sort(key=lambda item: (item["sample_scope"], item["dimension"], item["bucket"]))
        return rows

    def _stats(self, frame: pd.DataFrame, outcome_col: str) -> dict[str, Any]:
        if frame.empty or outcome_col not in frame:
            values: list[float] = []
            resolved = pd.DataFrame()
        else:
            resolved = frame[frame[outcome_col].notna()].copy()
            resolved["_outcome"] = pd.to_numeric(resolved[outcome_col], errors="coerce")
            resolved = resolved[resolved["_outcome"].notna()]
            values = [float(value) for value in resolved["_outcome"]]
        wins = [value for value in values if value > 0]
        losses = [value for value in values if value < 0]
        equity = peak = max_drawdown = 0.0
        if not resolved.empty and "timestamp" in resolved:
            resolved = resolved.sort_values("timestamp")
        for value in values:
            equity += value
            peak = max(peak, equity)
            max_drawdown = max(max_drawdown, peak - equity)
        p05_values = self._probability_values(resolved, "hit_0_5R_before_minus_1R")
        p1_values = self._probability_values(resolved, "hit_1_0R_before_minus_1R")
        return {
            "N": len(values),
            "open_or_unresolved_N": max(0, len(frame) - len(values)),
            "total_R": round(sum(values), 4) if values else 0.0,
            "expectancy": round(sum(values) / len(values), 4) if values else 0.0,
            "median_R": round(median(values), 4) if values else 0.0,
            "profit_factor": round(sum(wins) / abs(sum(losses)), 4) if losses else (None if not wins else "infinite"),
            "win_rate": round(len(wins) / len(values), 4) if values else 0.0,
            "average_winner": round(sum(wins) / len(wins), 4) if wins else 0.0,
            "average_loser": round(sum(losses) / len(losses), 4) if losses else 0.0,
            "avg_MFE": round(pd.to_numeric(resolved.get("MFE_R"), errors="coerce").mean(), 4)
            if not resolved.empty and "MFE_R" in resolved else 0.0,
            "avg_MAE": round(pd.to_numeric(resolved.get("MAE_R"), errors="coerce").mean(), 4)
            if not resolved.empty and "MAE_R" in resolved else 0.0,
            "max_drawdown": round(max_drawdown, 4),
            "prob_plus_0_5R_before_minus_1R": round(sum(p05_values) / len(p05_values), 4) if p05_values else None,
            "prob_plus_1R_before_minus_1R": round(sum(p1_values) / len(p1_values), 4) if p1_values else None,
            "sample_label": self._sample_label(len(values)),
        }

    @staticmethod
    def _probability_values(frame: pd.DataFrame, column: str) -> list[int]:
        if frame.empty or column not in frame:
            return []
        values = []
        for value in frame[column]:
            if value is True or value == True:
                values.append(1)
            elif value is False or value == False:
                values.append(0)
        return values

    def _segment_frame(self, df: pd.DataFrame, dimensions: dict[str, str],
                       report_date: str) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for sample_scope, scoped in self._scopes(df, report_date).items():
            for dimension, column in dimensions.items():
                rows.extend(self._metric_rows(scoped, dimension, column, sample_scope))
        return pd.DataFrame(rows)

    def _scopes(self, df: pd.DataFrame, report_date: str) -> dict[str, pd.DataFrame]:
        if df.empty or "session_date" not in df:
            return {"cumulative": df, "today": df}
        return {"cumulative": df, "today": df[df["session_date"] == report_date].copy()}

    def _interaction_frame(self, df: pd.DataFrame, report_date: str) -> pd.DataFrame:
        pairs = [
            ("direction_x_gamma_regime", "direction", "gamma_regime"),
            ("direction_x_market_trend", "direction", "market_alignment"),
            ("level_type_x_direction", "reclaimed_level_type", "direction"),
            ("score_bucket_x_direction", "score_bucket", "direction"),
            ("score_bucket_x_level_type", "score_bucket", "reclaimed_level_type"),
            ("time_bucket_x_direction", "time_bucket", "direction"),
            ("asset_class_x_direction", "asset_class", "direction"),
            ("data_quality_x_level_type", "data_quality_tier", "reclaimed_level_type"),
        ]
        rows: list[dict[str, Any]] = []
        for sample_scope, scoped in self._scopes(df, report_date).items():
            for name, left, right in pairs:
                if left not in scoped or right not in scoped:
                    continue
                temp = scoped.copy()
                temp["_interaction_bucket"] = temp[left].astype(str) + " × " + temp[right].astype(str)
                rows.extend(self._metric_rows(temp, name, "_interaction_bucket", sample_scope))
        return pd.DataFrame(rows)

    def _bootstrap_frame(self, df: pd.DataFrame, segment_frames: list[pd.DataFrame]) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        overall = df[df.get("canonical_R").notna()] if not df.empty and "canonical_R" in df else pd.DataFrame()
        rows.append({"sample_scope": "cumulative", "dimension": "overall", "bucket": "ALL",
                     **self._bootstrap(overall)})
        for frame in segment_frames:
            if frame.empty:
                continue
            for item in frame.to_dict("records"):
                if int(item.get("N") or 0) < 20 or item.get("sample_scope") != "cumulative":
                    continue
                subset = df[df.get(item["dimension"].replace("reclaimed_level", "reclaimed_level"), pd.Series(dtype=str))
                            == item["bucket"]] if item["dimension"] in df else pd.DataFrame()
                if subset.empty:
                    continue
                rows.append({"sample_scope": item["sample_scope"], "dimension": item["dimension"],
                             "bucket": item["bucket"], **self._bootstrap(subset)})
        return pd.DataFrame(rows)

    def _bootstrap(self, frame: pd.DataFrame, iterations: int = 500) -> dict[str, Any]:
        if not isinstance(frame, pd.DataFrame) or frame.empty or "canonical_R" not in frame.columns:
            resolved = pd.DataFrame()
            values: list[float] = []
        else:
            resolved = frame[frame["canonical_R"].notna()].copy()
            values = [float(value) for value in pd.to_numeric(resolved["canonical_R"], errors="coerce").dropna()]
        if not values:
            return {
                "N": 0,
                "expectancy_ci_low": None, "expectancy_ci_high": None,
                "profit_factor_ci_low": None, "profit_factor_ci_high": None,
                "win_rate_ci_low": None, "win_rate_ci_high": None,
                "prob_plus_0_5R_ci_low": None, "prob_plus_0_5R_ci_high": None,
                "prob_plus_1R_ci_low": None, "prob_plus_1R_ci_high": None,
            }
        records = resolved.to_dict("records")
        rng = random.Random(20260903)
        means: list[float] = []
        pfs: list[float] = []
        win_rates: list[float] = []
        p05s: list[float] = []
        p1s: list[float] = []
        for _ in range(iterations):
            sample = [records[rng.randrange(len(records))] for _ in records]
            sample_values = [float(row["canonical_R"]) for row in sample if row.get("canonical_R") is not None]
            wins = [value for value in sample_values if value > 0]
            losses = [value for value in sample_values if value < 0]
            means.append(sum(sample_values) / len(sample_values))
            win_rates.append(len(wins) / len(sample_values))
            if wins and losses:
                pfs.append(sum(wins) / abs(sum(losses)))
            p05 = [1 if row.get("hit_0_5R_before_minus_1R") is True else 0
                   for row in sample if row.get("hit_0_5R_before_minus_1R") in {True, False}]
            p1 = [1 if row.get("hit_1_0R_before_minus_1R") is True else 0
                  for row in sample if row.get("hit_1_0R_before_minus_1R") in {True, False}]
            if p05:
                p05s.append(sum(p05) / len(p05))
            if p1:
                p1s.append(sum(p1) / len(p1))
        return {
            "N": len(values),
            "expectancy_ci_low": self._percentile(means, 2.5),
            "expectancy_ci_high": self._percentile(means, 97.5),
            "profit_factor_ci_low": self._percentile(pfs, 2.5),
            "profit_factor_ci_high": self._percentile(pfs, 97.5),
            "win_rate_ci_low": self._percentile(win_rates, 2.5),
            "win_rate_ci_high": self._percentile(win_rates, 97.5),
            "prob_plus_0_5R_ci_low": self._percentile(p05s, 2.5),
            "prob_plus_0_5R_ci_high": self._percentile(p05s, 97.5),
            "prob_plus_1R_ci_low": self._percentile(p1s, 2.5),
            "prob_plus_1R_ci_high": self._percentile(p1s, 97.5),
        }

    @staticmethod
    def _percentile(values: list[float], percentile: float) -> float | None:
        if not values:
            return None
        values = sorted(values)
        index = (len(values) - 1) * percentile / 100
        lower = math.floor(index)
        upper = math.ceil(index)
        if lower == upper:
            return round(values[int(index)], 4)
        result = values[lower] * (upper - index) + values[upper] * (index - lower)
        return round(result, 4)

    @classmethod
    def _clean_json(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: cls._clean_json(item) for key, item in value.items()}
        if isinstance(value, list):
            return [cls._clean_json(item) for item in value]
        if isinstance(value, tuple):
            return [cls._clean_json(item) for item in value]
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return value

    def _candidate_segments(self, frames: list[pd.DataFrame]) -> pd.DataFrame:
        rows = []
        for frame in frames:
            if frame.empty:
                continue
            for row in frame.to_dict("records"):
                if row.get("sample_scope") != "cumulative":
                    continue
                n = int(row.get("N") or 0)
                pf = row.get("profit_factor")
                numeric_pf = self._safe_float(pf)
                if n >= 20 and row.get("expectancy", 0) > 0 and (numeric_pf is not None and numeric_pf > 1):
                    rows.append(row)
        return pd.DataFrame(rows)

    def _robustness_frame(self, df: pd.DataFrame, candidates: pd.DataFrame) -> pd.DataFrame:
        rows = []
        if candidates.empty:
            return pd.DataFrame(rows)
        for candidate in candidates.to_dict("records"):
            subset = self._subset_for_candidate(df, candidate)
            if subset.empty:
                continue
            base = self._stats(subset, "canonical_R")
            best_symbol = (subset.groupby("symbol")["canonical_R"].sum().sort_values(ascending=False).index[0]
                           if "symbol" in subset and subset["canonical_R"].notna().any() else None)
            best_day = (subset.groupby("session_date")["canonical_R"].sum().sort_values(ascending=False).index[0]
                        if "session_date" in subset and subset["canonical_R"].notna().any() else None)
            tests = [
                ("base", subset),
                ("remove_best_symbol", subset[subset["symbol"] != best_symbol] if best_symbol else subset),
                ("remove_best_day", subset[subset["session_date"] != best_day] if best_day else subset),
                ("remove_top_5_winners", subset.drop(subset.sort_values("canonical_R", ascending=False).head(5).index, errors="ignore")),
            ]
            final_status = "ROBUSTNESS_IMPROVED"
            result_rows = []
            for test_name, test_frame in tests:
                stats = self._stats(test_frame, "canonical_R")
                numeric_pf = self._safe_float(stats.get("profit_factor"))
                if test_name != "base" and (stats["N"] < 20 or stats["expectancy"] <= 0 or not numeric_pf or numeric_pf <= 1):
                    final_status = "FRAGILE_EDGE"
                result = {"dimension": candidate["dimension"], "bucket": candidate["bucket"],
                          "test": test_name,
                          "best_symbol_removed": best_symbol, "best_day_removed": best_day,
                          **stats}
                result_rows.append(result)
            for result in result_rows:
                result["status"] = final_status
                rows.append(result)
            candidate["robustness_status"] = final_status
            candidate["base_expectancy"] = base["expectancy"]
        return pd.DataFrame(rows)

    def _holdout_frame(self, df: pd.DataFrame, candidates: pd.DataFrame) -> pd.DataFrame:
        rows = []
        if df.empty or candidates.empty:
            return pd.DataFrame(rows)
        ordered = df.sort_values("timestamp").reset_index(drop=True)
        split = max(1, int(len(ordered) * 0.70))
        discovery = ordered.iloc[:split].copy()
        holdout = ordered.iloc[split:].copy()
        for candidate in candidates.to_dict("records"):
            discovery_subset = self._subset_for_candidate(discovery, candidate)
            holdout_subset = self._subset_for_candidate(holdout, candidate)
            rows.append({"dimension": candidate["dimension"], "bucket": candidate["bucket"],
                         "split": "DISCOVERY", **self._stats(discovery_subset, "canonical_R")})
            rows.append({"dimension": candidate["dimension"], "bucket": candidate["bucket"],
                         "split": "HOLDOUT", **self._stats(holdout_subset, "canonical_R")})
        return pd.DataFrame(rows)

    @staticmethod
    def _subset_for_candidate(df: pd.DataFrame, candidate: dict[str, Any]) -> pd.DataFrame:
        dimension = candidate.get("dimension")
        bucket = candidate.get("bucket")
        interaction_columns = {
            "direction_x_gamma_regime": ("direction", "gamma_regime"),
            "direction_x_market_trend": ("direction", "market_alignment"),
            "level_type_x_direction": ("reclaimed_level_type", "direction"),
            "score_bucket_x_direction": ("score_bucket", "direction"),
            "score_bucket_x_level_type": ("score_bucket", "reclaimed_level_type"),
            "time_bucket_x_direction": ("time_bucket", "direction"),
            "asset_class_x_direction": ("asset_class", "direction"),
            "data_quality_x_level_type": ("data_quality_tier", "reclaimed_level_type"),
        }
        if dimension in interaction_columns and isinstance(bucket, str) and " × " in bucket:
            left, right = interaction_columns[dimension]
            if left not in df or right not in df:
                return pd.DataFrame()
            left_value, right_value = bucket.split(" × ", 1)
            return df[(df[left].astype(str) == left_value) & (df[right].astype(str) == right_value)].copy()
        if not dimension or dimension not in df:
            return pd.DataFrame()
        return df[df[dimension].astype(str) == str(bucket)].copy()

    def _store_candidates(self, candidates: pd.DataFrame, bootstrap: pd.DataFrame,
                          holdout: pd.DataFrame, robustness: pd.DataFrame) -> list[dict[str, Any]]:
        stored = []
        if candidates.empty:
            return stored
        for row in candidates.sort_values(["expectancy", "N"], ascending=[False, False]).to_dict("records")[:25]:
            description = f"{row['dimension']} = {row['bucket']}"
            edge_id = "EDGE_" + hashlib.sha1(description.encode()).hexdigest()[:10].upper()
            boot = bootstrap[(bootstrap.get("dimension") == row["dimension"]) &
                             (bootstrap.get("bucket") == row["bucket"])] if not bootstrap.empty else pd.DataFrame()
            hold = holdout[(holdout.get("dimension") == row["dimension"]) &
                           (holdout.get("bucket") == row["bucket"])] if not holdout.empty else pd.DataFrame()
            robust = robustness[(robustness.get("dimension") == row["dimension"]) &
                                (robustness.get("bucket") == row["bucket"])] if not robustness.empty else pd.DataFrame()
            robustness_status = "FRAGILE" if (not robust.empty and
                                              "FRAGILE_EDGE" in set(robust.get("status").dropna())) else None
            status = robustness_status or ("PRELIMINARY_EDGE" if int(row.get("N") or 0) >= 50 else "EXPLORATORY")
            candidate = {
                "edge_id": edge_id,
                "description": description,
                "discovered_at": datetime.now(timezone.utc).isoformat(),
                "sample_n": int(row.get("N") or 0),
                "expectancy": float(row.get("expectancy") or 0),
                "PF": row.get("profit_factor"),
                "MFE": row.get("avg_MFE"),
                "MAE": row.get("avg_MAE"),
                "bootstrap_CI": boot.to_dict("records")[0] if not boot.empty else {},
                "discovery_result": row,
                "holdout_result": hold.to_dict("records") if not hold.empty else [],
                "status": status,
            }
            candidate = self._clean_json(candidate)
            self.repository.store_edge_candidate(candidate)
            stored.append(candidate)
        return stored

    @staticmethod
    def _safe_write_frame(frame: pd.DataFrame, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if frame.empty:
            frame.to_csv(path, index=False)
            return
        clean = frame.copy()
        for column in clean.columns:
            if clean[column].dtype == object:
                clean[column] = clean[column].map(
                    lambda value: json.dumps(value, sort_keys=True, default=str)
                    if isinstance(value, (dict, list, tuple, set)) else value
                )
        clean.to_csv(path, index=False)

    def _write_master(self, df: pd.DataFrame, parquet_path: Path) -> None:
        export = df.copy()
        for column in export.columns:
            if export[column].dtype == object:
                export[column] = export[column].map(
                    lambda value: json.dumps(value, sort_keys=True, default=str)
                    if isinstance(value, (dict, list, tuple, set)) else value
                )
        export.to_parquet(parquet_path, index=False)

    def _write_markdown(self, path: Path, df: pd.DataFrame, outputs: dict[str, str],
                        segments: dict[str, pd.DataFrame], candidates: list[dict[str, Any]],
                        bootstrap: pd.DataFrame, holdout: pd.DataFrame, ab_status: dict[str, Any] | None) -> dict[str, Any]:
        overall = self._stats(df, "canonical_R")
        symbol_frame = segments.get("symbol", pd.DataFrame())
        direction_frame = segments.get("direction", pd.DataFrame())
        asset_frame = segments.get("asset_class", pd.DataFrame())
        level_frame = segments.get("level_type", pd.DataFrame())
        score_frame = segments.get("score", pd.DataFrame())
        confidence_frame = segments.get("confidence", pd.DataFrame())
        time_frame = segments.get("time", pd.DataFrame())
        data_frame = segments.get("data_quality", pd.DataFrame())

        cumulative_symbols = symbol_frame[symbol_frame["sample_scope"] == "cumulative"] if not symbol_frame.empty else pd.DataFrame()
        best_symbols = cumulative_symbols.sort_values("total_R", ascending=False).head(10) if not cumulative_symbols.empty else pd.DataFrame()
        worst_symbols = cumulative_symbols.sort_values("total_R", ascending=True).head(10) if not cumulative_symbols.empty else pd.DataFrame()
        insufficient_symbols = cumulative_symbols[cumulative_symbols["N"] < 5] if not cumulative_symbols.empty else pd.DataFrame()
        total_losses = abs(sum(value for value in pd.to_numeric(df.get("canonical_R"), errors="coerce").dropna() if value < 0))
        worst_two_loss = abs(sum(value for value in worst_symbols.head(2)["total_R"] if value < 0)) if not worst_symbols.empty else 0
        loss_concentration = round(worst_two_loss / total_losses, 4) if total_losses else 0
        long_row = self._first_metric(direction_frame, "cumulative", "LONG")
        short_row = self._first_metric(direction_frame, "cumulative", "SHORT")
        index_row = self._first_metric(asset_frame, "cumulative", "INDEX_ETF")
        single_stock = df[df["asset_group"] == "SINGLE_STOCK"] if not df.empty and "asset_group" in df else pd.DataFrame()
        single_stats = self._stats(single_stock, "canonical_R")
        best_level = self._best(level_frame)
        worst_level = self._worst(level_frame)
        best_time = self._best(time_frame)
        worst_time = self._worst(time_frame)
        best_score = self._best(score_frame)
        worst_score = self._worst(score_frame)
        best_quality = self._best(data_frame)
        worst_quality = self._worst(data_frame)
        candidate_counts = Counter(item["status"] for item in candidates)
        best_candidate = candidates[0] if candidates else None
        holdout_survivors = [
            row for row in (holdout.to_dict("records") if not holdout.empty else [])
            if row.get("split") == "HOLDOUT" and int(row.get("N") or 0) >= 20
            and row.get("expectancy", 0) > 0 and (self._safe_float(row.get("profit_factor")) or 0) > 1
        ]

        def table(frame: pd.DataFrame, cols: list[str], limit: int = 10) -> str:
            if frame.empty:
                return "_No rows._"
            lines = ["| " + " | ".join(cols) + " |",
                     "| " + " | ".join("---" for _ in cols) + " |"]
            for row in frame.head(limit).to_dict("records"):
                lines.append("| " + " | ".join(str(row.get(col, "")) for col in cols) + " |")
            return "\n".join(lines)

        ab_lines = ""
        if ab_status:
            branches = {row["branch"]: row for row in ab_status.get("branches", [])}
            a = branches.get("A", {})
            b = branches.get("B", {})
            ab_lines = f"""
## A/B management status

- Paired completed/censored: {ab_status.get('paired_completed_or_censored')} / {ab_status.get('acceptance_target')}
- Branch A expectancy/PF: {a.get('expectancy')} / {a.get('profit_factor')}
- Branch B expectancy/PF: {b.get('expectancy')} / {b.get('profit_factor')}
- B minus A expectancy/PF: {ab_status.get('expectancy_delta_b_minus_a')} / {ab_status.get('profit_factor_delta_b_minus_a')}
- Decision: do not promote B yet; keep paired forward collection unchanged.
"""

        summary = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "rows": len(df),
            "resolved_rows": overall["N"],
            "overall": overall,
            "loss_concentration_worst_two_symbols": loss_concentration,
            "best_candidate": best_candidate,
            "candidate_counts": dict(candidate_counts),
            "holdout_survivor_count": len(holdout_survivors),
            "dashboard": {
                "overall_expectancy": overall["expectancy"],
                "overall_profit_factor": overall["profit_factor"],
                "best_preliminary_subgroup": self._label_metric(best_candidate),
                "worst_subgroup": self._label_metric(self._worst(symbol_frame)),
                "long_expectancy": long_row.get("expectancy") if long_row else None,
                "short_expectancy": short_row.get("expectancy") if short_row else None,
                "index_etf_expectancy": index_row.get("expectancy") if index_row else None,
                "single_stock_expectancy": single_stats.get("expectancy"),
                "best_level_type": self._label_metric(best_level),
                "worst_level_type": self._label_metric(worst_level),
                "best_time_window": self._label_metric(best_time),
                "worst_time_window": self._label_metric(worst_time),
                "best_score_bucket": self._label_metric(best_score),
                "worst_score_bucket": self._label_metric(worst_score),
                "candidate_counts": dict(candidate_counts),
            },
            "outputs": outputs,
        }
        summary = self._clean_json(summary)
        low_score = self._low_score_driver(score_frame)
        markdown = f"""# Phase 2D.5 Edge Discovery & Loss Attribution

Generated: {summary['generated_at_utc']}

Diagnosis only. No setup definitions, thresholds, confluence weights, stops, targets, trade management, watchlist, macro guard, provider gates, live-trading safeguards, or Portfolio OS isolation were changed.

## Plain-English answers

1. **Where did most losses come from?** The largest cumulative loss contributors are shown in the Worst 10 table below. Worst-two-symbol loss concentration is {loss_concentration:.1%} of gross losses.
2. **Are losses concentrated or broad-based?** {"Concentrated enough to treat symbol selection as a live hypothesis." if loss_concentration >= 0.35 else "Broad enough that the current evidence does not blame only one or two symbols."}
3. **Do LONG and SHORT behave differently?** LONG expectancy is {long_row.get('expectancy') if long_row else 'n/a'}R; SHORT expectancy is {short_row.get('expectancy') if short_row else 'n/a'}R.
4. **Do SPY/QQQ/IWM behave better than individual stocks?** INDEX_ETF expectancy is {index_row.get('expectancy') if index_row else 'n/a'}R; single-stock expectancy is {single_stats.get('expectancy')}R.
5. **Which options level type performs best?** Best current level bucket: {best_level.get('bucket') if best_level else 'n/a'} with expectancy {best_level.get('expectancy') if best_level else 'n/a'}R. Worst: {worst_level.get('bucket') if worst_level else 'n/a'}.
6. **Does confluence score predict outcomes?** {low_score}
7. **Does data quality predict outcome?** Best data-quality bucket: {best_quality.get('bucket') if best_quality else 'n/a'}; worst: {worst_quality.get('bucket') if worst_quality else 'n/a'}.
8. **Which time of day is best/worst?** Best time bucket: {best_time.get('bucket') if best_time else 'n/a'}; worst time bucket: {worst_time.get('bucket') if worst_time else 'n/a'}.
9. **Does any subset show positive entry edge before trade-management effects?** {self._entry_edge_sentence(df)}
10. **Does any candidate survive holdout/robustness tests?** {len(holdout_survivors)} candidate bucket(s) currently survive the holdout screen with N >= 20, expectancy > 0, and PF > 1; robustness details are in `edge_robustness.csv`.
11. **What should be tested prospectively next?** Keep collection unchanged and register only the candidate buckets below as hypotheses. No parameter change is supported until a candidate survives prospective forward validation.

## Overall canonical forward sample

- Unique natural setup rows: {len(df)}
- Resolved canonical rows used for expectancy: {overall['N']}
- Expectancy: {overall['expectancy']}R
- Profit factor: {overall['profit_factor']}
- Win rate: {overall['win_rate']:.1%}
- Median R: {overall['median_R']}R
- Avg MFE / MAE: {overall['avg_MFE']}R / {overall['avg_MAE']}R
- Max drawdown: {overall['max_drawdown']}R

## Worst 10 symbols by total R

{table(worst_symbols, ['bucket', 'N', 'total_R', 'expectancy', 'profit_factor', 'win_rate', 'avg_MFE', 'avg_MAE', 'max_drawdown'])}

## Best 10 symbols by total R

{table(best_symbols, ['bucket', 'N', 'total_R', 'expectancy', 'profit_factor', 'win_rate', 'avg_MFE', 'avg_MAE', 'max_drawdown'])}

## Symbols with N < 5

{table(insufficient_symbols.sort_values('bucket') if not insufficient_symbols.empty else insufficient_symbols, ['bucket', 'N', 'total_R', 'expectancy', 'sample_label'], 80)}

## Direction

{table(direction_frame[direction_frame['sample_scope'] == 'cumulative'] if not direction_frame.empty else direction_frame, ['bucket', 'N', 'expectancy', 'profit_factor', 'win_rate', 'median_R', 'avg_MFE', 'avg_MAE'])}

## Asset class

{table(asset_frame[asset_frame['sample_scope'] == 'cumulative'] if not asset_frame.empty else asset_frame, ['bucket', 'N', 'expectancy', 'profit_factor', 'win_rate', 'median_R', 'avg_MFE', 'avg_MAE'])}

## Score discrimination

{table(score_frame[score_frame['sample_scope'] == 'cumulative'] if not score_frame.empty else score_frame, ['bucket', 'N', 'expectancy', 'profit_factor', 'win_rate', 'prob_plus_0_5R_before_minus_1R', 'prob_plus_1R_before_minus_1R'])}

## Confidence and data quality

{table(confidence_frame[confidence_frame['sample_scope'] == 'cumulative'] if not confidence_frame.empty else confidence_frame, ['bucket', 'N', 'expectancy', 'profit_factor', 'win_rate', 'avg_MFE', 'avg_MAE'])}

{table(data_frame[data_frame['sample_scope'] == 'cumulative'] if not data_frame.empty else data_frame, ['dimension', 'bucket', 'N', 'expectancy', 'profit_factor', 'win_rate', 'avg_MFE', 'avg_MAE'])}

## Candidate edge registry generated this run

{table(pd.DataFrame(candidates), ['edge_id', 'description', 'sample_n', 'expectancy', 'PF', 'status'], 25) if candidates else '_No positive candidate met the minimum exploratory filters._'}

{ab_lines}
## Output artifacts

{chr(10).join(f'- `{Path(path).name}`' for path in outputs.values())}
"""
        path.write_text(markdown, encoding="utf-8")
        return summary

    @staticmethod
    def _first_metric(frame: pd.DataFrame, sample_scope: str, bucket: str) -> dict[str, Any] | None:
        if frame.empty:
            return None
        rows = frame[(frame["sample_scope"] == sample_scope) & (frame["bucket"] == bucket)]
        return rows.to_dict("records")[0] if not rows.empty else None

    @staticmethod
    def _best(frame: pd.DataFrame) -> dict[str, Any] | None:
        if frame.empty:
            return None
        rows = frame[(frame["sample_scope"] == "cumulative") & (frame["N"] >= 5)]
        return rows.sort_values("expectancy", ascending=False).to_dict("records")[0] if not rows.empty else None

    @staticmethod
    def _worst(frame: pd.DataFrame) -> dict[str, Any] | None:
        if frame.empty:
            return None
        rows = frame[(frame["sample_scope"] == "cumulative") & (frame["N"] >= 5)]
        return rows.sort_values("expectancy", ascending=True).to_dict("records")[0] if not rows.empty else None

    @staticmethod
    def _label_metric(row: dict[str, Any] | None) -> str | None:
        if not row:
            return None
        label = row.get("description") or row.get("bucket")
        expectancy = row.get("expectancy")
        n = row.get("sample_n") or row.get("N")
        return f"{label} ({expectancy}R, N={n})"

    def _low_score_driver(self, score_frame: pd.DataFrame) -> str:
        if score_frame.empty:
            return "No score-bucket rows are available yet."
        rows = score_frame[score_frame["sample_scope"] == "cumulative"].copy()
        if rows.empty:
            return "No cumulative score-bucket rows are available yet."
        low = rows[rows["bucket"].isin(["<50", "50-54", "55-59"])]
        high = rows[~rows["bucket"].isin(["<50", "50-54", "55-59"])]
        low_r = low["total_R"].sum() if not low.empty else 0
        high_r = high["total_R"].sum() if not high.empty else 0
        if low_r < 0 and abs(low_r) > abs(high_r):
            return f"Low-score buckets are the larger visible loss source ({round(low_r, 4)}R vs {round(high_r, 4)}R outside low-score)."
        return f"Losses are not explained solely by low-score buckets ({round(low_r, 4)}R low-score vs {round(high_r, 4)}R outside low-score)."

    def _entry_edge_sentence(self, df: pd.DataFrame) -> str:
        if df.empty:
            return "No natural setup rows are available."
        p05 = self._probability_values(df, "hit_0_5R_before_minus_1R")
        p1 = self._probability_values(df, "hit_1_0R_before_minus_1R")
        if not p05 and not p1:
            return "No filled setup path has enough bar history for threshold-before-stop analysis."
        first = f"P(+0.5R before -1R)={sum(p05)/len(p05):.1%}" if p05 else "P(+0.5R before -1R)=n/a"
        second = f"P(+1R before -1R)={sum(p1)/len(p1):.1%}" if p1 else "P(+1R before -1R)=n/a"
        return f"Overall filled-entry path shows {first}; {second}. Segment-level probabilities are in `edge_entry_excursion.csv` and `edge_interactions.csv`."

    def generate(self, report_date: str | None = None, *, ab_status: dict[str, Any] | None = None) -> dict[str, Any]:
        report_date = report_date or datetime.now(EASTERN).date().isoformat()
        self.output_root.mkdir(parents=True, exist_ok=True)
        rows = self._build_rows()
        df = pd.DataFrame(rows)
        if df.empty:
            df = pd.DataFrame(columns=["parent_setup_id", "symbol", "timestamp", "canonical_R"])
        outputs = {
            "master_parquet": str(self.output_root / "edge_master_dataset.parquet"),
            "master_csv": str(self.output_root / "edge_master_dataset.csv"),
            "by_symbol": str(self.output_root / "edge_by_symbol.csv"),
            "by_direction": str(self.output_root / "edge_by_direction.csv"),
            "by_asset_class": str(self.output_root / "edge_by_asset_class.csv"),
            "by_time": str(self.output_root / "edge_by_time.csv"),
            "by_time_of_day": str(self.output_root / "edge_by_time_of_day.csv"),
            "by_score": str(self.output_root / "edge_by_score.csv"),
            "by_confidence": str(self.output_root / "edge_by_confidence.csv"),
            "by_level_type": str(self.output_root / "edge_by_level_type.csv"),
            "by_gamma_regime": str(self.output_root / "edge_by_gamma_regime.csv"),
            "by_market_alignment": str(self.output_root / "edge_by_market_alignment.csv"),
            "by_data_quality": str(self.output_root / "edge_by_data_quality.csv"),
            "by_rr": str(self.output_root / "edge_by_rr.csv"),
            "by_candle_provider": str(self.output_root / "edge_by_candle_provider.csv"),
            "by_gamma_distance": str(self.output_root / "edge_by_gamma_distance.csv"),
            "entry_excursion": str(self.output_root / "edge_entry_excursion.csv"),
            "interactions": str(self.output_root / "edge_interactions.csv"),
            "bootstrap": str(self.output_root / "edge_bootstrap.csv"),
            "robustness": str(self.output_root / "edge_robustness.csv"),
            "holdout": str(self.output_root / "edge_holdout.csv"),
            "report": str(self.output_root / "PHASE_2D5_EDGE_DISCOVERY.md"),
        }
        self._write_master(df, Path(outputs["master_parquet"]))
        self._safe_write_frame(df, Path(outputs["master_csv"]))

        segments = {
            "symbol": self._segment_frame(df, {"symbol": "symbol"}, report_date),
            "direction": self._segment_frame(df, {"direction": "direction"}, report_date),
            "asset_class": self._segment_frame(df, {"asset_class": "asset_class", "asset_group": "asset_group"}, report_date),
            "time": self._segment_frame(df, {"time_bucket": "time_bucket"}, report_date),
            "score": self._segment_frame(df, {"score_bucket": "score_bucket"}, report_date),
            "confidence": self._segment_frame(df, {"confidence_bucket": "confidence_bucket"}, report_date),
            "level_type": self._segment_frame(df, {"reclaimed_level_type": "reclaimed_level_type"}, report_date),
            "gamma_regime": self._segment_frame(df, {"gamma_regime": "gamma_regime"}, report_date),
            "market_alignment": self._segment_frame(df, {"market_alignment": "market_alignment"}, report_date),
            "data_quality": self._segment_frame(df, {
                "data_quality_tier": "data_quality_tier",
                "candle_provider": "candle_provider",
                "options_provider": "options_provider",
            }, report_date),
            "rr": self._segment_frame(df, {"rr_bucket": "rr_bucket"}, report_date),
            "candle_provider": self._segment_frame(df, {"candle_provider": "candle_provider"}, report_date),
            "gamma_distance": self._segment_frame(df, {"gamma_distance_bucket": "gamma_distance_bucket"}, report_date),
        }
        interaction_frame = self._interaction_frame(df, report_date)
        candidates = self._candidate_segments([
            segments["symbol"], segments["direction"], segments["asset_class"], segments["time"],
            segments["score"], segments["confidence"], segments["level_type"], segments["gamma_regime"],
            segments["market_alignment"], segments["data_quality"], segments["rr"], segments["gamma_distance"],
            interaction_frame,
        ])
        bootstrap = self._bootstrap_candidates(df, candidates)
        holdout = self._holdout_frame(df, candidates)
        robustness = self._robustness_frame(df, candidates)
        stored_candidates = self._store_candidates(candidates, bootstrap, holdout, robustness)

        self._safe_write_frame(segments["symbol"], Path(outputs["by_symbol"]))
        self._safe_write_frame(segments["direction"], Path(outputs["by_direction"]))
        self._safe_write_frame(segments["asset_class"], Path(outputs["by_asset_class"]))
        self._safe_write_frame(segments["time"], Path(outputs["by_time"]))
        self._safe_write_frame(segments["time"], Path(outputs["by_time_of_day"]))
        self._safe_write_frame(segments["score"], Path(outputs["by_score"]))
        self._safe_write_frame(segments["confidence"], Path(outputs["by_confidence"]))
        self._safe_write_frame(segments["level_type"], Path(outputs["by_level_type"]))
        self._safe_write_frame(segments["gamma_regime"], Path(outputs["by_gamma_regime"]))
        self._safe_write_frame(segments["market_alignment"], Path(outputs["by_market_alignment"]))
        self._safe_write_frame(segments["data_quality"], Path(outputs["by_data_quality"]))
        self._safe_write_frame(segments["rr"], Path(outputs["by_rr"]))
        self._safe_write_frame(segments["candle_provider"], Path(outputs["by_candle_provider"]))
        self._safe_write_frame(segments["gamma_distance"], Path(outputs["by_gamma_distance"]))
        excursion_cols = [
            "parent_setup_id", "symbol", "timestamp", "direction", "score_bucket", "confidence_bucket",
            "reclaimed_level_type", "gamma_regime", "MFE_R", "MAE_R",
            "reached_0_25R", "reached_0_5R", "reached_0_75R", "reached_1_0R",
            "reached_1_5R", "reached_2_0R", "hit_0_5R_before_minus_1R",
            "hit_1_0R_before_minus_1R", "hit_1_5R_before_minus_1R", "hit_2_0R_before_minus_1R",
            "R_after_15m", "R_after_30m", "R_after_60m", "R_after_120m", "R_at_close",
        ]
        self._safe_write_frame(df[[col for col in excursion_cols if col in df]], Path(outputs["entry_excursion"]))
        self._safe_write_frame(interaction_frame, Path(outputs["interactions"]))
        self._safe_write_frame(bootstrap, Path(outputs["bootstrap"]))
        self._safe_write_frame(robustness, Path(outputs["robustness"]))
        self._safe_write_frame(holdout, Path(outputs["holdout"]))

        summary = self._write_markdown(Path(outputs["report"]), df, outputs, segments, stored_candidates,
                                       bootstrap, holdout, ab_status)
        return {"report": summary, "markdown_path": outputs["report"],
                "csv_paths": [value for key, value in outputs.items() if key not in {"report", "master_parquet"}],
                "parquet_path": outputs["master_parquet"]}

    def _bootstrap_candidates(self, df: pd.DataFrame, candidates: pd.DataFrame) -> pd.DataFrame:
        rows = [{"sample_scope": "cumulative", "dimension": "overall", "bucket": "ALL",
                 **self._bootstrap(df)}]
        if candidates.empty:
            return pd.DataFrame(rows)
        for candidate in candidates.to_dict("records"):
            subset = self._subset_for_candidate(df, candidate)
            rows.append({"sample_scope": "cumulative", "dimension": candidate["dimension"],
                         "bucket": candidate["bucket"], **self._bootstrap(subset)})
        return pd.DataFrame(rows)


class ForwardEdgeValidationReporter(EdgeDiscoveryReporter):
    """Prospective Phase 2D.6 cohort tracker.

    Phase 2D.5 remains discovery data. This class only persists cohort
    memberships for setup events seen after Phase 2D.6 activation, and reports
    those forward-holdout cohorts without changing strategy parameters.
    """

    PHASE_ID = "phase_2d6_forward_edge_validation"
    MANAGEMENT_VERSIONS = ("TM_V0_CURRENT", "TM_V3_TP1_PLUS_RUNNER")
    COHORT_LABELS = {
        "A_ALL_LONG": "A · all LONG setups",
        "B_ALL_SHORT": "B · all SHORT setups",
        "C_LONG_1130_1300": "C · LONG 11:30–13:00 ET",
        "D_LONG_OUTSIDE_1130_1300": "D · LONG outside 11:30–13:00 ET",
        "E_SHORT_MARKET_ALIGNED": "E · SHORT aligned with broader market trend",
        "F_SHORT_COUNTER_TREND": "F · SHORT counter to broader market trend",
        "G_LONG_GEX_NODE": "G · LONG GEX_NODE reclaims",
        "H_LONG_GAMMA_FLIP": "H · LONG GAMMA_FLIP reclaims",
        "SHORT_13_00_14_30": "2D.7 · SHORT 13:00–14:30 ET prospective cohort",
    }

    def __init__(self, repository: Repository, settings: Any, watchlist: Any, output_root: Path):
        super().__init__(repository, settings, watchlist, output_root)
        self.activate()

    @classmethod
    def _stable_id(cls, *parts: Any) -> str:
        digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:24]
        return f"fedge_{digest}"

    def activation(self) -> dict[str, Any] | None:
        rows = self.repository.list_json("forward_edge_activation", "WHERE id=?", (self.PHASE_ID,), 1)
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
            "phase": "2D.6_FORWARD_EDGE_VALIDATION",
            "holdout_rule": "Only setup events created after activated_at_utc are eligible for Phase 2D.6 cohorts.",
            "discovery_data_note": "Phase 2D.5 rows remain discovery data and are not retrospectively relabeled.",
            "strategy_parameters_changed": False,
            "canonical_strategy_unchanged": True,
            "live_trading_disabled": True,
        }
        self.repository.store_forward_edge_activation(record)
        return record

    def phase2d7_activation(self) -> dict[str, Any] | None:
        rows = self.repository.list_json("forward_edge_activation", "WHERE id=?",
                                         ("phase_2d7_short_failure_decomposition",), 1)
        return rows[0] if rows else None

    def activate_phase2d7(self, *, force: bool = False, activated_at: datetime | None = None) -> dict[str, Any]:
        existing = self.phase2d7_activation()
        if existing and not force:
            return existing
        now = activated_at or datetime.now(timezone.utc)
        record = {
            "id": "phase_2d7_short_failure_decomposition",
            "activated_at_utc": now.isoformat(),
            "discovery_cutoff_utc": now.isoformat(),
            "phase": "2D.7_SHORT_EDGE_FAILURE_DECOMPOSITION",
            "holdout_rule": "SHORT_13_00_14_30 membership is prospective from this timestamp.",
            "strategy_parameters_changed": False,
            "canonical_strategy_unchanged": True,
            "live_trading_disabled": True,
        }
        self.repository.store_forward_edge_activation(record)
        return record

    def _trend_lookback(self, bars: dict[str, list[dict[str, Any]]], symbol: str,
                        at: datetime | None, lookback_minutes: int) -> str:
        if not at:
            return "UNKNOWN"
        rows = [row for row in bars.get(symbol.upper(), [])
                if (self._parse_time(row.get("bar_end_utc")) or at) <= at]
        needed = max(2, lookback_minutes // 5 + 1)
        if len(rows) < needed:
            return "UNKNOWN"
        latest = self._safe_float(rows[-1].get("close"))
        earlier = self._safe_float(rows[-needed].get("close"))
        if latest is None or earlier is None or earlier == 0:
            return "UNKNOWN"
        change = (latest - earlier) / earlier
        threshold = 0.0015 if lookback_minutes <= 15 else 0.003
        if change > threshold:
            return "BULLISH"
        if change < -threshold:
            return "BEARISH"
        return "NEUTRAL"

    @staticmethod
    def _short_alignment_class(spy_15m: str, qqq_15m: str, symbol_15m: str, symbol_1h: str) -> str:
        values = [spy_15m, qqq_15m, symbol_15m, symbol_1h]
        known = [value for value in values if value in {"BULLISH", "BEARISH", "NEUTRAL"}]
        if len(known) < 2:
            return "UNKNOWN"
        market_bearish = spy_15m == "BEARISH" or qqq_15m == "BEARISH"
        market_bullish = spy_15m == "BULLISH" or qqq_15m == "BULLISH"
        symbol_bearish = symbol_15m == "BEARISH" or symbol_1h == "BEARISH"
        symbol_bullish = symbol_15m == "BULLISH" or symbol_1h == "BULLISH"
        if market_bearish and symbol_bearish:
            if spy_15m == "BEARISH" and qqq_15m == "BEARISH" and symbol_15m == "BEARISH" and symbol_1h == "BEARISH":
                return "FULLY_ALIGNED"
            return "MARKET_ALIGNED"
        if symbol_bearish and not market_bearish:
            return "SYMBOL_ONLY"
        if market_bullish or symbol_bullish:
            return "COUNTERTREND"
        return "UNKNOWN"

    def _setup_features(self, setup: dict[str, Any]) -> dict[str, Any]:
        symbol = str(setup.get("ticker", "")).upper()
        direction = str(setup.get("side") or "UNKNOWN").upper()
        created = self._parse_time(setup.get("created_at_utc"))
        snapshot = setup.get("signal_snapshot") or {}
        features = snapshot.get("features") or {}
        raw_features = features.get("raw") or {}
        level = snapshot.get("level") or {}
        plan = setup.get("trade_plan") or {}
        score = setup.get("score") or {}
        bars = self._bars_index()
        gex_index = self._gex_index()
        latest_gex = self._latest_gex(gex_index, symbol, created) or {}
        watchlist_entry = self.watchlist.entry(symbol)
        tier = watchlist_entry.tier if watchlist_entry else "UNKNOWN"
        asset_class = self._asset_class(symbol, tier)
        spy_trend = self._trend(bars, "SPY", created)
        qqq_trend = self._trend(bars, "QQQ", created)
        spy_15m = self._trend_lookback(bars, "SPY", created, 15)
        qqq_15m = self._trend_lookback(bars, "QQQ", created, 15)
        symbol_15m = self._trend_lookback(bars, symbol, created, 15)
        symbol_1h = self._trend_lookback(bars, symbol, created, 60)
        short_alignment = self._short_alignment_class(spy_15m, qqq_15m, symbol_15m, symbol_1h)
        market_trend = qqq_trend if asset_class in {"SEMICONDUCTOR", "CYBERSECURITY", "MEGA_CAP", "HIGH_BETA_GROWTH"} else spy_trend
        market_alignment = self._alignment(direction, market_trend)
        level_type = str(level.get("level_type") or setup.get("level_type") or "UNKNOWN").upper()
        entry = self._safe_float(plan.get("planned_entry"))
        stop = self._safe_float(plan.get("stop_initial"))
        risk = abs((entry or 0) - (stop or 0)) if entry is not None and stop is not None else None
        gamma_flip = (
            self._safe_float(level.get("price")) if level_type == "GAMMA_FLIP"
            else self._safe_float(latest_gex.get("gamma_flip"))
        )
        gamma_regime = str(raw_features.get("gamma_regime") or latest_gex.get("gamma_regime") or "UNKNOWN").upper()
        if gamma_regime in {"POSITIVE", "POSITIVE_GAMMA"}:
            gamma_regime = "POSITIVE_GAMMA"
        elif gamma_regime in {"NEGATIVE", "NEGATIVE_GAMMA"}:
            gamma_regime = "NEGATIVE_GAMMA"
        elif gamma_flip and entry and abs(entry - gamma_flip) / max(abs(entry), 1) < 0.0025:
            gamma_regime = "NEAR_FLIP"
        elif not gamma_regime:
            gamma_regime = "UNKNOWN"
        return {
            "symbol": symbol,
            "direction": direction,
            "timestamp": setup.get("created_at_utc"),
            "session_date": created.astimezone(EASTERN).date().isoformat() if created else None,
            "time_bucket": self._time_bucket(created),
            "tier": tier or "UNKNOWN",
            "asset_class": asset_class,
            "asset_group": self._asset_group(symbol),
            "reclaimed_level_type": level_type,
            "score": self._safe_float(score.get("adjusted_score") or score.get("total")),
            "score_bucket": self._score_bucket(score.get("adjusted_score") or score.get("total")),
            "confidence_score": self._safe_float(score.get("confidence_score")),
            "confidence_bucket": self._confidence_bucket(score.get("confidence_score")),
            "gamma_regime": gamma_regime,
            "gamma_flip": gamma_flip,
            "distance_to_gamma_flip_R": round(abs(entry - gamma_flip) / risk, 4)
            if entry is not None and gamma_flip is not None and risk and risk > 0 else None,
            "distance_to_gamma_flip_pct": round(abs(entry - gamma_flip) / max(abs(entry), 1) * 100, 4)
            if entry is not None and gamma_flip is not None else None,
            "SPY_direction": spy_trend,
            "QQQ_direction": qqq_trend,
            "SPY_15m_trend": spy_15m,
            "QQQ_15m_trend": qqq_15m,
            "symbol_15m_trend": symbol_15m,
            "symbol_1h_trend": symbol_1h,
            "broader_market_trend_used": market_trend,
            "market_alignment": market_alignment,
            "short_alignment_class": short_alignment,
            "against_higher_timeframe_trend": market_alignment == "COUNTER_TREND",
            "higher_timeframe_trend_proxy": "SPY_QQQ_5M_4BAR_PROXY",
            "data_quality_tier": score.get("data_quality_tier") or "UNKNOWN",
            "source_mode": setup.get("source_mode"),
        }

    def _cohorts_for_setup(self, features: dict[str, Any]) -> list[str]:
        direction = features.get("direction")
        time_bucket = features.get("time_bucket")
        level_type = features.get("reclaimed_level_type")
        alignment = features.get("market_alignment")
        cohorts: list[str] = []
        if direction == "LONG":
            cohorts.append("A_ALL_LONG")
            cohorts.append("C_LONG_1130_1300" if time_bucket == "11:30-13:00" else "D_LONG_OUTSIDE_1130_1300")
            if level_type == "GEX_NODE":
                cohorts.append("G_LONG_GEX_NODE")
            if level_type == "GAMMA_FLIP":
                cohorts.append("H_LONG_GAMMA_FLIP")
        elif direction == "SHORT":
            cohorts.append("B_ALL_SHORT")
            short_alignment = features.get("short_alignment_class")
            if short_alignment in {"FULLY_ALIGNED", "MARKET_ALIGNED"} or alignment == "ALIGNED":
                cohorts.append("E_SHORT_MARKET_ALIGNED")
            elif short_alignment == "COUNTERTREND" or alignment == "COUNTER_TREND":
                cohorts.append("F_SHORT_COUNTER_TREND")
        return cohorts

    def register_setup(self, setup: dict[str, Any] | Any) -> list[dict[str, Any]]:
        if hasattr(setup, "model_dump"):
            setup = setup.model_dump(mode="json")
        if not setup.get("trade_plan") or not self._natural(setup):
            return []
        if not str(setup.get("source_mode", "")).startswith("REAL_"):
            return []
        activation = self.activate()
        activated_at = self._parse_time(activation.get("activated_at_utc"))
        created = self._parse_time(setup.get("created_at_utc"))
        if activated_at and created and created < activated_at:
            return []
        features = self._setup_features(setup)
        cohorts = self._cohorts_for_setup(features)
        phase2d7 = self.phase2d7_activation()
        phase2d7_at = self._parse_time((phase2d7 or {}).get("activated_at_utc"))
        if (features.get("direction") == "SHORT" and features.get("time_bucket") == "13:00-14:30"
                and phase2d7_at and created and created >= phase2d7_at):
            cohorts.append("SHORT_13_00_14_30")
        records: list[dict[str, Any]] = []
        for cohort in cohorts:
            for version in self.MANAGEMENT_VERSIONS:
                record = {
                    "id": self._stable_id(setup["setup_event_id"], cohort, version),
                    "parent_setup_id": setup["setup_event_id"],
                    "cohort": cohort,
                    "cohort_label": self.COHORT_LABELS[cohort],
                    "management_version": version,
                    "ticker": features["symbol"],
                    "side": features["direction"],
                    "created_at_utc": setup.get("created_at_utc") or datetime.now(timezone.utc).isoformat(),
                    "phase": "2D.6_FORWARD_HOLDOUT",
                    "discovery_cutoff_utc": activation.get("discovery_cutoff_utc"),
                    "features": features,
                    "counts_as_empirical_setup": False,
                    "parent_setup_counts_once": True,
                }
                self.repository.store_forward_edge_membership(record)
                records.append(record)
        if features.get("direction") == "SHORT":
            diagnostic = {
                "id": self._stable_id(setup["setup_event_id"], "SHORT_FAILURE_ANALYSIS"),
                "parent_setup_id": setup["setup_event_id"],
                "ticker": features["symbol"],
                "created_at_utc": setup.get("created_at_utc") or datetime.now(timezone.utc).isoformat(),
                "phase": "2D.6_FORWARD_HOLDOUT",
                "SPY_direction": features.get("SPY_direction"),
                "QQQ_direction": features.get("QQQ_direction"),
                "gamma_regime": features.get("gamma_regime"),
                "distance_to_gamma_flip_R": features.get("distance_to_gamma_flip_R"),
                "time_of_day": features.get("time_bucket"),
                "against_higher_timeframe_trend": features.get("against_higher_timeframe_trend"),
                "higher_timeframe_trend_proxy": features.get("higher_timeframe_trend_proxy"),
                "market_alignment": features.get("market_alignment"),
                "short_alignment_class": features.get("short_alignment_class"),
                "SPY_15m_trend": features.get("SPY_15m_trend"),
                "QQQ_15m_trend": features.get("QQQ_15m_trend"),
                "symbol_15m_trend": features.get("symbol_15m_trend"),
                "symbol_1h_trend": features.get("symbol_1h_trend"),
                "outcome_pending": True,
            }
            self.repository.store_short_failure_analysis(diagnostic)
        return records

    def _forward_rows(self) -> pd.DataFrame:
        memberships = self.repository.list_json("forward_edge_memberships", limit=100000)
        base_rows = {row["parent_setup_id"]: row for row in self._build_rows()}
        rows: list[dict[str, Any]] = []
        for membership in memberships:
            parent_id = membership.get("parent_setup_id")
            base = base_rows.get(parent_id, {})
            if membership.get("management_version") == "TM_V3_TP1_PLUS_RUNNER":
                outcome = base.get("branch_B_R") if base.get("branch_B_final") else None
                status = base.get("branch_B_status")
                mfe = base.get("branch_B_MFE_R")
                mae = base.get("branch_B_MAE_R")
            else:
                outcome = base.get("canonical_R") if base.get("canonical_final") else None
                status = base.get("canonical_status")
                if outcome is None and base.get("branch_A_final"):
                    outcome = base.get("branch_A_R")
                    status = base.get("branch_A_status")
                mfe = base.get("MFE_R") if base.get("MFE_R") is not None else base.get("branch_A_MFE_R")
                mae = base.get("MAE_R") if base.get("MAE_R") is not None else base.get("branch_A_MAE_R")
            row = {
                **base,
                "membership_id": membership.get("id"),
                "cohort": membership.get("cohort"),
                "cohort_label": membership.get("cohort_label") or self.COHORT_LABELS.get(membership.get("cohort"), membership.get("cohort")),
                "management_version": membership.get("management_version"),
                "membership_created_at_utc": membership.get("created_at_utc"),
                "outcome_R": outcome,
                "outcome_status": status,
                "MFE_R": mfe,
                "MAE_R": mae,
            }
            if not base:
                features = membership.get("features") or {}
                row.update({
                    "parent_setup_id": parent_id,
                    "symbol": membership.get("ticker"),
                    "timestamp": membership.get("created_at_utc"),
                    "session_date": features.get("session_date"),
                    "direction": membership.get("side"),
                    "tier": features.get("tier"),
                    "asset_class": features.get("asset_class"),
                    "asset_group": features.get("asset_group"),
                    "reclaimed_level_type": features.get("reclaimed_level_type"),
                    "time_bucket": features.get("time_bucket"),
                    "score_bucket": features.get("score_bucket"),
                    "confidence_bucket": features.get("confidence_bucket"),
                    "gamma_regime": features.get("gamma_regime"),
                    "distance_to_gamma_flip_R": features.get("distance_to_gamma_flip_R"),
                    "data_quality_tier": features.get("data_quality_tier"),
                    "SPY_trend": features.get("SPY_direction"),
                    "QQQ_trend": features.get("QQQ_direction"),
                    "market_alignment": features.get("market_alignment"),
                })
            rows.append(row)
        return pd.DataFrame(rows)

    def _symbol_concentration(self, frame: pd.DataFrame) -> dict[str, Any]:
        resolved = frame[frame.get("outcome_R").notna()].copy() if not frame.empty and "outcome_R" in frame else pd.DataFrame()
        if resolved.empty:
            return {"top_symbol": None, "top_symbol_count_share": 0.0, "top_symbol_abs_contribution_share": 0.0,
                    "dominated_by_one_symbol": False}
        values = pd.to_numeric(resolved["outcome_R"], errors="coerce")
        resolved = resolved[values.notna()].copy()
        resolved["outcome_R"] = values[values.notna()]
        counts = resolved.groupby("symbol")["parent_setup_id"].nunique().sort_values(ascending=False)
        totals = resolved.groupby("symbol")["outcome_R"].sum()
        abs_total = totals.abs().sum()
        abs_shares = (totals.abs() / abs_total).sort_values(ascending=False) if abs_total else pd.Series(dtype=float)
        top_symbol = str(counts.index[0]) if not counts.empty else None
        count_share = float(counts.iloc[0] / max(1, resolved["parent_setup_id"].nunique())) if not counts.empty else 0.0
        contribution_share = float(abs_shares.iloc[0]) if not abs_shares.empty else 0.0
        return {
            "top_symbol": top_symbol,
            "top_symbol_count_share": round(count_share, 4),
            "top_symbol_abs_contribution_share": round(contribution_share, 4),
            "dominated_by_one_symbol": count_share >= 0.35 or contribution_share >= 0.50,
        }

    def _promotion_status(self, frame: pd.DataFrame, stats: dict[str, Any],
                          concentration: dict[str, Any]) -> tuple[str, str]:
        n = int(stats.get("N") or 0)
        numeric_pf = math.inf if stats.get("profit_factor") == "infinite" else self._safe_float(stats.get("profit_factor"))
        if n >= 100 and stats.get("expectancy", 0) > 0 and numeric_pf and numeric_pf > 1:
            robustness = self._robustness_for_forward(frame)
            if robustness == "FORWARD_SUPPORTED":
                return "FORWARD_SUPPORTED", robustness
            if n >= 50 and not concentration.get("dominated_by_one_symbol"):
                return "PRELIMINARY_EDGE_FRAGILE", robustness
            return "FRAGILE", robustness
        if n >= 50 and stats.get("expectancy", 0) > 0 and numeric_pf and numeric_pf > 1 and not concentration.get("dominated_by_one_symbol"):
            return "PRELIMINARY_EDGE", "NOT_TESTABLE_UNTIL_N_100"
        if n >= 20:
            return "EXPLORATORY", "NOT_TESTABLE_UNTIL_N_100"
        return "INSUFFICIENT_FORWARD_SAMPLE", "NOT_TESTABLE_UNTIL_N_100"

    def _robustness_for_forward(self, frame: pd.DataFrame) -> str:
        resolved = frame[frame.get("outcome_R").notna()].copy() if not frame.empty and "outcome_R" in frame else pd.DataFrame()
        if resolved.empty or len(resolved) < 100:
            return "NOT_TESTABLE_UNTIL_N_100"
        resolved["outcome_R"] = pd.to_numeric(resolved["outcome_R"], errors="coerce")
        resolved = resolved[resolved["outcome_R"].notna()]
        if resolved.empty:
            return "NOT_TESTABLE_UNTIL_N_100"
        best_symbol = resolved.groupby("symbol")["outcome_R"].sum().sort_values(ascending=False).index[0] if "symbol" in resolved else None
        best_day = resolved.groupby("session_date")["outcome_R"].sum().sort_values(ascending=False).index[0] if "session_date" in resolved else None
        tests = [
            ("remove_best_symbol", resolved[resolved["symbol"] != best_symbol] if best_symbol else resolved),
            ("remove_best_day", resolved[resolved["session_date"] != best_day] if best_day else resolved),
            ("remove_top_5_winners", resolved.drop(resolved.sort_values("outcome_R", ascending=False).head(5).index, errors="ignore")),
        ]
        for _, test_frame in tests:
            stats = self._stats(test_frame, "outcome_R")
            pf = math.inf if stats.get("profit_factor") == "infinite" else self._safe_float(stats.get("profit_factor"))
            if stats["N"] == 0 or stats["expectancy"] <= 0 or not pf or pf <= 1:
                return "FRAGILE_REMOVAL_TEST_FAILED"
        return "FORWARD_SUPPORTED"

    def _cohort_metrics(self, df: pd.DataFrame) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        if df.empty:
            return pd.DataFrame(rows)
        for (cohort, version), group in df.groupby(["cohort", "management_version"], dropna=False):
            stats = self._stats(group, "outcome_R")
            concentration = self._symbol_concentration(group)
            status, robustness = self._promotion_status(group, stats, concentration)
            parent_count = group["parent_setup_id"].nunique() if "parent_setup_id" in group else len(group)
            rows.append({
                "cohort": cohort,
                "cohort_label": self.COHORT_LABELS.get(str(cohort), str(cohort)),
                "management_version": version,
                "parent_setup_count": int(parent_count),
                **stats,
                **concentration,
                "robustness_status": robustness,
                "promotion_status": status,
            })
        order = {cohort: index for index, cohort in enumerate(self.COHORT_LABELS)}
        rows.sort(key=lambda item: (order.get(item["cohort"], 999), str(item["management_version"])))
        return pd.DataFrame(rows)

    def _short_failure_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        diagnostics = self.repository.list_json("short_failure_analysis", limit=100000)
        by_parent = {row.get("parent_setup_id"): row for row in df.to_dict("records")} if not df.empty else {}
        rows: list[dict[str, Any]] = []
        for item in diagnostics:
            parent = item.get("parent_setup_id")
            row = by_parent.get(parent, {})
            price_reached_05 = row.get("hit_0_5R_before_minus_1R")
            rows.append({
                "parent_setup_id": parent,
                "symbol": item.get("ticker"),
                "timestamp": item.get("created_at_utc"),
                "SPY_direction": item.get("SPY_direction"),
                "QQQ_direction": item.get("QQQ_direction"),
                "gamma_regime": item.get("gamma_regime"),
                "distance_to_gamma_flip_R": item.get("distance_to_gamma_flip_R"),
                "time_of_day": item.get("time_of_day"),
                "against_higher_timeframe_trend": item.get("against_higher_timeframe_trend"),
                "market_alignment": item.get("market_alignment"),
                "price_first_reached_plus_0_5R": price_reached_05,
                "price_first_reached_plus_1R": row.get("hit_1_0R_before_minus_1R"),
                "later_reversed_to_stop": bool(price_reached_05 is True and row.get("canonical_R") is not None and row.get("canonical_R") <= -0.9),
                "canonical_R": row.get("canonical_R"),
                "TM_V3_R": row.get("branch_B_R"),
                "canonical_status": row.get("canonical_status"),
                "TM_V3_status": row.get("branch_B_status"),
            })
        return pd.DataFrame(rows)

    def _long_validation_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame()
        long_rows = df[df.get("direction") == "LONG"].copy()
        if long_rows.empty:
            return pd.DataFrame()
        grouped = []
        for parent_id, group in long_rows.groupby("parent_setup_id", dropna=False):
            base = group.to_dict("records")[0]
            cohorts = sorted(set(group["cohort"].dropna()))
            grouped.append({
                "parent_setup_id": parent_id,
                "symbol": base.get("symbol"),
                "timestamp": base.get("timestamp"),
                "time_bucket": base.get("time_bucket"),
                "reclaimed_level_type": base.get("reclaimed_level_type"),
                "gamma_regime": base.get("gamma_regime"),
                "distance_to_gamma_flip_R": base.get("distance_to_gamma_flip_R"),
                "score_bucket": base.get("score_bucket"),
                "confidence_bucket": base.get("confidence_bucket"),
                "cohorts": cohorts,
                "in_1130_1300_long": "C_LONG_1130_1300" in cohorts,
                "in_gex_node_long": "G_LONG_GEX_NODE" in cohorts,
                "in_gamma_flip_long": "H_LONG_GAMMA_FLIP" in cohorts,
                "canonical_R": base.get("canonical_R"),
                "TM_V3_R": base.get("branch_B_R"),
                "canonical_status": base.get("canonical_status"),
                "TM_V3_status": base.get("branch_B_status"),
                "MFE_R": base.get("MFE_R"),
                "MAE_R": base.get("MAE_R"),
            })
        return pd.DataFrame(grouped)

    def _dashboard(self, metrics: pd.DataFrame) -> dict[str, Any]:
        def metric(cohort: str, version: str = "TM_V0_CURRENT") -> dict[str, Any] | None:
            if metrics.empty:
                return None
            rows = metrics[(metrics["cohort"] == cohort) & (metrics["management_version"] == version)]
            return rows.to_dict("records")[0] if not rows.empty else None

        best = None
        if not metrics.empty:
            resolved = metrics[pd.to_numeric(metrics["N"], errors="coerce") >= 20].copy()
            if not resolved.empty:
                best = resolved.sort_values(["expectancy", "N"], ascending=[False, False]).to_dict("records")[0]

        long_row = metric("A_ALL_LONG")
        short_row = metric("B_ALL_SHORT")
        window_row = metric("C_LONG_1130_1300")
        gex_row = metric("G_LONG_GEX_NODE")
        gamma_row = metric("H_LONG_GAMMA_FLIP")

        def expectancy(row: dict[str, Any] | None) -> float | None:
            return row.get("expectancy") if row and int(row.get("N") or 0) > 0 else None

        return {
            "long_forward_expectancy": expectancy(long_row),
            "short_forward_expectancy": expectancy(short_row),
            "long_1130_1300_expectancy": expectancy(window_row),
            "long_gex_node_expectancy": expectancy(gex_row),
            "long_gamma_flip_expectancy": expectancy(gamma_row),
            "best_forward_cohort": self._label_metric({
                "description": f"{best.get('cohort')} / {best.get('management_version')}",
                "expectancy": best.get("expectancy"),
                "sample_n": best.get("N"),
            }) if best else None,
            "cohort_sample_size": int(best.get("N") or 0) if best else 0,
            "cohort_robustness_status": best.get("robustness_status") if best else "INSUFFICIENT_FORWARD_SAMPLE",
            "cohort_promotion_status": best.get("promotion_status") if best else "INSUFFICIENT_FORWARD_SAMPLE",
        }

    def _write_forward_markdown(self, path: Path, activation: dict[str, Any], df: pd.DataFrame,
                                metrics: pd.DataFrame, short_frame: pd.DataFrame,
                                long_frame: pd.DataFrame, outputs: dict[str, str]) -> dict[str, Any]:
        canonical = metrics[metrics["management_version"] == "TM_V0_CURRENT"] if not metrics.empty else pd.DataFrame()
        tm_v3 = metrics[metrics["management_version"] == "TM_V3_TP1_PLUS_RUNNER"] if not metrics.empty else pd.DataFrame()
        unique_setups = df["parent_setup_id"].nunique() if not df.empty and "parent_setup_id" in df else 0
        resolved_unique = df[df.get("outcome_R").notna()]["parent_setup_id"].nunique() if not df.empty and "outcome_R" in df else 0

        def table(frame: pd.DataFrame, cols: list[str], limit: int = 20) -> str:
            if frame.empty:
                return "_No rows yet._"
            lines = ["| " + " | ".join(cols) + " |",
                     "| " + " | ".join("---" for _ in cols) + " |"]
            for row in frame.head(limit).to_dict("records"):
                lines.append("| " + " | ".join(str(row.get(col, "")) for col in cols) + " |")
            return "\n".join(lines)

        summary = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "activation": activation,
            "unique_forward_parent_setups": int(unique_setups),
            "resolved_forward_parent_setups": int(resolved_unique),
            "cohort_rows": int(len(df)),
            "short_diagnostics": int(len(short_frame)),
            "long_validation_rows": int(len(long_frame)),
            "dashboard": self._dashboard(metrics),
            "outputs": outputs,
        }
        summary = self._clean_json(summary)
        canonical_cols = ["cohort", "management_version", "parent_setup_count", "N", "expectancy",
                          "median_R", "profit_factor", "win_rate", "avg_MFE", "avg_MAE",
                          "prob_plus_0_5R_before_minus_1R", "prob_plus_1R_before_minus_1R",
                          "max_drawdown", "top_symbol", "top_symbol_count_share", "promotion_status",
                          "robustness_status"]
        markdown = f"""# Phase 2D.6 Forward Edge Validation

Generated: {summary['generated_at_utc']}

This is a prospective holdout tracker. Phase 2D.5 remains discovery data; no old setup was retrospectively relabeled.

## Activation and guardrails

- Activated at: {activation.get('activated_at_utc')}
- Discovery cutoff: {activation.get('discovery_cutoff_utc')}
- Forward parent setups registered: {summary['unique_forward_parent_setups']}
- Resolved forward parent setups: {summary['resolved_forward_parent_setups']}
- Strategy parameters changed: no
- Canonical paper behavior changed: no
- SHORT setups disabled: no
- Live trading enabled: no
- Portfolio OS integration changed: no

## Decision

No cohort is eligible for promotion until it satisfies the explicit forward thresholds:

- EXPLORATORY: N >= 20
- PRELIMINARY_EDGE: N >= 50, expectancy > 0, PF > 1, and not dominated by one symbol
- FORWARD_SUPPORTED: N >= 100, expectancy > 0, PF > 1, and positive after removing the best symbol, best day, and top five winners

## Canonical management cohorts

{table(canonical, canonical_cols)}

## TM_V3 research management cohorts

{table(tm_v3, canonical_cols)}

## SHORT failure diagnostic

{table(short_frame, ['parent_setup_id', 'symbol', 'timestamp', 'SPY_direction', 'QQQ_direction', 'gamma_regime', 'distance_to_gamma_flip_R', 'time_of_day', 'market_alignment', 'price_first_reached_plus_0_5R', 'later_reversed_to_stop', 'canonical_R'], 20)}

## LONG edge validation sample

{table(long_frame, ['parent_setup_id', 'symbol', 'timestamp', 'time_bucket', 'reclaimed_level_type', 'gamma_regime', 'score_bucket', 'in_1130_1300_long', 'in_gex_node_long', 'in_gamma_flip_long', 'canonical_R', 'TM_V3_R'], 20)}

## Output artifacts

{chr(10).join(f'- `{Path(value).name}`' for value in outputs.values())}
"""
        path.write_text(markdown, encoding="utf-8")
        return summary

    def generate(self, report_date: str | None = None) -> dict[str, Any]:
        del report_date
        self.output_root.mkdir(parents=True, exist_ok=True)
        activation = self.activate()
        outputs = {
            "report": str(self.output_root / "PHASE_2D6_FORWARD_EDGE_VALIDATION.md"),
            "cohorts": str(self.output_root / "forward_edge_cohorts.csv"),
            "short_failure": str(self.output_root / "short_failure_analysis.csv"),
            "long_validation": str(self.output_root / "long_edge_validation.csv"),
        }
        df = self._forward_rows()
        if df.empty:
            df = pd.DataFrame(columns=["parent_setup_id", "symbol", "timestamp", "cohort",
                                       "management_version", "outcome_R", "MFE_R", "MAE_R"])
        metrics = self._cohort_metrics(df)
        short_frame = self._short_failure_frame(df)
        long_frame = self._long_validation_frame(df)
        if metrics.empty:
            metrics = pd.DataFrame(columns=[
                "cohort", "cohort_label", "management_version", "parent_setup_count", "N",
                "open_or_unresolved_N", "total_R", "expectancy", "median_R", "profit_factor",
                "win_rate", "average_winner", "average_loser", "avg_MFE", "avg_MAE",
                "max_drawdown", "prob_plus_0_5R_before_minus_1R", "prob_plus_1R_before_minus_1R",
                "sample_label", "top_symbol", "top_symbol_count_share",
                "top_symbol_abs_contribution_share", "dominated_by_one_symbol",
                "robustness_status", "promotion_status",
            ])
        if short_frame.empty:
            short_frame = pd.DataFrame(columns=[
                "parent_setup_id", "symbol", "timestamp", "SPY_direction", "QQQ_direction",
                "gamma_regime", "distance_to_gamma_flip_R", "time_of_day",
                "against_higher_timeframe_trend", "market_alignment",
                "price_first_reached_plus_0_5R", "price_first_reached_plus_1R",
                "later_reversed_to_stop", "canonical_R", "TM_V3_R", "canonical_status",
                "TM_V3_status",
            ])
        if long_frame.empty:
            long_frame = pd.DataFrame(columns=[
                "parent_setup_id", "symbol", "timestamp", "time_bucket", "reclaimed_level_type",
                "gamma_regime", "distance_to_gamma_flip_R", "score_bucket", "confidence_bucket",
                "cohorts", "in_1130_1300_long", "in_gex_node_long", "in_gamma_flip_long",
                "canonical_R", "TM_V3_R", "canonical_status", "TM_V3_status", "MFE_R", "MAE_R",
            ])
        self._safe_write_frame(metrics, Path(outputs["cohorts"]))
        self._safe_write_frame(short_frame, Path(outputs["short_failure"]))
        self._safe_write_frame(long_frame, Path(outputs["long_validation"]))
        summary = self._write_forward_markdown(Path(outputs["report"]), activation, df, metrics,
                                               short_frame, long_frame, outputs)
        return {"report": summary, "markdown_path": outputs["report"],
                "csv_paths": [outputs["cohorts"], outputs["short_failure"], outputs["long_validation"]]}


class ShortFailureDecompositionReporter(ForwardEdgeValidationReporter):
    """Phase 2D.7 research-only SHORT decomposition and LONG holdout update."""

    SHORT_VARIANTS = {
        "SHORT_TM_A_CURRENT": "current realized paper behavior",
        "SHORT_TM_B_FULL_EXIT_0_5R": "full exit at +0.5R",
        "SHORT_TM_C_HALF_0_5R_REST_BE_RUNNER": "50% at +0.5R, remaining exits at BE or RTH close",
        "SHORT_TM_D_FULL_EXIT_1R": "full exit at +1R",
        "SHORT_TM_E_HALF_0_5R_HALF_1R": "50% at +0.5R, 50% at +1R",
    }

    def __init__(self, repository: Repository, settings: Any, watchlist: Any, output_root: Path):
        super().__init__(repository, settings, watchlist, output_root)
        self.activate_phase2d7()

    def _setup_by_id(self) -> dict[str, dict[str, Any]]:
        return {row.get("setup_event_id"): row for row in self._load_json_rows("setup_events")
                if self._natural(row) and str(row.get("source_mode", "")).startswith("REAL_")}

    def _trade_rows(self) -> list[dict[str, Any]]:
        return [row for row in self._load_json_rows("paper_trades") if self._natural(row)]

    def _rth_close(self, value: datetime) -> datetime:
        local = value.astimezone(EASTERN)
        return datetime.combine(local.date(), time(16, 0), EASTERN).astimezone(timezone.utc)

    def _bars_between(self, bars: dict[str, list[dict[str, Any]]], symbol: str,
                      start: datetime | None, end: datetime | None) -> list[dict[str, Any]]:
        if not start:
            return []
        result = []
        for row in bars.get(symbol.upper(), []):
            bar_end = self._parse_time(row.get("bar_end_utc"))
            if not bar_end or bar_end <= start:
                continue
            if end and bar_end > end:
                continue
            result.append(row)
        return result

    def _time_to_thresholds(self, trade: dict[str, Any], setup: dict[str, Any],
                            bars: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        entry_time = self._parse_time(trade.get("opened_at_utc"))
        close_time = self._parse_time(trade.get("closed_at_utc"))
        if not close_time and entry_time:
            close_time = self._rth_close(entry_time)
        entry = self._safe_float(trade.get("actual_fill_price") or trade.get("planned_entry"))
        stop = self._safe_float(trade.get("stop_initial") or (setup.get("trade_plan") or {}).get("stop_initial"))
        if not entry_time or entry is None or stop is None or entry == stop:
            return {
                "time_to_0_25R": None, "time_to_0_5R": None, "time_to_1R": None,
                "time_to_stop": None, "maximum_R_before_reversal": None,
                "time_from_MFE_to_reversal": None, "mfe_timestamp": None,
                "returned_to_entry": False, "market_reversed_after_first_favorable_excursion": False,
                "strict_hit_0_5R_before_stop": None, "strict_hit_1R_before_stop": None,
            }
        risk = abs(entry - stop)
        thresholds = {0.25: None, 0.5: None, 1.0: None}
        strict = {0.5: None, 1.0: None}
        stop_time = None
        first_favorable_time = None
        reversal_time = None
        returned_to_entry = False
        max_r = 0.0
        max_before_reversal = None
        mfe_time = None
        for bar in self._bars_between(bars, trade["ticker"], entry_time, close_time):
            bar_end = self._parse_time(bar.get("bar_end_utc"))
            if not bar_end:
                continue
            high = self._safe_float(bar.get("high"), entry) or entry
            low = self._safe_float(bar.get("low"), entry) or entry
            favorable = (entry - low) / risk
            adverse = (high - entry) / risk
            if favorable > max_r:
                max_r = favorable
                mfe_time = bar_end
            if first_favorable_time is None and favorable >= 0.25:
                first_favorable_time = bar_end
            for threshold in thresholds:
                if thresholds[threshold] is None and favorable >= threshold:
                    thresholds[threshold] = bar_end
            for threshold in strict:
                if strict[threshold] is None:
                    hit_gain = favorable >= threshold
                    hit_stop = adverse >= 1
                    if hit_gain and not hit_stop:
                        strict[threshold] = True
                    elif hit_stop and not hit_gain:
                        strict[threshold] = False
                    elif hit_gain and hit_stop:
                        strict[threshold] = None
            if first_favorable_time and high >= entry and reversal_time is None:
                returned_to_entry = True
                reversal_time = bar_end
                max_before_reversal = max_r
            if stop_time is None and adverse >= 1:
                stop_time = bar_end
                if reversal_time is None:
                    reversal_time = bar_end
                    max_before_reversal = max_r

        def minutes(when: datetime | None) -> float | None:
            return round((when - entry_time).total_seconds() / 60, 2) if when else None

        return {
            "time_to_0_25R": minutes(thresholds[0.25]),
            "time_to_0_5R": minutes(thresholds[0.5]),
            "time_to_1R": minutes(thresholds[1.0]),
            "time_to_stop": minutes(stop_time),
            "maximum_R_before_reversal": round(max_before_reversal if max_before_reversal is not None else max_r, 4),
            "time_from_MFE_to_reversal": round((reversal_time - mfe_time).total_seconds() / 60, 2)
            if reversal_time and mfe_time and reversal_time >= mfe_time else None,
            "mfe_timestamp": mfe_time.isoformat() if mfe_time else None,
            "returned_to_entry": returned_to_entry,
            "market_reversed_after_first_favorable_excursion": bool(first_favorable_time and reversal_time),
            "strict_hit_0_5R_before_stop": strict[0.5],
            "strict_hit_1R_before_stop": strict[1.0],
        }

    def _entry_timing(self, trade: dict[str, Any], setup: dict[str, Any]) -> dict[str, Any]:
        snapshot = setup.get("signal_snapshot") or {}
        level = snapshot.get("level") or {}
        confirmation = snapshot.get("confirmation_bar") or {}
        reclaim_at = self._parse_time(confirmation.get("bar_end_utc") or setup.get("created_at_utc"))
        entry_at = self._parse_time(trade.get("opened_at_utc"))
        entry = self._safe_float(trade.get("actual_fill_price") or trade.get("planned_entry"))
        level_price = self._safe_float(level.get("price") or setup.get("level_price"))
        atr = self._safe_float(confirmation.get("atr"))
        delay_minutes = round((entry_at - reclaim_at).total_seconds() / 60, 2) if entry_at and reclaim_at else None
        delay_candles = round(delay_minutes / 5, 2) if delay_minutes is not None else None
        if delay_candles is None:
            delay_bucket = "NO_FILL"
        elif delay_candles <= 0:
            delay_bucket = "same_candle"
        elif delay_candles <= 1:
            delay_bucket = "1_candle_after_reclaim"
        else:
            delay_bucket = "2_plus_candles_after_reclaim"
        signed_distance = (level_price - entry) if entry is not None and level_price is not None else None
        extension_atr = abs(signed_distance) / atr if signed_distance is not None and atr else None
        return {
            "reclaim_timestamp": reclaim_at.isoformat() if reclaim_at else None,
            "entry_delay_minutes": delay_minutes,
            "entry_delay_candles": delay_candles,
            "entry_delay_bucket": delay_bucket,
            "distance_from_reclaimed_level_at_entry": round(signed_distance, 6) if signed_distance is not None else None,
            "price_extension_from_level_ATR": round(extension_atr, 4) if extension_atr is not None else None,
            "entry_after_first_impulse_exhausted": bool(delay_candles is not None and delay_candles >= 2
                                                        and extension_atr is not None and extension_atr >= 0.5),
        }

    def _trend_features(self, setup: dict[str, Any], bars: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        symbol = str(setup.get("ticker", "")).upper()
        at = self._parse_time(setup.get("created_at_utc"))
        spy_15m = self._trend_lookback(bars, "SPY", at, 15)
        qqq_15m = self._trend_lookback(bars, "QQQ", at, 15)
        symbol_15m = self._trend_lookback(bars, symbol, at, 15)
        symbol_1h = self._trend_lookback(bars, symbol, at, 60)
        alignment = self._short_alignment_class(spy_15m, qqq_15m, symbol_15m, symbol_1h)
        return {
            "SPY_15m_trend": spy_15m,
            "QQQ_15m_trend": qqq_15m,
            "symbol_15m_trend": symbol_15m,
            "symbol_1h_trend": symbol_1h,
            "short_alignment_class": alignment,
        }

    def _short_classification(self, row: dict[str, Any]) -> str:
        realized = self._safe_float(row.get("realized_R"), 0.0) or 0.0
        mfe = self._safe_float(row.get("MFE_R"), 0.0) or 0.0
        time_to_stop = self._safe_float(row.get("time_to_stop"))
        if row.get("entry_timestamp") is None:
            return "NO_EDGE"
        if row.get("short_alignment_class") == "COUNTERTREND" and realized < -0.25:
            return "COUNTERTREND_FAILURE"
        if time_to_stop is not None and time_to_stop <= 5 and mfe < 0.25:
            return "IMMEDIATE_FAILURE"
        if row.get("entry_after_first_impulse_exhausted") and realized < 0:
            return "LATE_ENTRY"
        if mfe < 0.25 and realized < 0:
            return "NO_EDGE"
        if mfe >= 1.0 and realized < 0.25:
            return "GOOD_MOVE_POOR_EXIT"
        if mfe >= 0.5 and realized < 0:
            return "EARLY_MFE_THEN_REVERSAL"
        if realized >= 0.5:
            return "GOOD_MOVE_FULLY_MONETIZED"
        return "GOOD_MOVE_POOR_EXIT" if mfe >= 0.5 else "NO_EDGE"

    def _short_path_decomposition(self) -> list[dict[str, Any]]:
        setup_by_id = self._setup_by_id()
        bars = self._bars_index()
        rows = []
        for trade in sorted(self._trade_rows(), key=lambda item: item.get("created_at_utc") or ""):
            if trade.get("side") != "SHORT" or trade.get("status") not in self.FINAL_TRADE_STATUSES:
                continue
            setup = setup_by_id.get(trade.get("setup_event_id"))
            if not setup:
                continue
            entry = self._safe_float(trade.get("actual_fill_price") or trade.get("planned_entry"))
            stop = self._safe_float(trade.get("stop_initial"))
            risk = abs(entry - stop) if entry is not None and stop is not None else None
            timing = self._entry_timing(trade, setup)
            path = self._time_to_thresholds(trade, setup, bars)
            trend = self._trend_features(setup, bars)
            targets = trade.get("targets") or []
            tp1 = self._safe_float(targets[0]) if targets else None
            time_to_tp1 = path.get("time_to_1R") if tp1 is None else (
                path.get("time_to_0_5R") if risk and abs((entry or 0) - tp1) / risk <= 0.5 else path.get("time_to_1R"))
            row = {
                "parent_setup_id": setup.get("setup_event_id"),
                "trade_id": trade.get("trade_id"),
                "symbol": trade.get("ticker"),
                "lane": trade.get("mode"),
                "setup_family": setup.get("setup_type"),
                "level_type": setup.get("level_type"),
                "time_bucket": self._time_bucket(self._parse_time(setup.get("created_at_utc"))),
                "entry_timestamp": trade.get("opened_at_utc"),
                "closed_at_utc": trade.get("closed_at_utc"),
                "entry_price": entry,
                "stop": stop,
                "initial_risk_R": risk,
                "MFE_R": self._safe_float(trade.get("mfe_r")),
                "MAE_R": self._safe_float(trade.get("mae_r")),
                "realized_R": self._safe_float(trade.get("realized_r")),
                "exit_reason": trade.get("exit_reason"),
                "status": trade.get("status"),
                "MFE_occurred_before_TP1": None if time_to_tp1 is None or path.get("mfe_timestamp") is None
                else (self._safe_float(path.get("time_from_MFE_to_reversal"), 0.0) is not None and
                      (path.get("time_to_0_5R") or 0) <= time_to_tp1),
                "trade_later_returned_to_entry": path.get("returned_to_entry"),
                "trade_reached_BE_before_loss": bool(trade.get("exit_reason") == "breakeven_stop"
                                                     or any(event.get("event_type") == "STOP_MOVE"
                                                            for event in trade.get("events", []))),
                **timing,
                **trend,
                **path,
            }
            row["short_failure_class"] = self._short_classification(row)
            rows.append(row)
        return rows

    def _stats_from_frame(self, frame: pd.DataFrame, outcome_col: str = "realized_R") -> dict[str, Any]:
        if frame.empty:
            return self._stats(pd.DataFrame(columns=[outcome_col, "MFE_R", "MAE_R"]), outcome_col)
        renamed = frame.copy()
        if "MFE_R" not in renamed and "mfe_r" in renamed:
            renamed["MFE_R"] = renamed["mfe_r"]
        if "MAE_R" not in renamed and "mae_r" in renamed:
            renamed["MAE_R"] = renamed["mae_r"]
        return self._stats(renamed, outcome_col)

    def _group_stats(self, frame: pd.DataFrame, dimension: str, outcome_col: str = "realized_R") -> pd.DataFrame:
        rows = []
        if frame.empty or dimension not in frame:
            return pd.DataFrame(rows)
        for bucket, group in frame.groupby(dimension, dropna=False):
            stats = self._stats_from_frame(group, outcome_col)
            rows.append({"dimension": dimension, "bucket": "UNKNOWN" if pd.isna(bucket) else str(bucket), **stats})
        rows.sort(key=lambda item: item["bucket"])
        return pd.DataFrame(rows)

    def _simulate_short_variant(self, row: dict[str, Any], variant: str,
                                bars: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        if variant == "SHORT_TM_A_CURRENT":
            return {
                "variant": variant,
                "variant_description": self.SHORT_VARIANTS[variant],
                "realized_R": row.get("realized_R"),
                "exit_reason": row.get("exit_reason"),
                "MFE_R": row.get("MFE_R"),
                "MAE_R": row.get("MAE_R"),
            }
        entry_time = self._parse_time(row.get("entry_timestamp"))
        entry = self._safe_float(row.get("entry_price"))
        stop = self._safe_float(row.get("stop"))
        if not entry_time or entry is None or stop is None or entry == stop:
            return {"variant": variant, "variant_description": self.SHORT_VARIANTS[variant],
                    "realized_R": None, "exit_reason": "unfilled_or_invalid_entry",
                    "MFE_R": row.get("MFE_R"), "MAE_R": row.get("MAE_R")}
        risk = abs(entry - stop)
        end = self._parse_time(row.get("closed_at_utc")) or self._rth_close(entry_time)
        realized = 0.0
        remaining = 1.0
        stop_current = stop
        hit_05 = False
        final_reason = "rth_close"
        mfe = mae = 0.0
        last_close = entry
        events = []
        for bar in self._bars_between(bars, row["symbol"], entry_time, end):
            high = self._safe_float(bar.get("high"), entry) or entry
            low = self._safe_float(bar.get("low"), entry) or entry
            close = self._safe_float(bar.get("close"), entry) or entry
            last_close = close
            favorable = (entry - low) / risk
            adverse = (high - entry) / risk
            mfe = max(mfe, favorable)
            mae = max(mae, adverse)
            stop_hit = high >= stop_current
            hit_half = favorable >= 0.5
            hit_one = favorable >= 1.0
            if variant == "SHORT_TM_B_FULL_EXIT_0_5R":
                if stop_hit and not hit_half:
                    realized = -1.0
                    final_reason = "stop_before_0_5R"
                    break
                if hit_half:
                    realized = 0.5
                    final_reason = "full_exit_0_5R"
                    break
            elif variant == "SHORT_TM_D_FULL_EXIT_1R":
                if stop_hit and not hit_one:
                    realized = -1.0
                    final_reason = "stop_before_1R"
                    break
                if hit_one:
                    realized = 1.0
                    final_reason = "full_exit_1R"
                    break
            elif variant == "SHORT_TM_C_HALF_0_5R_REST_BE_RUNNER":
                if not hit_05 and stop_hit and not hit_half:
                    realized = -1.0
                    remaining = 0.0
                    final_reason = "stop_before_0_5R"
                    break
                if not hit_05 and hit_half:
                    realized += 0.25
                    remaining = 0.5
                    stop_current = entry
                    hit_05 = True
                    events.append("half_exit_0_5R_stop_to_BE")
                elif hit_05 and high >= stop_current:
                    final_reason = "runner_breakeven"
                    remaining = 0.0
                    break
            elif variant == "SHORT_TM_E_HALF_0_5R_HALF_1R":
                if not hit_05 and stop_hit and not hit_half:
                    realized = -1.0
                    remaining = 0.0
                    final_reason = "stop_before_0_5R"
                    break
                if not hit_05 and hit_half:
                    realized += 0.25
                    remaining = 0.5
                    hit_05 = True
                    events.append("half_exit_0_5R")
                if hit_05 and hit_one:
                    realized += 0.5
                    remaining = 0.0
                    final_reason = "second_half_exit_1R"
                    break
                if hit_05 and stop_hit:
                    realized -= 0.5
                    remaining = 0.0
                    final_reason = "remaining_half_initial_stop"
                    break
        if remaining > 0:
            close_r = (entry - last_close) / risk
            realized += close_r * remaining
        return {
            "variant": variant,
            "variant_description": self.SHORT_VARIANTS[variant],
            "realized_R": round(realized, 6),
            "exit_reason": final_reason,
            "MFE_R": round(mfe, 6),
            "MAE_R": round(mae, 6),
            "events": events,
        }

    def _short_management_replay(self, decomp: pd.DataFrame) -> pd.DataFrame:
        rows = []
        bars = self._bars_index()
        for row in decomp.to_dict("records") if not decomp.empty else []:
            for variant in self.SHORT_VARIANTS:
                replay = self._simulate_short_variant(row, variant, bars)
                rows.append({
                    "parent_setup_id": row.get("parent_setup_id"),
                    "trade_id": row.get("trade_id"),
                    "symbol": row.get("symbol"),
                    "time_bucket": row.get("time_bucket"),
                    "level_type": row.get("level_type"),
                    "short_alignment_class": row.get("short_alignment_class"),
                    "short_failure_class": row.get("short_failure_class"),
                    **replay,
                })
        return pd.DataFrame(rows)

    def _short_time_bucket_forward(self) -> pd.DataFrame:
        forward = self._forward_rows()
        rows = []
        if forward.empty:
            return pd.DataFrame(rows)
        short_rows = forward[forward["direction"] == "SHORT"].copy()
        for (bucket, version), group in short_rows.groupby(["time_bucket", "management_version"], dropna=False):
            stats = self._stats_from_frame(group.rename(columns={"outcome_R": "realized_R"}), "realized_R")
            rows.append({"time_bucket": bucket, "management_version": version,
                         "parent_setup_count": int(group["parent_setup_id"].nunique()), **stats})
        rows.sort(key=lambda item: (str(item["time_bucket"]), str(item["management_version"])))
        return pd.DataFrame(rows)

    def _long_midday_holdout(self) -> pd.DataFrame:
        forward = self._forward_rows()
        rows = []
        if forward.empty:
            return pd.DataFrame(rows)
        subset = forward[forward["cohort"] == "C_LONG_1130_1300"].copy()
        for version, group in subset.groupby("management_version", dropna=False):
            frame = group[group["outcome_R"].notna()].copy() if "outcome_R" in group else pd.DataFrame()
            stats = self._stats_from_frame(frame.rename(columns={"outcome_R": "realized_R"}), "realized_R")
            values = [float(value) for value in pd.to_numeric(frame.get("outcome_R"), errors="coerce").dropna()] if not frame.empty else []
            ci = self._bootstrap_values(values)
            concentration = self._concentration_stats(frame)
            remove_symbol = self._removal_stats(frame, "symbol")
            remove_day = self._removal_stats(frame, "session_date")
            rows.append({
                "cohort": "C_LONG_1130_1300",
                "management_version": version,
                "parent_setup_count": int(group["parent_setup_id"].nunique()),
                "resolved_N": stats["N"],
                "unresolved_N": int(group["parent_setup_id"].nunique()) - int(frame["parent_setup_id"].nunique()) if not frame.empty else int(group["parent_setup_id"].nunique()),
                "expectancy": stats["expectancy"],
                "profit_factor": stats["profit_factor"],
                "win_rate": stats["win_rate"],
                "max_drawdown": stats["max_drawdown"],
                "avg_MFE": stats["avg_MFE"],
                "avg_MAE": stats["avg_MAE"],
                "bootstrap_expectancy_ci_low": ci.get("low"),
                "bootstrap_expectancy_ci_high": ci.get("high"),
                **concentration,
                "remove_best_symbol_expectancy": remove_symbol.get("expectancy"),
                "remove_best_symbol_PF": remove_symbol.get("profit_factor"),
                "remove_best_day_expectancy": remove_day.get("expectancy"),
                "remove_best_day_PF": remove_day.get("profit_factor"),
                "promotion_status": "PRELIMINARY_EDGE" if stats["N"] >= 50 and stats["expectancy"] and stats["expectancy"] > 0
                and (math.inf if stats["profit_factor"] == "infinite" else (self._safe_float(stats["profit_factor"]) or 0)) > 1
                and not concentration.get("symbol_dominated") and not concentration.get("day_dominated") else
                ("EXPLORATORY" if stats["N"] >= 20 and stats["expectancy"] and stats["expectancy"] > 0 else
                 "INSUFFICIENT_SAMPLE" if stats["N"] < 20 else "REJECTED"),
            })
        return pd.DataFrame(rows)

    def _bootstrap_values(self, values: list[float], iterations: int = 500) -> dict[str, Any]:
        if not values:
            return {"low": None, "high": None}
        rng = random.Random(20260903)
        means = []
        for _ in range(iterations):
            sample = [values[rng.randrange(len(values))] for _ in values]
            means.append(sum(sample) / len(sample))
        return {"low": self._percentile(means, 2.5), "high": self._percentile(means, 97.5)}

    def _concentration_stats(self, frame: pd.DataFrame) -> dict[str, Any]:
        if frame.empty:
            return {"top_symbol": None, "top_symbol_share": 0.0, "symbol_dominated": False,
                    "top_day": None, "top_day_share": 0.0, "day_dominated": False}
        symbol_counts = frame.groupby("symbol")["parent_setup_id"].nunique().sort_values(ascending=False)
        day_counts = frame.groupby("session_date")["parent_setup_id"].nunique().sort_values(ascending=False)
        total = max(1, int(frame["parent_setup_id"].nunique()))
        top_symbol_share = float(symbol_counts.iloc[0] / total) if not symbol_counts.empty else 0.0
        top_day_share = float(day_counts.iloc[0] / total) if not day_counts.empty else 0.0
        return {
            "top_symbol": str(symbol_counts.index[0]) if not symbol_counts.empty else None,
            "top_symbol_share": round(top_symbol_share, 4),
            "symbol_dominated": top_symbol_share >= 0.35,
            "top_day": str(day_counts.index[0]) if not day_counts.empty else None,
            "top_day_share": round(top_day_share, 4),
            "day_dominated": top_day_share >= 0.60,
        }

    def _removal_stats(self, frame: pd.DataFrame, column: str) -> dict[str, Any]:
        if frame.empty or column not in frame:
            return self._stats_from_frame(pd.DataFrame(), "realized_R")
        totals = frame.groupby(column)["outcome_R"].sum().sort_values(ascending=False)
        if totals.empty:
            return self._stats_from_frame(pd.DataFrame(), "realized_R")
        reduced = frame[frame[column] != totals.index[0]].copy()
        return self._stats_from_frame(reduced.rename(columns={"outcome_R": "realized_R"}), "realized_R")

    @staticmethod
    def _ensure_columns(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
        if frame.empty:
            return pd.DataFrame(columns=columns)
        for column in columns:
            if column not in frame:
                frame[column] = None
        return frame[columns + [column for column in frame.columns if column not in columns]]

    def _write_phase2d7_markdown(self, path: Path, outputs: dict[str, str], activation: dict[str, Any],
                                  decomp: pd.DataFrame, entry: pd.DataFrame, alignment: pd.DataFrame,
                                  time_forward: pd.DataFrame, replay: pd.DataFrame,
                                  long_midday: pd.DataFrame) -> dict[str, Any]:
        class_counts = Counter(decomp["short_failure_class"]) if not decomp.empty and "short_failure_class" in decomp else Counter()
        current_replay = replay[replay["variant"] == "SHORT_TM_A_CURRENT"] if not replay.empty and "variant" in replay else pd.DataFrame()
        replay_summary = self._group_stats(replay, "variant", "realized_R") if not replay.empty else pd.DataFrame()
        short_stats = self._stats_from_frame(decomp, "realized_R")

        def table(frame: pd.DataFrame, cols: list[str], limit: int = 20) -> str:
            if frame.empty:
                return "_No rows yet._"
            lines = ["| " + " | ".join(cols) + " |",
                     "| " + " | ".join("---" for _ in cols) + " |"]
            for row in frame.head(limit).to_dict("records"):
                lines.append("| " + " | ".join(str(row.get(col, "")) for col in cols) + " |")
            return "\n".join(lines)

        summary = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "activation": activation,
            "resolved_short_setups": int(len(decomp)),
            "short_expectancy": short_stats.get("expectancy"),
            "short_profit_factor": short_stats.get("profit_factor"),
            "classification_counts": dict(class_counts),
            "current_replay_rows": int(len(current_replay)),
            "outputs": outputs,
        }
        summary = self._clean_json(summary)
        markdown = f"""# Phase 2D.7 SHORT Failure Decomposition

Generated: {summary['generated_at_utc']}

Research-only diagnostics. Canonical/live strategy parameters, thresholds, score weights, setup definitions, watchlist, stops, targets, provider gates, and management variants were not changed.

## Activation

- Phase 2D.7 activated at: {activation.get('activated_at_utc')}
- New prospective cohort: `SHORT_13_00_14_30`
- Existing Phase 2D.6 cohorts continue unchanged.
- SHORT rules were not disabled or optimized.

## Resolved SHORT summary

- Resolved natural SHORT setups analyzed: {summary['resolved_short_setups']}
- Current SHORT expectancy: {summary['short_expectancy']}R
- Current SHORT PF: {summary['short_profit_factor']}
- Classification counts: {dict(class_counts)}

## SHORT classification

{table(pd.DataFrame([{'class': key, 'count': value} for key, value in class_counts.items()]).sort_values('count', ascending=False) if class_counts else pd.DataFrame(), ['class', 'count'])}

## Entry timing

{table(entry, ['bucket', 'N', 'expectancy', 'profit_factor', 'win_rate', 'avg_MFE', 'avg_MAE', 'max_drawdown'])}

## Market alignment

{table(alignment, ['bucket', 'N', 'expectancy', 'profit_factor', 'win_rate', 'avg_MFE', 'avg_MAE', 'max_drawdown'])}

## Forward SHORT time buckets

{table(time_forward, ['time_bucket', 'management_version', 'parent_setup_count', 'N', 'expectancy', 'profit_factor', 'win_rate', 'avg_MFE', 'avg_MAE', 'max_drawdown'])}

## SHORT-only management replay

{table(replay_summary, ['bucket', 'N', 'expectancy', 'profit_factor', 'win_rate', 'avg_MFE', 'avg_MAE', 'max_drawdown'])}

## LONG 11:30–13:00 holdout continuation

{table(long_midday, ['management_version', 'parent_setup_count', 'resolved_N', 'unresolved_N', 'expectancy', 'profit_factor', 'win_rate', 'max_drawdown', 'top_symbol', 'top_symbol_share', 'top_day', 'top_day_share', 'bootstrap_expectancy_ci_low', 'bootstrap_expectancy_ci_high', 'promotion_status'])}

## Output artifacts

{chr(10).join(f'- `{Path(value).name}`' for value in outputs.values())}
"""
        path.write_text(markdown, encoding="utf-8")
        return summary

    def generate_phase2d7(self, report_date: str | None = None) -> dict[str, Any]:
        del report_date
        self.output_root.mkdir(parents=True, exist_ok=True)
        activation = self.activate_phase2d7()
        outputs = {
            "report": str(self.output_root / "PHASE_2D7_SHORT_FAILURE_DECOMPOSITION.md"),
            "short_path_decomposition": str(self.output_root / "short_path_decomposition.csv"),
            "short_entry_timing": str(self.output_root / "short_entry_timing.csv"),
            "short_market_alignment": str(self.output_root / "short_market_alignment.csv"),
            "short_time_bucket_forward": str(self.output_root / "short_time_bucket_forward.csv"),
            "short_management_replay": str(self.output_root / "short_management_replay.csv"),
            "long_midday_holdout_update": str(self.output_root / "long_midday_holdout_update.csv"),
        }
        decomp = pd.DataFrame(self._short_path_decomposition())
        decomp = self._ensure_columns(decomp, [
            "parent_setup_id", "trade_id", "symbol", "lane", "level_type", "time_bucket",
            "entry_timestamp", "closed_at_utc", "entry_price", "stop", "initial_risk_R", "MFE_R", "MAE_R",
            "time_to_0_25R", "time_to_0_5R", "time_to_1R", "time_to_stop",
            "maximum_R_before_reversal", "realized_R", "time_from_MFE_to_reversal",
            "MFE_occurred_before_TP1", "trade_later_returned_to_entry",
            "trade_reached_BE_before_loss", "market_reversed_after_first_favorable_excursion",
            "entry_delay_candles", "entry_delay_minutes", "entry_delay_bucket",
            "distance_from_reclaimed_level_at_entry", "price_extension_from_level_ATR",
            "entry_after_first_impulse_exhausted", "SPY_15m_trend", "QQQ_15m_trend",
            "symbol_15m_trend", "symbol_1h_trend", "short_alignment_class",
            "strict_hit_0_5R_before_stop", "strict_hit_1R_before_stop", "short_failure_class",
        ])
        entry = self._group_stats(decomp, "entry_delay_bucket", "realized_R")
        alignment = self._group_stats(decomp, "short_alignment_class", "realized_R")
        time_forward = self._short_time_bucket_forward()
        replay = self._short_management_replay(decomp)
        long_midday = self._long_midday_holdout()

        self._safe_write_frame(decomp, Path(outputs["short_path_decomposition"]))
        self._safe_write_frame(entry, Path(outputs["short_entry_timing"]))
        self._safe_write_frame(alignment, Path(outputs["short_market_alignment"]))
        self._safe_write_frame(time_forward, Path(outputs["short_time_bucket_forward"]))
        self._safe_write_frame(replay, Path(outputs["short_management_replay"]))
        self._safe_write_frame(long_midday, Path(outputs["long_midday_holdout_update"]))
        summary = self._write_phase2d7_markdown(Path(outputs["report"]), outputs, activation, decomp,
                                                entry, alignment, time_forward, replay, long_midday)
        return {"report": summary, "markdown_path": outputs["report"],
                "csv_paths": [value for key, value in outputs.items() if key != "report"]}
