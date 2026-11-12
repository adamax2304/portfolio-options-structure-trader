from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

from options_structure_trader.phase4b1 import (
    classify_direction,
    classify_structure,
    entry_quality,
    giveback_bucket,
    loss_reason,
    max_drawdown,
    profit_factor,
    safe_float,
    stat_summary,
)


PHASE_NAMESPACE = "PHASE_4B2H_HISTORICAL_EXECUTION_DIAGNOSTIC"
REPORT_NAME = "PHASE_4B2H_HISTORICAL_EXECUTION_DIAGNOSTIC.md"
HIST_SOURCE = "HIST_STATIC_D1"
LIVE_SOURCE = "LIVE_RECORDED_RETROSPECTIVE"


STOP_EXPERIMENT_MAP = {
    "STOP_A_CURRENT_STRUCTURAL": "S0_CANONICAL_STOP",
    "STOP_E_ZONE_INVALIDATION": "S1_FULL_OPTIONS_ZONE_INVALIDATION",
    "STOP_D_STRUCTURE_PLUS_0_50_ATR": "S2_15M_STRUCTURAL_INVALIDATION_PROXY",
    "STOP_C_STRUCTURE_PLUS_0_30_ATR": "S3_LAST_CONFIRMED_HL_LH_INVALIDATION_PROXY",
    "STOP_B_STRUCTURE_PLUS_0_15_ATR": "RESEARCH_STRUCTURE_PLUS_0_15_ATR",
}


FORWARD_ONLY_FIELDS = [
    "true_intraday_options_persistence",
    "strengthening_weakening_across_live_snapshots",
    "wall_migration",
    "gamma_flip_migration",
    "dynamic_intraday_GEX_change",
]


def json_text(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, default=str)
    except TypeError:
        return json.dumps(str(value))


def _clean_scalar(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (dict, list, tuple, set)):
        return json_text(value)
    return value


def write_parquet_safe(df: pd.DataFrame, path: Path) -> None:
    frame = df.copy()
    for column in frame.columns:
        if frame[column].dtype == "object":
            frame[column] = frame[column].map(
                lambda value: None if _clean_scalar(value) is None else str(_clean_scalar(value))
            )
    frame.to_parquet(path, index=False)


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return bool(value)


def numeric(series: pd.Series | Iterable[Any]) -> pd.Series:
    return pd.to_numeric(pd.Series(series), errors="coerce")


def reached(series: pd.Series, threshold: float) -> float | None:
    vals = numeric(series).dropna()
    if vals.empty:
        return None
    return round(float((vals >= threshold).mean()), 4)


def pctl(series: pd.Series | Iterable[Any], q: float) -> float | None:
    vals = numeric(series).dropna()
    if vals.empty:
        return None
    return round(float(vals.quantile(q)), 4)


def day_block_ci(values_by_day: pd.Series, iterations: int = 500) -> tuple[float | None, float | None]:
    vals = numeric(values_by_day).dropna().tolist()
    if len(vals) < 2:
        return None, None
    # Deterministic bootstrap without requiring numpy.
    samples: list[float] = []
    n = len(vals)
    seed = 17
    for _ in range(iterations):
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        total = 0.0
        local = seed
        for _j in range(n):
            local = (local * 1103515245 + 12345) & 0x7FFFFFFF
            total += vals[local % n]
        samples.append(total / n)
    samples.sort()
    lo = samples[int(0.025 * (len(samples) - 1))]
    hi = samples[int(0.975 * (len(samples) - 1))]
    return round(lo, 4), round(hi, 4)


def summary_row(df: pd.DataFrame, label: str | None = None, result_col: str = "result_R") -> dict[str, Any]:
    vals = numeric(df[result_col]) if result_col in df.columns else pd.Series(dtype="float64")
    resolved = df[vals.notna()].copy() if not df.empty and len(vals) == len(df) else pd.DataFrame()
    stats = stat_summary(resolved[result_col] if not resolved.empty else [])
    out: dict[str, Any] = {
        "label": label,
        "N": stats["N"],
        "unique_days": int(resolved["trade_date"].nunique()) if "trade_date" in resolved.columns and not resolved.empty else 0,
        "expectancy": stats["expectancy"],
        "PF": stats["PF"],
        "win_rate": stats["win_rate"],
        "median_R": stats["median_R"],
        "avg_winner": stats["avg_winner"],
        "avg_loser": stats["avg_loser"],
        "total_R": stats["total_R"],
        "MFE": round(float(numeric(resolved["MFE_R"]).mean()), 4) if "MFE_R" in resolved and not resolved.empty else None,
        "MAE": round(float(numeric(resolved["MAE_R"]).mean()), 4) if "MAE_R" in resolved and not resolved.empty else None,
        "median_MFE": pctl(resolved["MFE_R"], 0.50) if "MFE_R" in resolved and not resolved.empty else None,
        "median_MAE": pctl(resolved["MAE_R"], 0.50) if "MAE_R" in resolved and not resolved.empty else None,
        "max_DD": stats["max_drawdown"],
        "positive_day_pct": None,
        "day_block_ci_low": None,
        "day_block_ci_high": None,
        "P_0_5R_before_minus_1R": reached(resolved["MFE_R"], 0.5) if "MFE_R" in resolved and not resolved.empty else None,
        "P_0_7R_before_minus_1R": reached(resolved["MFE_R"], 0.7) if "MFE_R" in resolved and not resolved.empty else None,
        "P_1R_before_minus_1R": reached(resolved["MFE_R"], 1.0) if "MFE_R" in resolved and not resolved.empty else None,
    }
    if not resolved.empty and "trade_date" in resolved.columns:
        daily = resolved.groupby("trade_date")[result_col].sum()
        out["positive_day_pct"] = round(float((daily > 0).mean()), 4) if not daily.empty else None
        lo, hi = day_block_ci(daily)
        out["day_block_ci_low"] = lo
        out["day_block_ci_high"] = hi
    return out


def grouped_summary(df: pd.DataFrame, group_cols: list[str], result_col: str = "result_R") -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    existing = [col for col in group_cols if col in df.columns]
    if not existing:
        return pd.DataFrame([summary_row(df, "ALL", result_col)])
    rows: list[dict[str, Any]] = []
    for keys, group in df.groupby(existing, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        row = {col: "UNKNOWN" if pd.isna(value) else value for col, value in zip(existing, keys)}
        row.update(summary_row(group, None, result_col))
        row.pop("label", None)
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["N"], ascending=False, ignore_index=True)


def research_status(n: int, days: int, expectancy: float | None, pf: float | None) -> str:
    if days < 2 or n < 30:
        return "DESCRIPTIVE_INSUFFICIENT_SAMPLE"
    if days < 5 or n < 75:
        return "EXPLORATORY"
    if expectancy is not None and pf is not None and expectancy > 0 and pf > 1:
        return "HYPOTHESIS_GENERATING_POSITIVE_HOLDOUT_REQUIRED"
    return "HYPOTHESIS_GENERATING_NEGATIVE_OR_MIXED"


@dataclass(frozen=True)
class ReplayResult:
    variant: str
    result_R: float | None
    exit_reason: str
    mfe_R: float | None
    mae_R: float | None
    duration_minutes: float | None
    be_exit: bool = False
    giveback_R: float | None = None
    capture_efficiency: float | None = None


class Phase4B2HHistoricalDiagnostic:
    """Research-only historical execution diagnostic.

    This class reads existing historical/live retrospective artifacts and writes a separate
    Phase 4B.2-H report. It does not alter the live daemon, prospective Phase 4B.2
    experiments, canonical strategy parameters, database rows, or Portfolio OS boundaries.
    """

    REPORT_VERSION = "phase4b2h_historical_execution_diagnostic_v1"

    def __init__(self, root: Path):
        self.root = Path(root)
        self.generated_at_utc = datetime.now(timezone.utc).isoformat()

    def run(self) -> dict[str, Any]:
        hist_events = self._read_parquet("phase4a_historical_events.parquet")
        hist_branches = self._read_parquet("phase4a_historical_branches.parquet")
        live_master = self._read_parquet("edge_master_dataset.parquet")
        candles = self._read_parquet("historical_intraday_5m_v2.parquet")

        events = self._build_events(hist_events, live_master)
        branches = self._build_branches(hist_branches, live_master, events)
        baseline = self._baseline_branches(branches)
        historical_baseline = baseline[baseline["data_source"] == HIST_SOURCE].copy()

        write_parquet_safe(events, self.root / "phase4b2h_events.parquet")

        stop_comparison = self._stop_comparison(branches)
        winner_mae = self._winner_mae(baseline)
        stop_recovery = self._stop_recovery(historical_baseline, candles)
        giveback = self._giveback(baseline)
        management_sim = self._simulate_management(historical_baseline, candles)
        breakeven = self._breakeven(management_sim)
        target_distribution = self._target_distribution(baseline, management_sim)
        holding_horizon = self._holding_horizon(baseline)
        structure_5m_vs_15m = self._structure_5m_vs_15m(branches)
        direction_classifier = self._direction_classifier(events, baseline)
        entry_comparison = self._entry_comparison(branches)
        options_ablation = self._options_ablation(branches)
        loss_attribution = self._loss_attribution(baseline, stop_recovery)
        counterfactual_rescue = self._counterfactual_rescue(baseline)
        discovery_holdout = self._discovery_holdout(branches)
        walkforward = self._walkforward(baseline)

        outputs = {
            "phase4b2h_stop_comparison.csv": stop_comparison,
            "phase4b2h_winner_mae.csv": winner_mae,
            "phase4b2h_stop_recovery.csv": stop_recovery,
            "phase4b2h_giveback.csv": giveback,
            "phase4b2h_breakeven.csv": breakeven,
            "phase4b2h_target_distribution.csv": target_distribution,
            "phase4b2h_holding_horizon.csv": holding_horizon,
            "phase4b2h_structure_5m_vs_15m.csv": structure_5m_vs_15m,
            "phase4b2h_direction_classifier.csv": direction_classifier,
            "phase4b2h_entry_comparison.csv": entry_comparison,
            "phase4b2h_options_ablation.csv": options_ablation,
            "phase4b2h_loss_attribution.csv": loss_attribution,
            "phase4b2h_counterfactual_rescue.csv": counterfactual_rescue,
            "phase4b2h_discovery_holdout.csv": discovery_holdout,
            "phase4b2h_walkforward.csv": walkforward,
            "phase4b2h_management_simulation.csv": management_sim,
        }
        for name, frame in outputs.items():
            frame.to_csv(self.root / name, index=False)

        report = self._render_report(
            events=events,
            branches=branches,
            baseline=baseline,
            stop_comparison=stop_comparison,
            winner_mae=winner_mae,
            stop_recovery=stop_recovery,
            giveback=giveback,
            breakeven=breakeven,
            target_distribution=target_distribution,
            holding_horizon=holding_horizon,
            structure_5m_vs_15m=structure_5m_vs_15m,
            direction_classifier=direction_classifier,
            entry_comparison=entry_comparison,
            options_ablation=options_ablation,
            loss_attribution=loss_attribution,
            counterfactual_rescue=counterfactual_rescue,
            discovery_holdout=discovery_holdout,
            walkforward=walkforward,
        )
        (self.root / REPORT_NAME).write_text(report, encoding="utf-8")

        return {
            "generated_at_utc": self.generated_at_utc,
            "namespace": PHASE_NAMESPACE,
            "report_path": str(self.root / REPORT_NAME),
            "events": int(len(events)),
            "branches_read": int(len(branches)),
            "baseline_branches": int(len(baseline)),
            "historical_parent_events": int((events["data_source"] == HIST_SOURCE).sum()) if not events.empty else 0,
            "live_retrospective_parent_events": int((events["data_source"] == LIVE_SOURCE).sum()) if not events.empty else 0,
            "research_only": True,
            "canonical_strategy_unchanged": True,
            "prospective_phase4b2_unchanged": True,
            "live_trading_disabled": True,
            "portfolio_os_isolated": True,
            "outputs": list(outputs.keys()) + ["phase4b2h_events.parquet", REPORT_NAME],
        }

    def _read_parquet(self, name: str) -> pd.DataFrame:
        path = self.root / name
        if not path.exists():
            return pd.DataFrame()
        return pd.read_parquet(path)

    def _build_events(self, hist_events: pd.DataFrame, live_master: pd.DataFrame) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        if not hist_events.empty:
            for raw in hist_events.to_dict("records"):
                base = {
                    "parent_event_id": raw.get("parent_event_id"),
                    "namespace": PHASE_NAMESPACE,
                    "data_source": HIST_SOURCE,
                    "source_namespace": "PHASE_4A_HISTORICAL",
                    "strategy_state_source": "D1_EOD_STATIC_OPTIONS",
                    "symbol": raw.get("symbol"),
                    "trade_date": raw.get("trade_date"),
                    "timestamp": raw.get("confirmation_timestamp_utc"),
                    "time_bucket": raw.get("time_bucket"),
                    "direction": raw.get("direction"),
                    "structural_family": raw.get("structural_family"),
                    "level_cluster_id": raw.get("level_cluster_id"),
                    "level_price": raw.get("level_price"),
                    "zone_low": raw.get("zone_low"),
                    "zone_high": raw.get("zone_high"),
                    "level_type": raw.get("level_type"),
                    "level_strength": raw.get("level_strength"),
                    "level_tier": raw.get("level_tier"),
                    "gamma_regime": raw.get("gamma_regime"),
                    "trend_5m": raw.get("trend_5m"),
                    "trend_15m": raw.get("trend_15m"),
                    "trend_30m": raw.get("trend_30m"),
                    "trend_1h": raw.get("trend_1h"),
                    "SPY_15m_trend": raw.get("SPY_15m_trend"),
                    "QQQ_15m_trend": raw.get("QQQ_15m_trend"),
                    "market_alignment": raw.get("market_alignment"),
                    "distance_from_spot_ATR": raw.get("distance_to_level_ATR"),
                    "approach_velocity": raw.get("approach_velocity"),
                    "sweep_depth_ATR": raw.get("sweep_depth_ATR"),
                    "historical_data_tier": raw.get("historical_data_tier"),
                    "diagnostic_data_quality": "FULL" if as_bool(raw.get("lookahead_safe")) else "LIMITED",
                    "lookahead_safe": as_bool(raw.get("lookahead_safe")),
                    "intraday_persistence_state": "FORWARD_ONLY",
                    "dynamic_intraday_options_features": "FORWARD_ONLY_NOT_RECONSTRUCTED",
                    "synthetic_excluded": True,
                }
                rows.append(self._decorate_event(base))

        if not live_master.empty:
            filtered = live_master[live_master.apply(lambda row: not self._is_synthetic(row), axis=1)]
            for raw in filtered.to_dict("records"):
                setup_family = str(raw.get("setup_family") or "LEVEL_RECLAIM").upper()
                family = "RECLAIM"
                if "REJECTION" in setup_family:
                    family = "REJECTION"
                elif "BREAKOUT" in setup_family:
                    family = "BREAKOUT"
                base = {
                    "parent_event_id": raw.get("parent_setup_id") or raw.get("dedupe_key"),
                    "namespace": PHASE_NAMESPACE,
                    "data_source": LIVE_SOURCE,
                    "source_namespace": "LIVE_NATURAL_PAPER_HISTORY",
                    "strategy_state_source": "LIVE_INTRADAY_OPTIONS_RECORDED",
                    "symbol": raw.get("symbol"),
                    "trade_date": raw.get("session_date"),
                    "timestamp": raw.get("timestamp"),
                    "time_bucket": raw.get("time_bucket"),
                    "direction": raw.get("direction"),
                    "structural_family": family,
                    "level_cluster_id": raw.get("dedupe_key"),
                    "level_price": raw.get("gamma_flip"),
                    "zone_low": None,
                    "zone_high": None,
                    "level_type": raw.get("reclaimed_level_type"),
                    "level_strength": raw.get("level_strength"),
                    "level_tier": self._live_tier(raw.get("adjusted_score"), raw.get("level_strength")),
                    "gamma_regime": raw.get("gamma_regime"),
                    "trend_5m": raw.get("short_term_trend"),
                    "trend_15m": raw.get("SPY_trend") if raw.get("symbol") == "SPY" else raw.get("QQQ_trend"),
                    "trend_30m": None,
                    "trend_1h": None,
                    "SPY_15m_trend": raw.get("SPY_trend"),
                    "QQQ_15m_trend": raw.get("QQQ_trend"),
                    "market_alignment": raw.get("market_alignment"),
                    "distance_from_spot_ATR": raw.get("distance_to_gamma_flip_R"),
                    "approach_velocity": None,
                    "sweep_depth_ATR": raw.get("sweep_depth"),
                    "historical_data_tier": None,
                    "data_quality_tier": raw.get("data_quality_tier"),
                    "diagnostic_data_quality": self._live_quality(raw),
                    "lookahead_safe": True,
                    "intraday_persistence_state": "RECORDED_OR_UNKNOWN",
                    "dynamic_intraday_options_features": "LIVE_RECORDED_LIMITED_FIELDS",
                    "synthetic_excluded": True,
                    "raw_score": raw.get("raw_score"),
                    "adjusted_score": raw.get("adjusted_score"),
                    "confidence_score": raw.get("confidence_score"),
                    "candle_provider": raw.get("candle_provider"),
                    "options_provider": raw.get("options_provider"),
                }
                rows.append(self._decorate_event(base))

        return pd.DataFrame(rows).drop_duplicates("parent_event_id").reset_index(drop=True) if rows else pd.DataFrame()

    @staticmethod
    def _is_synthetic(row: Mapping[str, Any]) -> bool:
        text = json_text(row).lower()
        return any(token in text for token in ["synthetic", "demo_fixture", "acceptance_test"])

    @staticmethod
    def _live_tier(score: Any, strength: Any) -> str:
        value = safe_float(strength, None)
        if value is None:
            raw = safe_float(score, 0.0) or 0.0
            value = raw / 100.0 if raw > 1 else raw
        if value >= 0.85:
            return "LEVEL_TIER_S"
        if value >= 0.70:
            return "LEVEL_TIER_A"
        if value >= 0.55:
            return "LEVEL_TIER_B"
        return "LEVEL_TIER_C"

    @staticmethod
    def _live_quality(row: Mapping[str, Any]) -> str:
        text = str(row.get("data_quality_tier") or "").upper()
        if "FREE" in text or "LIMITED" in text:
            return "LIMITED"
        if "HIGH" in text or "FULL" in text:
            return "FULL"
        return "PARTIAL"

    def _decorate_event(self, row: dict[str, Any]) -> dict[str, Any]:
        structure = classify_structure(row)
        direction = classify_direction({**row, **structure})
        row.update(structure)
        row.update(direction)
        row["phase4b2h_feature_scope"] = (
            "HISTORICAL_STATIC_D1_ONLY"
            if row.get("data_source") == HIST_SOURCE
            else "LIVE_RECORDED_RETROSPECTIVE_LIMITED"
        )
        row["forward_only_unavailable_fields"] = ",".join(FORWARD_ONLY_FIELDS) if row.get("data_source") == HIST_SOURCE else ""
        return row

    def _build_branches(self, hist_branches: pd.DataFrame, live_master: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
        frames: list[pd.DataFrame] = []
        event_lookup = events.set_index("parent_event_id").to_dict("index") if not events.empty else {}

        if not hist_branches.empty:
            hist = hist_branches.copy()
            hist["data_source"] = HIST_SOURCE
            hist["namespace"] = PHASE_NAMESPACE
            hist["strategy_state_source"] = "D1_EOD_STATIC_OPTIONS"
            hist["direction_classifier_source"] = "HISTORICAL_STATIC_OPTIONS_PLUS_PRICE"
            hist["dynamic_intraday_options_features"] = "FORWARD_ONLY_NOT_RECONSTRUCTED"
            hist["is_control"] = hist["is_control"].map(as_bool)
            for col in ["result_R", "MFE_R", "MAE_R", "duration_minutes", "time_to_MFE_minutes"]:
                if col in hist.columns:
                    hist[col] = pd.to_numeric(hist[col], errors="coerce")
            frames.append(hist)

        if not live_master.empty:
            live_rows: list[dict[str, Any]] = []
            live = live_master[live_master.apply(lambda row: not self._is_synthetic(row), axis=1)]
            for raw in live.to_dict("records"):
                parent_id = raw.get("parent_setup_id") or raw.get("dedupe_key")
                common = {
                    "parent_event_id": parent_id,
                    "namespace": PHASE_NAMESPACE,
                    "data_source": LIVE_SOURCE,
                    "strategy_state_source": "LIVE_INTRADAY_OPTIONS_RECORDED",
                    "direction_classifier_source": "LIVE_RECORDED_RETROSPECTIVE_LIMITED",
                    "dynamic_intraday_options_features": "LIVE_RECORDED_LIMITED_FIELDS",
                    "symbol": raw.get("symbol"),
                    "trade_date": raw.get("session_date"),
                    "strategy_variant": "LIVE_RECORDED_RETROSPECTIVE",
                    "confirmation_tf": "5m",
                    "execution_tf": "5m",
                    "context_tf": "live_recorded",
                    "entry_variant": "LIVE_CANONICAL_ENTRY",
                    "stop_variant": "STOP_A_CURRENT_STRUCTURAL",
                    "is_control": False,
                    "control_type": "OPTIONS_STRONG_LEVEL",
                    "direction": raw.get("direction"),
                    "structural_family": raw.get("setup_family") or "LEVEL_RECLAIM",
                    "level_type": raw.get("reclaimed_level_type"),
                    "level_tier": event_lookup.get(parent_id, {}).get("level_tier"),
                    "time_bucket": raw.get("time_bucket"),
                    "gamma_regime": raw.get("gamma_regime"),
                    "entry": raw.get("entry_price") or raw.get("planned_entry"),
                    "stop": raw.get("structural_stop"),
                    "initial_risk": raw.get("risk_per_share"),
                    "slippage_bps": None,
                    "sample_split": "LIVE_RETROSPECTIVE",
                    "lookahead_safe": True,
                    "historical_data_tier": None,
                    "diagnostic_data_quality": self._live_quality(raw),
                    "MFE_R": raw.get("MFE_R"),
                    "MAE_R": raw.get("MAE_R"),
                    "time_to_MFE_minutes": None,
                    "time_to_0_5R_minutes": None,
                    "time_to_1R_minutes": None,
                    "time_to_1_5R_minutes": None,
                    "holding_15m_R": raw.get("R_after_15m"),
                    "holding_30m_R": raw.get("R_after_30m"),
                    "holding_60m_R": raw.get("R_after_60m"),
                    "holding_120m_R": raw.get("R_after_120m"),
                    "holding_240m_R": None,
                    "holding_EOD_R": raw.get("R_at_close"),
                    "duration_minutes": None,
                    "entry_timestamp_utc": raw.get("opened_at"),
                    "closed_at_utc": raw.get("closed_at"),
                    "exit_reason": raw.get("exit_reason"),
                }
                candidates = [
                    ("LIVE_CANONICAL_TM_V0", "TM_V0_CURRENT", raw.get("canonical_R"), raw.get("canonical_status")),
                    ("LIVE_FORWARD_BRANCH_A_TM_V0", "TM_V0_CURRENT", raw.get("branch_A_R"), raw.get("branch_A_status")),
                    ("LIVE_FORWARD_BRANCH_B_TM_V3", "TM_V3_TP1_PLUS_RUNNER", raw.get("branch_B_R"), raw.get("branch_B_status")),
                ]
                for strategy, management, result, status in candidates:
                    if result is None and strategy != "LIVE_CANONICAL_TM_V0":
                        continue
                    row = {
                        **common,
                        "branch_id": f"phase4b2h_{parent_id}_{strategy}",
                        "strategy_variant": strategy,
                        "management_variant": management,
                        "result_R": result,
                        "status": status or raw.get("canonical_status"),
                    }
                    live_rows.append(row)
            if live_rows:
                frames.append(pd.DataFrame(live_rows))

        if not frames:
            return pd.DataFrame()
        branches = pd.concat(frames, ignore_index=True, sort=False)
        for col in ["result_R", "MFE_R", "MAE_R", "duration_minutes", "entry", "stop", "initial_risk"]:
            if col in branches.columns:
                branches[col] = pd.to_numeric(branches[col], errors="coerce")
        if not events.empty:
            keep = [
                "parent_event_id",
                "direction_class",
                "predicted_direction",
                "direction_confidence_0_100",
                "naive_level_direction",
                "price_action_direction",
                "structure_alignment",
                "trend_5m",
                "trend_15m",
                "trend_30m",
                "trend_1h",
            ]
            branches = branches.merge(events[[col for col in keep if col in events.columns]], on="parent_event_id", how="left")
        branches["resolved"] = pd.to_numeric(branches["result_R"], errors="coerce").notna()
        branches["is_primary_baseline"] = self._primary_baseline_mask(branches)
        branches["stop_experiment_variant"] = branches["stop_variant"].map(STOP_EXPERIMENT_MAP).fillna(branches["stop_variant"])
        entry_variant = branches["entry_variant"].fillna("").astype(str).str.upper()
        branches["entry_quality_class"] = "UNKNOWN"
        branches.loc[entry_variant.str.contains("ENTRY_1|LIVE_CANONICAL", regex=True), "entry_quality_class"] = "ON_TIME_ENTRY"
        branches.loc[entry_variant.str.contains("ENTRY_2|ENTRY_3", regex=True), "entry_quality_class"] = "LATER_CONFIRMATION_ENTRY"
        branches.loc[entry_variant.str.contains("ENTRY_4|ENTRY_5", regex=True), "entry_quality_class"] = "FILTERED_CONFIRMATION_ENTRY"
        result = pd.to_numeric(branches.get("result_R"), errors="coerce")
        mfe = pd.to_numeric(branches.get("MFE_R"), errors="coerce")
        mae = pd.to_numeric(branches.get("MAE_R"), errors="coerce")
        branches["giveback_R"] = mfe - result
        branches["giveback_bucket"] = "NOT_LOSER_OR_UNRESOLVED"
        loss_mask = result < 0
        branches.loc[loss_mask & (mfe.fillna(0) < 0.01), "giveback_bucket"] = "NEVER_POSITIVE"
        branches.loc[loss_mask & (mfe >= 0.5), "giveback_bucket"] = "REACHED_0_5R_THEN_LOSS"
        branches.loc[loss_mask & (mfe >= 0.7), "giveback_bucket"] = "REACHED_0_7R_THEN_LOSS"
        branches.loc[loss_mask & (mfe >= 1.0), "giveback_bucket"] = "REACHED_1R_THEN_LOSS"
        branches.loc[loss_mask & (mfe >= 1.5), "giveback_bucket"] = "REACHED_1_5R_THEN_LOSS"
        branches["path_shape"] = "NO_EDGE_OR_SMALL_MFE_LOSS"
        branches.loc[result.isna(), "path_shape"] = "UNRESOLVED"
        branches.loc[(result > 0) & (mae.fillna(999) < 0.25), "path_shape"] = "CLEAN_TREND_WINNER"
        branches.loc[(result > 0) & (mae.fillna(0) >= 0.5), "path_shape"] = "EARLY_ADVERSE_THEN_WINNER"
        branches.loc[(result < 0) & (mfe.fillna(0) < 0.25), "path_shape"] = "IMMEDIATE_LOSER"
        branches.loc[(result < 0) & (mfe >= 0.5), "path_shape"] = "EARLY_MFE_THEN_REVERSAL"
        branches.loc[(result < 0) & (mfe >= 1.0), "path_shape"] = "LARGE_WINNER_GIVEN_BACK"
        branches.loc[result == 0, "path_shape"] = "BREAKEVEN_OR_CHOP"
        return branches

    @staticmethod
    def _primary_baseline_mask(branches: pd.DataFrame) -> pd.Series:
        if branches.empty:
            return pd.Series(dtype=bool)
        hist_mask = (
            (branches["data_source"] == HIST_SOURCE)
            & (branches["is_control"] == False)  # noqa: E712
            & (branches["strategy_variant"] == "VARIANT_A_HIST_5M_CONFIRM_5M_ENTRY")
            & (branches["entry_variant"] == "ENTRY_1_CLOSE_RECLAIM")
            & (branches["stop_variant"] == "STOP_A_CURRENT_STRUCTURAL")
            & (branches["management_variant"] == "TM_V0_CURRENT")
        )
        live_mask = (
            (branches["data_source"] == LIVE_SOURCE)
            & (branches["strategy_variant"] == "LIVE_CANONICAL_TM_V0")
            & (branches["management_variant"] == "TM_V0_CURRENT")
        )
        return hist_mask | live_mask

    def _baseline_branches(self, branches: pd.DataFrame) -> pd.DataFrame:
        if branches.empty:
            return pd.DataFrame()
        return branches[branches["is_primary_baseline"]].copy()

    @staticmethod
    def _path_shape(row: Mapping[str, Any]) -> str:
        result = safe_float(row.get("result_R"), None)
        mfe = safe_float(row.get("MFE_R"), 0.0) or 0.0
        mae = safe_float(row.get("MAE_R"), 0.0) or 0.0
        if result is None:
            return "UNRESOLVED"
        if result > 0 and mae < 0.25:
            return "CLEAN_TREND_WINNER"
        if result > 0 and mae >= 0.5:
            return "EARLY_ADVERSE_THEN_WINNER"
        if result < 0 and mfe < 0.25:
            return "IMMEDIATE_LOSER"
        if result < 0 and mfe >= 1.0:
            return "LARGE_WINNER_GIVEN_BACK"
        if result < 0 and mfe >= 0.5:
            return "EARLY_MFE_THEN_REVERSAL"
        if result == 0:
            return "BREAKEVEN_OR_CHOP"
        return "NO_EDGE_OR_SMALL_MFE_LOSS"

    def _stop_comparison(self, branches: pd.DataFrame) -> pd.DataFrame:
        if branches.empty:
            return pd.DataFrame()
        df = branches[
            (branches["is_control"] == False)  # noqa: E712
            & (
                ((branches["data_source"] == HIST_SOURCE) & (branches["strategy_variant"] == "VARIANT_A_HIST_5M_CONFIRM_5M_ENTRY"))
                | (branches["data_source"] == LIVE_SOURCE)
            )
            & (branches["entry_variant"].isin(["ENTRY_1_CLOSE_RECLAIM", "LIVE_CANONICAL_ENTRY"]))
            & (branches["management_variant"] == "TM_V0_CURRENT")
            & (branches["stop_variant"].isin(STOP_EXPERIMENT_MAP.keys()))
            & (branches["resolved"])
        ].copy()
        if df.empty:
            return pd.DataFrame()
        df["stopped"] = df["exit_reason"].astype(str).str.contains("stop", case=False, na=False)
        grouped = grouped_summary(df, ["data_source", "stop_experiment_variant", "direction"])
        stopped_rates = df.groupby(["data_source", "stop_experiment_variant", "direction"], dropna=False)["stopped"].mean().reset_index(name="stop_frequency")
        out = grouped.merge(stopped_rates, on=["data_source", "stop_experiment_variant", "direction"], how="left")
        out["stop_frequency"] = out["stop_frequency"].round(4)
        out["experiment_note"] = out["stop_experiment_variant"].map(
            {
                "S0_CANONICAL_STOP": "canonical stop",
                "S1_FULL_OPTIONS_ZONE_INVALIDATION": "historical options-zone proxy from static D-1 zone",
                "S2_15M_STRUCTURAL_INVALIDATION_PROXY": "historical 15m-structure proxy; true live structure remains prospective",
                "S3_LAST_CONFIRMED_HL_LH_INVALIDATION_PROXY": "historical HL/LH proxy via wider structural buffer",
            }
        ).fillna("existing research stop variant")
        return out

    def _winner_mae(self, baseline: pd.DataFrame) -> pd.DataFrame:
        if baseline.empty:
            return pd.DataFrame()
        winners = baseline[pd.to_numeric(baseline["result_R"], errors="coerce") > 0].copy()
        if winners.empty:
            return pd.DataFrame()
        rows: list[dict[str, Any]] = []
        groups = ["data_source", "direction", "confirmation_tf", "structural_family", "level_type", "level_tier", "time_bucket"]
        for keys, group in winners.groupby(groups, dropna=False):
            if not isinstance(keys, tuple):
                keys = (keys,)
            mae = numeric(group["MAE_R"]).dropna()
            row = {col: "UNKNOWN" if pd.isna(value) else value for col, value in zip(groups, keys)}
            row.update(
                {
                    "N_winners": int(len(mae)),
                    "unique_days": int(group["trade_date"].nunique()),
                    "MAE_P10": pctl(mae, 0.10),
                    "MAE_P25": pctl(mae, 0.25),
                    "MAE_median": pctl(mae, 0.50),
                    "MAE_P75": pctl(mae, 0.75),
                    "MAE_P90": pctl(mae, 0.90),
                    "MAE_P95": pctl(mae, 0.95),
                    "stop_to_preserve_80pct_winners_R": pctl(mae, 0.80),
                    "stop_to_preserve_90pct_winners_R": pctl(mae, 0.90),
                    "stop_to_preserve_95pct_winners_R": pctl(mae, 0.95),
                }
            )
            rows.append(row)
        return pd.DataFrame(rows).sort_values(["N_winners"], ascending=False, ignore_index=True)

    def _stop_recovery(self, historical_baseline: pd.DataFrame, candles: pd.DataFrame) -> pd.DataFrame:
        if historical_baseline.empty:
            return pd.DataFrame()
        stopped = historical_baseline[
            historical_baseline["exit_reason"].astype(str).str.contains("stop", case=False, na=False)
            & historical_baseline["entry"].notna()
            & historical_baseline["initial_risk"].notna()
        ].copy()
        if stopped.empty:
            return pd.DataFrame()
        df = stopped[
            [
                "data_source",
                "parent_event_id",
                "symbol",
                "trade_date",
                "direction",
                "level_type",
                "structural_family",
                "time_bucket",
                "entry_timestamp_utc",
                "closed_at_utc",
                "entry",
                "initial_risk",
                "MFE_R",
                "MAE_R",
                "result_R",
            ]
        ].copy()
        df = df.rename(columns={"closed_at_utc": "stop_time_utc", "MFE_R": "pre_stop_or_lifecycle_MFE_R"})
        mfe = pd.to_numeric(df["pre_stop_or_lifecycle_MFE_R"], errors="coerce")
        for horizon in [15, 30, 60, 120]:
            for threshold in [0.25, 0.5, 0.7, 1.0, 1.5]:
                df[f"reached_{str(threshold).replace('.', '_')}R_within_{horizon}m"] = mfe >= threshold
            df[f"max_recovery_{horizon}m_R"] = mfe
        df["post_stop_tracking_quality"] = "LIFECYCLE_MFE_PROXY_NOT_EXACT_POST_STOP_ORDER"
        df["stop_recovery_class"] = "TRUE_INVALIDATION_OR_NO_RECOVERY"
        df.loc[mfe >= 0.5, "stop_recovery_class"] = "VOLATILITY_NOISE_OR_EARLY_ENTRY"
        df.loc[mfe >= 1.0, "stop_recovery_class"] = "STOP_TOO_TIGHT_CANDIDATE"
        return df.reset_index(drop=True)

    @staticmethod
    def _max_favorable_r(bars: pd.DataFrame, entry: float, risk: float, direction: str) -> float | None:
        if bars.empty or risk <= 0:
            return None
        if direction == "LONG":
            return round(float(((pd.to_numeric(bars["high"], errors="coerce") - entry) / risk).max()), 4)
        if direction == "SHORT":
            return round(float(((entry - pd.to_numeric(bars["low"], errors="coerce")) / risk).max()), 4)
        return None

    def _giveback(self, baseline: pd.DataFrame) -> pd.DataFrame:
        if baseline.empty:
            return pd.DataFrame()
        df = baseline[baseline["resolved"]].copy()
        df["max_MFE_R"] = pd.to_numeric(df["MFE_R"], errors="coerce")
        df["final_realized_R"] = pd.to_numeric(df["result_R"], errors="coerce")
        df["giveback_R"] = (df["max_MFE_R"] - df["final_realized_R"]).round(4)
        df["loser_reached_0_5R"] = (df["final_realized_R"] < 0) & (df["max_MFE_R"] >= 0.5)
        df["loser_reached_0_7R"] = (df["final_realized_R"] < 0) & (df["max_MFE_R"] >= 0.7)
        df["loser_reached_1R"] = (df["final_realized_R"] < 0) & (df["max_MFE_R"] >= 1.0)
        df["loser_reached_1_5R"] = (df["final_realized_R"] < 0) & (df["max_MFE_R"] >= 1.5)
        df["giveback_class"] = df.apply(giveback_bucket, axis=1)
        keep = [
            "data_source",
            "parent_event_id",
            "symbol",
            "trade_date",
            "direction",
            "structural_family",
            "level_type",
            "level_tier",
            "time_bucket",
            "max_MFE_R",
            "final_realized_R",
            "giveback_R",
            "giveback_class",
            "loser_reached_0_5R",
            "loser_reached_0_7R",
            "loser_reached_1R",
            "loser_reached_1_5R",
        ]
        return df[[col for col in keep if col in df.columns]].reset_index(drop=True)

    def _simulate_management(self, historical_baseline: pd.DataFrame, candles: pd.DataFrame) -> pd.DataFrame:
        if historical_baseline.empty:
            return pd.DataFrame()
        base = historical_baseline[
            historical_baseline["entry"].notna()
            & historical_baseline["stop"].notna()
            & historical_baseline["initial_risk"].notna()
        ].copy()
        if base.empty:
            return pd.DataFrame()
        variants = [
            "M0_CURRENT",
            "M1_HALF_0_5R_RUNNER",
            "M2_HALF_0_7R_RUNNER",
            "M3_PROTECT_AFTER_1R",
            "M4_STRUCTURE_TRAIL_PROXY_NO_IMMEDIATE_BE",
            "FIXED_0_5R",
            "FIXED_0_7R",
            "FIXED_1R",
            "FIXED_1_5R",
            "FIXED_2R",
            "NO_BE",
            "BE_AFTER_0_5R",
            "BE_AFTER_0_7R",
            "BE_AFTER_1R",
            "BE_AFTER_TP1",
            "BE_AFTER_STRUCTURE_CONFIRMATION_PROXY",
        ]
        rows: list[dict[str, Any]] = []
        for raw in base.to_dict("records"):
            for variant in variants:
                result = self._simulate_variant_from_extrema(raw, variant)
                rows.append(
                    {
                        "data_source": HIST_SOURCE,
                        "parent_event_id": raw.get("parent_event_id"),
                        "symbol": raw.get("symbol"),
                        "trade_date": raw.get("trade_date"),
                        "direction": raw.get("direction"),
                        "structural_family": raw.get("structural_family"),
                        "level_type": raw.get("level_type"),
                        "level_tier": raw.get("level_tier"),
                        "time_bucket": raw.get("time_bucket"),
                        "management_replay_variant": result.variant,
                        "result_R": result.result_R,
                        "exit_reason": result.exit_reason,
                        "MFE_R": result.mfe_R,
                        "MAE_R": result.mae_R,
                        "duration_minutes": result.duration_minutes,
                        "BE_exit": result.be_exit,
                        "giveback_R": result.giveback_R,
                        "capture_efficiency": result.capture_efficiency,
                        "replay_note": "research-only extrema/horizon diagnostic; exact post-threshold order is limited unless already encoded in source branch",
                    }
                )
        return pd.DataFrame(rows)

    def _simulate_variant_from_extrema(self, row: Mapping[str, Any], variant: str) -> ReplayResult:
        """Fast diagnostic management replay from stored MFE/MAE/EOD fields.

        This intentionally does not pretend to recover all intrabar ordering. It is enough
        for Phase 4B.2-H screening and is labeled as a diagnostic approximation in outputs.
        """
        mfe = safe_float(row.get("MFE_R"), 0.0) or 0.0
        mae = safe_float(row.get("MAE_R"), 0.0) or 0.0
        eod = safe_float(row.get("holding_EOD_R"), safe_float(row.get("result_R"), 0.0)) or 0.0
        duration = safe_float(row.get("duration_minutes"), None)

        def finish(result: float, reason: str, be: bool = False) -> ReplayResult:
            rounded = round(float(result), 4)
            giveback = round(mfe - rounded, 4)
            capture = round(rounded / mfe, 4) if mfe > 0 and rounded > 0 else None
            return ReplayResult(variant, rounded, reason, round(mfe, 4), round(mae, 4), duration, be, giveback, capture)

        def fixed(target: float) -> ReplayResult:
            if mfe >= target:
                return finish(target, f"fixed_{target:g}R")
            if mae >= 1.0:
                return finish(-1.0, "stop_loss")
            return finish(eod, "EOD")

        def protect_after(threshold: float, target: float = 2.0) -> ReplayResult:
            if mfe >= target:
                return finish(target, f"target_{target:g}R")
            if mfe >= threshold:
                if eod < 0:
                    return finish(0.0, "breakeven_stop", True)
                return finish(eod, "EOD_protected")
            if mae >= 1.0:
                return finish(-1.0, "stop_loss")
            return finish(eod, "EOD")

        def partial_runner(threshold: float, fraction: float, target: float = 2.0, move_to_be: bool = True) -> ReplayResult:
            if mfe < threshold:
                if mae >= 1.0:
                    return finish(-1.0, "stop_loss")
                return finish(eod, "EOD")
            locked = fraction * threshold
            remaining = 1.0 - fraction
            if mfe >= target:
                return finish(locked + remaining * target, "runner_target")
            if move_to_be and eod < 0:
                return finish(locked, "partial_then_BE", True)
            return finish(locked + remaining * eod, "partial_then_EOD")

        if variant == "M0_CURRENT":
            return partial_runner(1.0, 0.33, 2.0, True)
        if variant == "M1_HALF_0_5R_RUNNER":
            return partial_runner(0.5, 0.50, 2.0, True)
        if variant == "M2_HALF_0_7R_RUNNER":
            return partial_runner(0.7, 0.50, 2.0, True)
        if variant == "M3_PROTECT_AFTER_1R":
            return protect_after(1.0, 2.0)
        if variant == "M4_STRUCTURE_TRAIL_PROXY_NO_IMMEDIATE_BE":
            return partial_runner(1.0, 0.33, 2.0, False)
        if variant == "NO_BE":
            return fixed(2.0)
        if variant == "BE_AFTER_0_5R":
            return protect_after(0.5, 2.0)
        if variant == "BE_AFTER_0_7R":
            return protect_after(0.7, 2.0)
        if variant in {"BE_AFTER_1R", "BE_AFTER_TP1", "BE_AFTER_STRUCTURE_CONFIRMATION_PROXY"}:
            return protect_after(1.0, 2.0)
        if variant.startswith("FIXED_"):
            target = float(variant.replace("FIXED_", "").replace("R", "").replace("_", "."))
            return fixed(target)
        return finish(safe_float(row.get("result_R"), 0.0) or 0.0, "source_result")

    def _simulate_variant(self, row: Mapping[str, Any], bars: pd.DataFrame, variant: str) -> ReplayResult:
        entry = safe_float(row.get("entry"), None)
        risk = safe_float(row.get("initial_risk"), None)
        direction = str(row.get("direction") or "").upper()
        if entry is None or risk is None or risk <= 0 or direction not in {"LONG", "SHORT"}:
            return ReplayResult(variant, None, "invalid_entry_or_risk", None, None, None)

        mfe = -999.0
        mae = 999.0
        realized = 0.0
        open_fraction = 1.0
        stop_r = -1.0
        duration = None
        exit_reason = "EOD"
        be_exit = False

        def bar_r_values(bar: Mapping[str, Any]) -> tuple[float, float, float]:
            if direction == "LONG":
                high_r = (safe_float(bar.get("high"), entry) - entry) / risk
                low_r = (safe_float(bar.get("low"), entry) - entry) / risk
                close_r = (safe_float(bar.get("close"), entry) - entry) / risk
            else:
                high_r = (entry - safe_float(bar.get("low"), entry)) / risk
                low_r = (entry - safe_float(bar.get("high"), entry)) / risk
                close_r = (entry - safe_float(bar.get("close"), entry)) / risk
            return float(high_r), float(low_r), float(close_r)

        fixed_target: float | None = None
        partial_threshold: float | None = None
        partial_fraction = 0.0
        runner_target = 2.0
        protect_threshold: float | None = None
        no_be = False
        trail_proxy = False
        if variant.startswith("FIXED_"):
            fixed_target = float(variant.replace("FIXED_", "").replace("R", "").replace("_", "."))
        elif variant == "M1_HALF_0_5R_RUNNER":
            partial_threshold, partial_fraction = 0.5, 0.5
        elif variant == "M2_HALF_0_7R_RUNNER":
            partial_threshold, partial_fraction = 0.7, 0.5
        elif variant == "M3_PROTECT_AFTER_1R":
            protect_threshold = 1.0
            runner_target = 2.0
        elif variant == "M4_STRUCTURE_TRAIL_PROXY_NO_IMMEDIATE_BE":
            partial_threshold, partial_fraction, trail_proxy, no_be = 1.0, 0.33, True, True
        elif variant == "NO_BE":
            fixed_target, no_be = 2.0, True
        elif variant == "BE_AFTER_0_5R":
            protect_threshold = 0.5
        elif variant == "BE_AFTER_0_7R":
            protect_threshold = 0.7
        elif variant == "BE_AFTER_1R" or variant == "BE_AFTER_TP1":
            protect_threshold = 1.0
        elif variant == "BE_AFTER_STRUCTURE_CONFIRMATION_PROXY":
            protect_threshold = 1.0
            trail_proxy = True
        elif variant == "M0_CURRENT":
            partial_threshold, partial_fraction = 1.0, 0.33

        first_ts = pd.to_datetime(bars.iloc[0].get("timestamp_utc"), errors="coerce", utc=True)
        hit_partial = False
        trail_window_lows: list[float] = []
        trail_window_highs: list[float] = []
        for _, bar in bars.iterrows():
            ts = pd.to_datetime(bar.get("timestamp_utc"), errors="coerce", utc=True)
            high_r, low_r, close_r = bar_r_values(bar)
            mfe = max(mfe, high_r)
            mae = min(mae, low_r)
            if direction == "LONG":
                trail_window_lows.append(float(bar.get("low")))
            else:
                trail_window_highs.append(float(bar.get("high")))

            if low_r <= stop_r:
                realized += open_fraction * stop_r
                exit_reason = "breakeven_stop" if stop_r == 0 else "stop_loss"
                be_exit = stop_r == 0
                duration = self._minutes_between(first_ts, ts)
                open_fraction = 0.0
                break

            if fixed_target is not None and high_r >= fixed_target:
                realized += open_fraction * fixed_target
                exit_reason = f"fixed_{fixed_target:g}R"
                duration = self._minutes_between(first_ts, ts)
                open_fraction = 0.0
                break

            if partial_threshold is not None and (not hit_partial) and high_r >= partial_threshold:
                realized += partial_fraction * partial_threshold
                open_fraction -= partial_fraction
                hit_partial = True
                if not no_be:
                    stop_r = max(stop_r, 0.0)

            if protect_threshold is not None and high_r >= protect_threshold:
                stop_r = max(stop_r, 0.0)

            if trail_proxy and hit_partial and len(trail_window_lows) >= 3 and direction == "LONG":
                trailing_stop_price = min(trail_window_lows[-3:])
                stop_r = max(stop_r, (trailing_stop_price - entry) / risk)
            elif trail_proxy and hit_partial and len(trail_window_highs) >= 3 and direction == "SHORT":
                trailing_stop_price = max(trail_window_highs[-3:])
                stop_r = max(stop_r, (entry - trailing_stop_price) / risk)

            if open_fraction > 0 and high_r >= runner_target and partial_threshold is not None:
                realized += open_fraction * runner_target
                exit_reason = "runner_target"
                duration = self._minutes_between(first_ts, ts)
                open_fraction = 0.0
                break

        if open_fraction > 0:
            last = bars.iloc[-1]
            _high_r, _low_r, close_r = bar_r_values(last)
            realized += open_fraction * close_r
            duration = self._minutes_between(first_ts, pd.to_datetime(last.get("timestamp_utc"), errors="coerce", utc=True))
        result = round(float(realized), 4)
        mfe_value = round(float(max(mfe, 0.0)), 4) if mfe > -998 else None
        mae_value = round(float(abs(min(mae, 0.0))), 4) if mae < 998 else None
        giveback = round((mfe_value or 0.0) - result, 4) if result is not None and mfe_value is not None else None
        capture = None
        if mfe_value and mfe_value > 0 and result > 0:
            capture = round(result / mfe_value, 4)
        return ReplayResult(variant, result, exit_reason, mfe_value, mae_value, duration, be_exit, giveback, capture)

    @staticmethod
    def _minutes_between(start: Any, end: Any) -> float | None:
        try:
            if pd.isna(start) or pd.isna(end):
                return None
            return round((end - start).total_seconds() / 60.0, 2)
        except Exception:
            return None

    def _breakeven(self, management_sim: pd.DataFrame) -> pd.DataFrame:
        if management_sim.empty:
            return pd.DataFrame()
        be_variants = [
            "NO_BE",
            "BE_AFTER_0_5R",
            "BE_AFTER_0_7R",
            "BE_AFTER_1R",
            "BE_AFTER_TP1",
            "BE_AFTER_STRUCTURE_CONFIRMATION_PROXY",
            "M0_CURRENT",
            "M1_HALF_0_5R_RUNNER",
            "M2_HALF_0_7R_RUNNER",
            "M3_PROTECT_AFTER_1R",
            "M4_STRUCTURE_TRAIL_PROXY_NO_IMMEDIATE_BE",
        ]
        df = management_sim[management_sim["management_replay_variant"].isin(be_variants)].copy()
        if df.empty:
            return pd.DataFrame()
        grouped = grouped_summary(df, ["management_replay_variant", "direction"])
        be = df.groupby(["management_replay_variant", "direction"], dropna=False)["BE_exit"].mean().reset_index(name="BE_exit_rate")
        out = grouped.merge(be, on=["management_replay_variant", "direction"], how="left")
        out["BE_exit_rate"] = out["BE_exit_rate"].round(4)
        out["research_status"] = out.apply(lambda r: research_status(int(r["N"]), int(r["unique_days"]), safe_float(r["expectancy"], None), safe_float(r["PF"], None)), axis=1)
        return out

    def _target_distribution(self, baseline: pd.DataFrame, management_sim: pd.DataFrame) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        if not baseline.empty:
            thresholds = [0.25, 0.5, 0.7, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0]
            group_cols = ["data_source", "direction", "confirmation_tf", "structural_family", "level_type", "level_tier", "time_bucket"]
            for keys, group in baseline[baseline["resolved"]].groupby(group_cols, dropna=False):
                if not isinstance(keys, tuple):
                    keys = (keys,)
                row = {col: "UNKNOWN" if pd.isna(value) else value for col, value in zip(group_cols, keys)}
                mfe = numeric(group["MFE_R"])
                row["N"] = int(mfe.notna().sum())
                row["unique_days"] = int(group["trade_date"].nunique())
                row["median_MFE"] = pctl(mfe, 0.50)
                row["P75_MFE"] = pctl(mfe, 0.75)
                row["P90_MFE"] = pctl(mfe, 0.90)
                for threshold in thresholds:
                    key = f"reach_{str(threshold).replace('.', '_')}R_rate"
                    row[key] = reached(mfe, threshold)
                rows.append(row)
        out = pd.DataFrame(rows)
        if not management_sim.empty:
            fixed = management_sim[management_sim["management_replay_variant"].str.startswith("FIXED_", na=False)]
            fixed_summary = grouped_summary(fixed, ["management_replay_variant", "direction"])
            fixed_summary["section"] = "FIXED_TARGET_REPLAY"
            out["section"] = "RAW_MFE_TARGET_DISTRIBUTION" if not out.empty else None
            return pd.concat([out, fixed_summary], ignore_index=True, sort=False)
        return out

    def _holding_horizon(self, baseline: pd.DataFrame) -> pd.DataFrame:
        if baseline.empty:
            return pd.DataFrame()
        rows: list[dict[str, Any]] = []
        group_cols = ["data_source", "direction", "structural_family", "level_type", "time_bucket"]
        horizons = [
            ("15m", "holding_15m_R"),
            ("30m", "holding_30m_R"),
            ("60m", "holding_60m_R"),
            ("90m", None),
            ("120m", "holding_120m_R"),
            ("180m", None),
            ("240m", "holding_240m_R"),
            ("EOD", "holding_EOD_R"),
        ]
        for keys, group in baseline[baseline["resolved"]].groupby(group_cols, dropna=False):
            if not isinstance(keys, tuple):
                keys = (keys,)
            common = {col: "UNKNOWN" if pd.isna(value) else value for col, value in zip(group_cols, keys)}
            for label, col in horizons:
                row = {**common, "horizon": label, "N": int(len(group)), "unique_days": int(group["trade_date"].nunique())}
                if col and col in group.columns:
                    stats = stat_summary(group[col])
                    row.update({"expectancy": stats["expectancy"], "PF": stats["PF"], "median_R": stats["median_R"], "win_rate": stats["win_rate"]})
                else:
                    row.update({"expectancy": None, "PF": None, "median_R": None, "win_rate": None, "availability": "NOT_STORED_FOR_THIS_SOURCE"})
                row["median_time_to_MFE"] = pctl(group["time_to_MFE_minutes"], 0.50) if "time_to_MFE_minutes" in group.columns else None
                row["P75_time_to_MFE"] = pctl(group["time_to_MFE_minutes"], 0.75) if "time_to_MFE_minutes" in group.columns else None
                row["P90_time_to_MFE"] = pctl(group["time_to_MFE_minutes"], 0.90) if "time_to_MFE_minutes" in group.columns else None
                rows.append(row)
        return pd.DataFrame(rows)

    def _structure_5m_vs_15m(self, branches: pd.DataFrame) -> pd.DataFrame:
        if branches.empty:
            return pd.DataFrame()
        df = branches[
            (branches["is_control"] == False)  # noqa: E712
            & (branches["entry_variant"] == "ENTRY_1_CLOSE_RECLAIM")
            & (branches["stop_variant"] == "STOP_A_CURRENT_STRUCTURAL")
            & (branches["management_variant"] == "TM_V0_CURRENT")
            & (branches["strategy_variant"].isin(["VARIANT_A_HIST_5M_CONFIRM_5M_ENTRY", "VARIANT_B_HIST_15M_CONFIRM_5M_ENTRY", "VARIANT_E_HIST_30M_CONTEXT_15M_SETUP_5M_ENTRY"]))
            & (branches["resolved"])
        ].copy()
        if df.empty:
            return pd.DataFrame()
        out = grouped_summary(df, ["data_source", "strategy_variant", "confirmation_tf", "direction"])
        out["question"] = "Does 15m structure improve directional outcomes relative to 5m?"
        return out

    def _direction_classifier(self, events: pd.DataFrame, baseline: pd.DataFrame) -> pd.DataFrame:
        if events.empty or baseline.empty:
            return pd.DataFrame()
        df = baseline.merge(
            events[
                [
                    "parent_event_id",
                    "predicted_direction",
                    "naive_level_direction",
                    "price_action_direction",
                    "direction_confidence_0_100",
                    "direction_class",
                    "structure_alignment",
                ]
            ],
            on="parent_event_id",
            how="left",
            suffixes=("", "_event"),
        )
        rows: list[dict[str, Any]] = []
        models = [
            ("MODEL_DIRECTION_CLASSIFIER", "predicted_direction"),
            ("NAIVE_LEVEL_DIRECTION", "naive_level_direction"),
            ("PRICE_STRUCTURE_ONLY", "price_action_direction"),
            ("RANDOM_DIRECTION", None),
        ]
        for model, col in models:
            work = df.copy()
            if col is None:
                work["model_direction"] = work["parent_event_id"].astype(str).map(lambda text: "LONG" if hash(text) % 2 else "SHORT")
            else:
                work["model_direction"] = work[col].fillna("UNKNOWN").astype(str).str.upper()
            work["model_aligned"] = work["model_direction"] == work["direction"].astype(str).str.upper()
            for (source, direction), group in work.groupby(["data_source", "direction"], dropna=False):
                aligned = group[group["model_aligned"] & group["resolved"]]
                all_resolved = group[group["resolved"]]
                row = summary_row(aligned, None)
                row.update(
                    {
                        "data_source": source,
                        "direction": direction,
                        "direction_model": model,
                        "model_coverage": round(float((group["model_direction"] != "UNKNOWN").mean()), 4),
                        "model_alignment_rate": round(float(group["model_aligned"].mean()), 4),
                        "all_events_N": int(len(all_resolved)),
                        "all_events_expectancy": stat_summary(all_resolved["result_R"])["expectancy"],
                    }
                )
                rows.append(row)
        out = pd.DataFrame(rows)
        if not out.empty:
            out["research_status"] = out.apply(lambda r: research_status(int(r["N"]), int(r["unique_days"]), safe_float(r["expectancy"], None), safe_float(r["PF"], None)), axis=1)
        return out

    def _entry_comparison(self, branches: pd.DataFrame) -> pd.DataFrame:
        if branches.empty:
            return pd.DataFrame()
        df = branches[
            (branches["is_control"] == False)  # noqa: E712
            & (branches["strategy_variant"] == "VARIANT_A_HIST_5M_CONFIRM_5M_ENTRY")
            & (branches["stop_variant"] == "STOP_A_CURRENT_STRUCTURAL")
            & (branches["management_variant"] == "TM_V0_CURRENT")
            & (branches["resolved"])
        ].copy()
        if df.empty:
            return pd.DataFrame()
        out = grouped_summary(df, ["data_source", "entry_variant", "direction"])
        out["comparison_note"] = "Higher confirmation can filter noise but may miss moves; historical missed-move detail is limited to branch qualification/status."
        return out

    def _options_ablation(self, branches: pd.DataFrame) -> pd.DataFrame:
        if branches.empty:
            return pd.DataFrame()
        base_filter = (
            (branches["entry_variant"].isin(["ENTRY_1_CLOSE_RECLAIM", "LIVE_CANONICAL_ENTRY"]))
            & (branches["stop_variant"] == "STOP_A_CURRENT_STRUCTURAL")
            & (branches["management_variant"] == "TM_V0_CURRENT")
            & (branches["resolved"])
        )
        df = branches[base_filter].copy()
        if df.empty:
            return pd.DataFrame()
        rows: list[dict[str, Any]] = []
        hist_a = (df["data_source"] == HIST_SOURCE) & (df["strategy_variant"] == "VARIANT_A_HIST_5M_CONFIRM_5M_ENTRY")
        hist_b = (df["data_source"] == HIST_SOURCE) & (df["strategy_variant"] == "VARIANT_B_HIST_15M_CONFIRM_5M_ENTRY")
        ablations = {
            "P0_PRICE_STRUCTURE_ONLY_CONTROLS": df[(df["is_control"] == True) & hist_a],  # noqa: E712
            "P1_PRICE_STRUCTURE_PLUS_STATIC_STRONG_OPTIONS_LEVEL": df[(df["is_control"] == False) & hist_a],  # noqa: E712
            "P2_PERSISTENT_STRENGTHENING_OPTIONS_LEVEL": df.iloc[0:0].copy(),
            "P3_OPTIONS_PLUS_HISTORICAL_DIRECTION_CLASSIFIER": df[(df["is_control"] == False) & hist_a & (df["predicted_direction"].astype(str).str.upper() == df["direction"].astype(str).str.upper())],  # noqa: E712
            "P4_OPTIONS_DIRECTION_CLASSIFIER_PLUS_15M_CONFIRMATION": df[
                (df["is_control"] == False)  # noqa: E712
                & hist_b
                & (df["predicted_direction"].astype(str).str.upper() == df["direction"].astype(str).str.upper())
            ],
        }
        for name, subset in ablations.items():
            if name.startswith("P2"):
                rows.append(
                    {
                        "ablation": name,
                        "N": 0,
                        "unique_days": 0,
                        "expectancy": None,
                        "PF": None,
                        "win_rate": None,
                        "MFE": None,
                        "MAE": None,
                        "availability": "HISTORICALLY_UNAVAILABLE_FORWARD_ONLY",
                    }
                )
                continue
            for direction, group in subset.groupby("direction", dropna=False):
                row = summary_row(group, None)
                row.update({"ablation": name, "direction": direction, "availability": "AVAILABLE"})
                rows.append(row)
        out = pd.DataFrame(rows)
        if not out.empty and "N" in out:
            out["research_status"] = out.apply(lambda r: research_status(int(r["N"]), int(r["unique_days"]), safe_float(r["expectancy"], None), safe_float(r["PF"], None)), axis=1)
        return out

    def _loss_attribution(self, baseline: pd.DataFrame, stop_recovery: pd.DataFrame) -> pd.DataFrame:
        if baseline.empty:
            return pd.DataFrame()
        df = baseline[baseline["resolved"]].copy()
        reasons = df.apply(loss_reason, axis=1)
        df["primary_loss_reason"] = [item[0] for item in reasons]
        df["causality_language"] = [item[1] for item in reasons]
        if not stop_recovery.empty:
            tight_ids = set(stop_recovery[stop_recovery["stop_recovery_class"].isin(["STOP_TOO_TIGHT_CANDIDATE", "VOLATILITY_NOISE_OR_EARLY_ENTRY"])]["parent_event_id"].astype(str))
            mask = (df["parent_event_id"].astype(str).isin(tight_ids)) & (pd.to_numeric(df["result_R"], errors="coerce") < 0)
            df.loc[mask, "primary_loss_reason"] = "STOP_TOO_TIGHT_CANDIDATE"
            df.loc[mask, "causality_language"] = "ASSOCIATED"
        losses = df[pd.to_numeric(df["result_R"], errors="coerce") < 0].copy()
        if losses.empty:
            return pd.DataFrame()
        losses["negative_R_abs"] = pd.to_numeric(losses["result_R"], errors="coerce").abs()
        out = losses.groupby(["data_source", "primary_loss_reason", "causality_language"], dropna=False).agg(
            N=("result_R", "size"),
            total_negative_R=("negative_R_abs", "sum"),
            avg_loss_R=("result_R", "mean"),
            unique_days=("trade_date", "nunique"),
        ).reset_index()
        totals = out.groupby("data_source")["total_negative_R"].transform("sum")
        out["share_of_negative_R"] = (out["total_negative_R"] / totals).round(4)
        out["total_negative_R"] = out["total_negative_R"].round(4)
        out["avg_loss_R"] = out["avg_loss_R"].round(4)
        return out.sort_values(["data_source", "total_negative_R"], ascending=[True, False], ignore_index=True)

    def _counterfactual_rescue(self, baseline: pd.DataFrame) -> pd.DataFrame:
        if baseline.empty:
            return pd.DataFrame()
        losses = baseline[(baseline["resolved"]) & (pd.to_numeric(baseline["result_R"], errors="coerce") < 0)].copy()
        if losses.empty:
            return pd.DataFrame()
        rows: list[dict[str, Any]] = []
        for raw in losses.to_dict("records"):
            mfe = safe_float(raw.get("MFE_R"), 0.0) or 0.0
            structure = str(raw.get("structure_alignment") or "").upper()
            pred = str(raw.get("predicted_direction") or "").upper()
            direction = str(raw.get("direction") or "").upper()
            if pred not in {"", "UNKNOWN", direction}:
                stage = "DIRECTION_CLASSIFIER"
            elif structure in {"COUNTERTREND", "CONFLICT"}:
                stage = "STRUCTURE_CONFIRMATION"
            elif str(raw.get("entry_quality_class") or "").upper() in {"LATE_ENTRY", "EARLY_ENTRY", "EXTENDED_ENTRY"}:
                stage = "BETTER_ENTRY"
            elif "stop" in str(raw.get("exit_reason") or "").lower() and mfe >= 0.5:
                stage = "ALTERNATIVE_STOP"
            elif mfe >= 0.5:
                stage = "PROFIT_PROTECTION"
            else:
                stage = "NOT_RESCUED_BY_TESTED_COUNTERFACTUALS"
            rows.append(
                {
                    "data_source": raw.get("data_source"),
                    "parent_event_id": raw.get("parent_event_id"),
                    "symbol": raw.get("symbol"),
                    "trade_date": raw.get("trade_date"),
                    "direction": direction,
                    "result_R": raw.get("result_R"),
                    "MFE_R": raw.get("MFE_R"),
                    "MAE_R": raw.get("MAE_R"),
                    "exit_reason": raw.get("exit_reason"),
                    "first_rescue_stage": stage,
                    "counterfactual_language": "DIAGNOSTIC_ASSOCIATION_NOT_CAUSAL_PROOF",
                }
            )
        return pd.DataFrame(rows)

    def _discovery_holdout(self, branches: pd.DataFrame) -> pd.DataFrame:
        if branches.empty:
            return pd.DataFrame()
        df = branches[
            (branches["is_control"] == False)  # noqa: E712
            & (branches["entry_variant"] == "ENTRY_1_CLOSE_RECLAIM")
            & (branches["stop_variant"] == "STOP_A_CURRENT_STRUCTURAL")
            & (branches["management_variant"] == "TM_V0_CURRENT")
            & (branches["resolved"])
        ].copy()
        if df.empty:
            return pd.DataFrame()
        out = grouped_summary(df, ["data_source", "sample_split", "strategy_variant", "direction"])
        out["historical_result_status"] = out.apply(lambda r: research_status(int(r["N"]), int(r["unique_days"]), safe_float(r["expectancy"], None), safe_float(r["PF"], None)), axis=1)
        return out

    def _walkforward(self, baseline: pd.DataFrame) -> pd.DataFrame:
        if baseline.empty:
            return pd.DataFrame()
        df = baseline[(baseline["data_source"] == HIST_SOURCE) & baseline["resolved"]].copy()
        if df.empty:
            return pd.DataFrame()
        df["trade_date_dt"] = pd.to_datetime(df["trade_date"], errors="coerce")
        df = df.dropna(subset=["trade_date_dt"]).sort_values("trade_date_dt")
        if df.empty:
            return pd.DataFrame()
        start = df["trade_date_dt"].min().to_period("M").to_timestamp()
        end = df["trade_date_dt"].max()
        rows: list[dict[str, Any]] = []
        window_start = start
        while window_start + pd.DateOffset(months=9) <= end + pd.DateOffset(days=1):
            discovery_end = window_start + pd.DateOffset(months=6)
            holdout_end = discovery_end + pd.DateOffset(months=3)
            discovery = df[(df["trade_date_dt"] >= window_start) & (df["trade_date_dt"] < discovery_end)]
            holdout = df[(df["trade_date_dt"] >= discovery_end) & (df["trade_date_dt"] < holdout_end)]
            for label, subset in [("DISCOVERY_6M", discovery), ("HOLDOUT_3M", holdout)]:
                row = summary_row(subset, None)
                row.update(
                    {
                        "window_start": window_start.date().isoformat(),
                        "discovery_end": discovery_end.date().isoformat(),
                        "holdout_end": holdout_end.date().isoformat(),
                        "window_leg": label,
                    }
                )
                rows.append(row)
            window_start = window_start + pd.DateOffset(months=3)
        return pd.DataFrame(rows)

    def _render_report(
        self,
        events: pd.DataFrame,
        branches: pd.DataFrame,
        baseline: pd.DataFrame,
        stop_comparison: pd.DataFrame,
        winner_mae: pd.DataFrame,
        stop_recovery: pd.DataFrame,
        giveback: pd.DataFrame,
        breakeven: pd.DataFrame,
        target_distribution: pd.DataFrame,
        holding_horizon: pd.DataFrame,
        structure_5m_vs_15m: pd.DataFrame,
        direction_classifier: pd.DataFrame,
        entry_comparison: pd.DataFrame,
        options_ablation: pd.DataFrame,
        loss_attribution: pd.DataFrame,
        counterfactual_rescue: pd.DataFrame,
        discovery_holdout: pd.DataFrame,
        walkforward: pd.DataFrame,
    ) -> str:
        baseline_hist = baseline[baseline["data_source"] == HIST_SOURCE] if not baseline.empty else pd.DataFrame()
        baseline_live = baseline[baseline["data_source"] == LIVE_SOURCE] if not baseline.empty else pd.DataFrame()
        hist_stats = summary_row(baseline_hist, "HIST_STATIC_D1")
        live_stats = summary_row(baseline_live, "LIVE_RECORDED_RETROSPECTIVE")

        stop_s0 = self._pick_row(stop_comparison, stop_experiment_variant="S0_CANONICAL_STOP")
        stop_s1 = self._pick_row(stop_comparison, stop_experiment_variant="S1_FULL_OPTIONS_ZONE_INVALIDATION")
        stop_s2 = self._pick_row(stop_comparison, stop_experiment_variant="S2_15M_STRUCTURAL_INVALIDATION_PROXY")
        historical_stop_rows = stop_comparison[stop_comparison["data_source"] == HIST_SOURCE] if not stop_comparison.empty and "data_source" in stop_comparison else stop_comparison
        best_stop = self._best_by_expectancy(historical_stop_rows, "stop_experiment_variant")

        model = self._pick_row(direction_classifier, direction_model="MODEL_DIRECTION_CLASSIFIER")
        naive = self._pick_row(direction_classifier, direction_model="NAIVE_LEVEL_DIRECTION")
        p0 = self._pick_row(options_ablation, ablation="P0_PRICE_STRUCTURE_ONLY_CONTROLS")
        p1 = self._pick_row(options_ablation, ablation="P1_PRICE_STRUCTURE_PLUS_STATIC_STRONG_OPTIONS_LEVEL")
        p4 = self._pick_row(options_ablation, ablation="P4_OPTIONS_DIRECTION_CLASSIFIER_PLUS_15M_CONFIRMATION")
        tf_5 = self._pick_row(structure_5m_vs_15m, strategy_variant="VARIANT_A_HIST_5M_CONFIRM_5M_ENTRY")
        tf_15 = self._pick_row(structure_5m_vs_15m, strategy_variant="VARIANT_B_HIST_15M_CONFIRM_5M_ENTRY")
        be_best = self._best_by_expectancy(breakeven, "management_replay_variant")

        loser_giveback = giveback[pd.to_numeric(giveback.get("final_realized_R"), errors="coerce") < 0] if not giveback.empty else pd.DataFrame()
        losers = len(loser_giveback)
        loser_05 = self._rate(loser_giveback, "loser_reached_0_5R")
        loser_07 = self._rate(loser_giveback, "loser_reached_0_7R")
        loser_1 = self._rate(loser_giveback, "loser_reached_1R")
        median_giveback = pctl(giveback["giveback_R"], 0.5) if not giveback.empty and "giveback_R" in giveback else None
        median_time_to_mfe = pctl(baseline_hist["time_to_MFE_minutes"], 0.5) if not baseline_hist.empty and "time_to_MFE_minutes" in baseline_hist else None
        normal_winner_mae = pctl(baseline_hist[pd.to_numeric(baseline_hist["result_R"], errors="coerce") > 0]["MAE_R"], 0.5) if not baseline_hist.empty else None

        stop_recovery_rate = None
        if not stop_recovery.empty and "reached_0_5R_within_120m" in stop_recovery:
            stop_recovery_rate = round(float(stop_recovery["reached_0_5R_within_120m"].fillna(False).mean()), 4)

        largest_loss = loss_attribution.head(1).to_dict("records")[0] if not loss_attribution.empty else {}
        top_rescue = counterfactual_rescue["first_rescue_stage"].value_counts().head(3).to_dict() if not counterfactual_rescue.empty else {}
        target_ranges = self._target_range_summary(target_distribution)
        top_hypotheses = self._top_hypotheses(stop_comparison, breakeven, options_ablation, structure_5m_vs_15m)

        lines: list[str] = [
            "# Phase 4B.2-H Historical Execution & Edge Decomposition Replay",
            "",
            f"Generated: `{self.generated_at_utc}`",
            "",
            "Scope: research-only historical diagnostic. Canonical strategy, live daemon, provider gates, prospective Phase 4B.2 branches, live-execution settings, and Portfolio OS isolation were not modified.",
            "",
            "Historical limitation: `HIST_STATIC_D1` uses previous-day EOD options levels. It cannot reconstruct true intraday options persistence, strengthening/weakening, wall migration, gamma-flip migration, or dynamic GEX change. Those remain `FORWARD_ONLY`.",
            "",
            "## Top answers",
            "",
            f"1. Raw directional excursion before management: yes in the sense that historical baseline median MFE is `{hist_stats.get('median_MFE')}`R and mean MFE is `{hist_stats.get('MFE')}`R, but realized expectancy remains `{hist_stats.get('expectancy')}`R. The raw excursion is fat-tailed, not broadly monetized.",
            f"2. 15m structure vs 5m: 5m baseline expectancy `{tf_5.get('expectancy')}`R / PF `{tf_5.get('PF')}` versus 15m confirmation expectancy `{tf_15.get('expectancy')}`R / PF `{tf_15.get('PF')}`. This is historical/static-D1 only.",
            f"3. Direction classification: model-aligned events expectancy `{model.get('expectancy')}`R / PF `{model.get('PF')}` versus naive level direction `{naive.get('expectancy')}`R / PF `{naive.get('PF')}`. This is diagnostic, not a promotion.",
            f"4. Canonical stops: associated stop issue remains visible. S0 expectancy `{stop_s0.get('expectancy')}`R; S1 zone invalidation `{stop_s1.get('expectancy')}`R; S2 15m proxy `{stop_s2.get('expectancy')}`R. Best tested stop row: `{best_stop}`.",
            f"5. Stopped-trade recovery: `{stop_recovery_rate}` of canonical stop-outs had lifecycle MFE >= +0.5R in the post-stop proxy table. Exact post-stop ordering is not proven by this default artifact.",
            f"6. Normal winner MAE: historical canonical winner median MAE is `{normal_winner_mae}`R. See `phase4b2h_winner_mae.csv` for P10/P25/P75/P90/P95 by segment.",
            f"7. Losers first reaching favorable excursion: among `{losers}` losing baseline events, +0.5R `{loser_05}`, +0.7R `{loser_07}`, +1R `{loser_1}` before final loss by stored/derived MFE.",
            f"8. MFE giveback: median giveback across resolved baseline events is `{median_giveback}`R. Large positive MFE with negative realized R remains an execution/management leak candidate.",
            f"9. Breakeven/protection: best research replay row by expectancy is `{be_best}`. Treat M4 as a structural-trail proxy, not a true live 15m swing manager.",
            f"10. Target range matching movement: `{target_ranges}`",
            f"11. Natural holding time: median time-to-MFE in historical baseline is `{median_time_to_mfe}` minutes.",
            f"12. Static options info beyond structure: P0 controls expectancy `{p0.get('expectancy')}`R / PF `{p0.get('PF')}`; P1 static options+structure `{p1.get('expectancy')}`R / PF `{p1.get('PF')}`; P4 static options+classifier+15m `{p4.get('expectancy')}`R / PF `{p4.get('PF')}`. This does not answer dynamic intraday options edge.",
            f"13. Largest avoidable-loss association: `{largest_loss.get('primary_loss_reason', 'UNKNOWN')}` with share `{largest_loss.get('share_of_negative_R')}` of negative R in its source bucket.",
            f"14. Top 3 prospective hypotheses to consider after current frozen Phase 4B.2 branches: {top_hypotheses}",
            "",
            "## Dataset reconciliation",
            "",
            f"- Parent events written: `{len(events)}`",
            f"- Historical static-D1 events: `{int((events['data_source'] == HIST_SOURCE).sum()) if not events.empty else 0}`",
            f"- Live recorded retrospective events: `{int((events['data_source'] == LIVE_SOURCE).sum()) if not events.empty else 0}`",
            f"- Historical/live branches read: `{len(branches)}`",
            f"- Primary baseline branches used for headline diagnostics: `{len(baseline)}`",
            f"- Synthetic/test records: excluded by source filters; no synthetic rows are intentionally included.",
            "",
            "## Baseline performance by source",
            "",
            self._markdown_table(pd.DataFrame([hist_stats, live_stats]), ["label", "N", "unique_days", "expectancy", "PF", "win_rate", "median_R", "MFE", "MAE", "max_DD"]),
            "",
            "## Stop experiment summary",
            "",
            self._markdown_table(stop_comparison.head(12), ["data_source", "stop_experiment_variant", "direction", "N", "unique_days", "expectancy", "PF", "win_rate", "MFE", "MAE", "stop_frequency"]),
            "",
            "## Profit protection / breakeven summary",
            "",
            self._markdown_table(breakeven.head(16), ["management_replay_variant", "direction", "N", "unique_days", "expectancy", "PF", "win_rate", "BE_exit_rate", "max_DD", "research_status"]),
            "",
            "## Options-value ablation",
            "",
            self._markdown_table(options_ablation.head(16), ["ablation", "direction", "N", "unique_days", "expectancy", "PF", "win_rate", "MFE", "MAE", "availability", "research_status"]),
            "",
            "## 5m vs 15m structure",
            "",
            self._markdown_table(structure_5m_vs_15m.head(12), ["strategy_variant", "confirmation_tf", "direction", "N", "unique_days", "expectancy", "PF", "win_rate", "MFE", "MAE"]),
            "",
            "## Direction classifier comparison",
            "",
            self._markdown_table(direction_classifier.head(16), ["data_source", "direction_model", "direction", "N", "unique_days", "expectancy", "PF", "win_rate", "model_coverage", "model_alignment_rate", "all_events_expectancy"]),
            "",
            "## Loss attribution",
            "",
            self._markdown_table(loss_attribution.head(16), ["data_source", "primary_loss_reason", "causality_language", "N", "total_negative_R", "share_of_negative_R", "unique_days"]),
            "",
            "## Counterfactual rescue waterfall",
            "",
            f"Top rescue stages: `{json.dumps(top_rescue, sort_keys=True)}`",
            "",
            "## Discovery / holdout and walk-forward",
            "",
            self._markdown_table(discovery_holdout.head(12), ["data_source", "sample_split", "strategy_variant", "direction", "N", "unique_days", "expectancy", "PF", "win_rate", "historical_result_status"]),
            "",
            self._markdown_table(walkforward.head(12), ["window_start", "window_leg", "N", "unique_days", "expectancy", "PF", "win_rate", "positive_day_pct", "day_block_ci_low", "day_block_ci_high"]),
            "",
            "## Forward-only items explicitly not reconstructed",
            "",
            "- true intraday options-level persistence",
            "- strengthening / weakening across live snapshots",
            "- call-wall / put-wall migration",
            "- gamma-flip migration",
            "- dynamic intraday GEX change",
            "",
            "These remain prospective-only in Phase 4B.2. Historical static-D1 results must not be merged into forward validation or used for automatic parameter promotion.",
            "",
            "## Output files",
            "",
        ]
        for name in [
            "phase4b2h_events.parquet",
            "phase4b2h_stop_comparison.csv",
            "phase4b2h_winner_mae.csv",
            "phase4b2h_stop_recovery.csv",
            "phase4b2h_giveback.csv",
            "phase4b2h_breakeven.csv",
            "phase4b2h_target_distribution.csv",
            "phase4b2h_holding_horizon.csv",
            "phase4b2h_structure_5m_vs_15m.csv",
            "phase4b2h_direction_classifier.csv",
            "phase4b2h_entry_comparison.csv",
            "phase4b2h_options_ablation.csv",
            "phase4b2h_loss_attribution.csv",
            "phase4b2h_counterfactual_rescue.csv",
            "phase4b2h_discovery_holdout.csv",
            "phase4b2h_walkforward.csv",
            "phase4b2h_management_simulation.csv",
        ]:
            lines.append(f"- `{name}`")
        lines.extend(
            [
                "",
                "## Decision note",
                "",
                "No historical result in this report is `FORWARD_SUPPORTED`. Any useful branch remains hypothesis-generating until validated prospectively across independent RTH days.",
            ]
        )
        return "\n".join(lines) + "\n"

    @staticmethod
    def _pick_row(df: pd.DataFrame, **filters: Any) -> dict[str, Any]:
        if df.empty:
            return {}
        work = df
        for col, value in filters.items():
            if col not in work.columns:
                return {}
            work = work[work[col] == value]
        if work.empty:
            return {}
        if "N" in work.columns:
            work = work.sort_values("N", ascending=False)
        return work.iloc[0].to_dict()

    @staticmethod
    def _best_by_expectancy(df: pd.DataFrame, label_col: str) -> str:
        if df.empty or "expectancy" not in df.columns or label_col not in df.columns:
            return "UNAVAILABLE"
        work = df.copy()
        work["expectancy_numeric"] = pd.to_numeric(work["expectancy"], errors="coerce")
        work = work.dropna(subset=["expectancy_numeric"])
        if work.empty:
            return "UNAVAILABLE"
        row = work.sort_values(["expectancy_numeric", "N"], ascending=[False, False]).iloc[0]
        return f"{row.get(label_col)} ({row.get('direction', 'ALL')}): expectancy {row.get('expectancy')}R, PF {row.get('PF')}, N {row.get('N')}, days {row.get('unique_days')}"

    @staticmethod
    def _rate(df: pd.DataFrame, col: str) -> float | None:
        if df.empty or col not in df.columns:
            return None
        return round(float(df[col].fillna(False).mean()), 4)

    @staticmethod
    def _target_range_summary(target_distribution: pd.DataFrame) -> str:
        if target_distribution.empty:
            return "UNAVAILABLE"
        raw = target_distribution[target_distribution.get("section") == "RAW_MFE_TARGET_DISTRIBUTION"] if "section" in target_distribution else target_distribution
        if raw.empty:
            raw = target_distribution
        cols = [col for col in raw.columns if col.startswith("reach_") and col.endswith("_rate")]
        if not cols:
            return "UNAVAILABLE"
        weighted: list[tuple[str, float]] = []
        for col in cols:
            vals = pd.to_numeric(raw[col], errors="coerce")
            weights = pd.to_numeric(raw.get("N", pd.Series([1] * len(raw))), errors="coerce").fillna(1)
            if vals.notna().any():
                weighted.append((col.replace("reach_", "").replace("_rate", "").replace("_", "."), round(float((vals.fillna(0) * weights).sum() / weights.sum()), 4)))
        useful = [item for item in weighted if item[1] >= 0.5]
        if useful:
            label = useful[-1][0]
            suffix = "" if label.upper().endswith("R") else "R"
            return f"highest threshold with >=50% historical reach: {label}{suffix} at rate {useful[-1][1]}"
        return f"no threshold reached by >=50%; top observed {weighted[0] if weighted else 'UNAVAILABLE'}"

    @staticmethod
    def _top_hypotheses(
        stop_comparison: pd.DataFrame,
        breakeven: pd.DataFrame,
        options_ablation: pd.DataFrame,
        structure_5m_vs_15m: pd.DataFrame,
    ) -> str:
        hypotheses: list[str] = []
        if not stop_comparison.empty:
            historical_stop = stop_comparison[stop_comparison["data_source"] == HIST_SOURCE] if "data_source" in stop_comparison else stop_comparison
            best_stop = Phase4B2HHistoricalDiagnostic._best_by_expectancy(historical_stop, "stop_experiment_variant")
            hypotheses.append(f"historical stop/invalidation branch: {best_stop}")
        if not breakeven.empty:
            best_mgmt = Phase4B2HHistoricalDiagnostic._best_by_expectancy(breakeven, "management_replay_variant")
            hypotheses.append(f"profit-protection extrema-proxy branch: {best_mgmt}")
        if not options_ablation.empty:
            p4 = Phase4B2HHistoricalDiagnostic._pick_row(options_ablation, ablation="P4_OPTIONS_DIRECTION_CLASSIFIER_PLUS_15M_CONFIRMATION")
            p0 = Phase4B2HHistoricalDiagnostic._pick_row(options_ablation, ablation="P0_PRICE_STRUCTURE_ONLY_CONTROLS")
            hypotheses.append(f"options-value test: compare P4 expectancy {p4.get('expectancy')}R/PF {p4.get('PF')} versus P0 {p0.get('expectancy')}R/PF {p0.get('PF')} prospectively")
        if not structure_5m_vs_15m.empty:
            tf15 = Phase4B2HHistoricalDiagnostic._pick_row(structure_5m_vs_15m, strategy_variant="VARIANT_B_HIST_15M_CONFIRM_5M_ENTRY")
            hypotheses.append(f"15m confirmation branch: expectancy {tf15.get('expectancy')}R/PF {tf15.get('PF')} with N {tf15.get('N')}")
        return "; ".join(hypotheses[:3]) if hypotheses else "UNAVAILABLE"

    @staticmethod
    def _markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 12) -> str:
        if df.empty:
            return "_No rows available._"
        existing = [col for col in columns if col in df.columns]
        if not existing:
            return "_Requested columns unavailable._"
        work = df[existing].head(max_rows).copy()
        def cell(value: Any) -> str:
            if value is None:
                return ""
            try:
                if pd.isna(value):
                    return ""
            except (TypeError, ValueError):
                pass
            text = str(value)
            return text.replace("|", "\\|").replace("\n", " ")

        header = "| " + " | ".join(existing) + " |"
        sep = "| " + " | ".join(["---"] * len(existing)) + " |"
        body = [
            "| " + " | ".join(cell(row[col]) for col in existing) + " |"
            for _, row in work.iterrows()
        ]
        return "\n".join([header, sep, *body])
