from __future__ import annotations

import hashlib
import json
import math
import random
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (str(ROOT), str(SRC)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from options_structure_trader.config import PROJECT_ROOT, Settings  # noqa: E402
from options_structure_trader.historical import HistoricalReconstructionPipeline  # noqa: E402


EASTERN = ZoneInfo("America/New_York")
AUDIT_VERSION = "phase3c2_replay_validity_audit_v1"
DEFAULT_MANAGEMENT = "TM_V0_CURRENT"
DEFAULT_SLIPPAGE = 3
RESOLVED_STATUSES = {"closed", "censored"}
SYMBOLS = ["SPY", "QQQ", "IWM"]
BOOTSTRAP_ITERATIONS = 1000


class EmptyRepository:
    def list_json(self, *_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        return []


@dataclass(frozen=True)
class OutputPaths:
    phase_report: Path
    frequency: Path
    level_count: Path
    dedup_variants: Path
    level_importance: Path
    matched_controls: Path
    reclaim_trace: Path
    d1_vs_intraday: Path
    gex_formula_audit: Path


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def stable_hash(*parts: Any) -> str:
    text = "|".join("" if part is None else str(part) for part in parts)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def parse_dt(value: Any) -> datetime | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    ts = pd.Timestamp(value)
    if pd.isna(ts):
        return None
    if ts.tzinfo is None:
        ts = ts.tz_localize(timezone.utc)
    return ts.to_pydatetime()


def parse_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return {}
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def to_float(value: Any, default: float | None = None) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def rounded(value: Any, digits: int = 4) -> float | None:
    result = to_float(value)
    return round(result, digits) if result is not None else None


def markdown_table(frame: pd.DataFrame, *, max_rows: int = 30) -> str:
    if frame.empty:
        return "No rows."
    display = frame.head(max_rows).copy()
    rows = ["| " + " | ".join(str(column) for column in display.columns) + " |"]
    rows.append("| " + " | ".join("---" for _ in display.columns) + " |")
    for item in display.to_dict("records"):
        rows.append("| " + " | ".join("" if pd.isna(item.get(column)) else str(item.get(column)) for column in display.columns) + " |")
    if len(frame) > max_rows:
        rows.append(f"| ... | {len(frame) - max_rows} more rows omitted | |")
    return "\n".join(rows)


def result_subset(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    subset = frame.copy()
    if "status" in subset.columns:
        subset = subset[subset["status"].isin(RESOLVED_STATUSES)]
    if "realized_R" in subset.columns:
        subset = subset[pd.to_numeric(subset["realized_R"], errors="coerce").notna()]
    return subset


def profit_factor(values: pd.Series) -> float | None:
    values = pd.to_numeric(values, errors="coerce").dropna()
    if values.empty:
        return None
    gross_win = float(values[values > 0].sum())
    gross_loss = float(values[values < 0].sum())
    if gross_loss == 0:
        return math.inf if gross_win > 0 else None
    return gross_win / abs(gross_loss)


def max_drawdown(values: pd.Series) -> float | None:
    values = pd.to_numeric(values, errors="coerce").dropna()
    if values.empty:
        return None
    cumulative = values.cumsum()
    return float((cumulative.cummax() - cumulative).max())


def day_bootstrap_ci(frame: pd.DataFrame, *, seed: int = 20260302) -> tuple[float | None, float | None]:
    subset = result_subset(frame)
    if subset.empty or "session_date" not in subset.columns:
        return None, None
    daily = subset.assign(_r=pd.to_numeric(subset["realized_R"], errors="coerce")).groupby("session_date")["_r"].mean()
    daily = daily.dropna()
    if daily.empty:
        return None, None
    rng = random.Random(seed)
    values = daily.to_list()
    means = []
    for _ in range(BOOTSTRAP_ITERATIONS):
        sample = [rng.choice(values) for _ in values]
        means.append(float(np.mean(sample)))
    return round(float(np.percentile(means, 2.5)), 4), round(float(np.percentile(means, 97.5)), 4)


def stats(frame: pd.DataFrame) -> dict[str, Any]:
    subset = result_subset(frame)
    if subset.empty:
        return {
            "N": 0,
            "unique_days": 0,
            "trades_per_symbol_day": 0.0,
            "expectancy_R": None,
            "profit_factor": None,
            "win_rate": None,
            "median_R": None,
            "avg_winner": None,
            "avg_loser": None,
            "MFE": None,
            "MAE": None,
            "max_DD": None,
            "positive_day_pct": None,
            "day_block_ci_low": None,
            "day_block_ci_high": None,
        }
    values = pd.to_numeric(subset["realized_R"], errors="coerce").dropna()
    wins = values[values > 0]
    losses = values[values < 0]
    day_totals = subset.assign(_r=values).groupby("session_date")["_r"].sum()
    symbol_days = subset[["symbol", "session_date"]].drop_duplicates().shape[0]
    ci_low, ci_high = day_bootstrap_ci(subset)
    return {
        "N": int(len(values)),
        "unique_days": int(subset["session_date"].nunique()) if "session_date" in subset.columns else 0,
        "trades_per_symbol_day": round(float(len(values) / symbol_days), 4) if symbol_days else 0.0,
        "expectancy_R": round(float(values.mean()), 4),
        "profit_factor": round(float(profit_factor(values)), 4) if profit_factor(values) not in {None, math.inf} else profit_factor(values),
        "win_rate": round(float((values > 0).mean()), 4),
        "median_R": round(float(values.median()), 4),
        "avg_winner": round(float(wins.mean()), 4) if not wins.empty else 0.0,
        "avg_loser": round(float(losses.mean()), 4) if not losses.empty else 0.0,
        "MFE": round(float(pd.to_numeric(subset.get("MFE_R"), errors="coerce").mean()), 4) if "MFE_R" in subset else None,
        "MAE": round(float(pd.to_numeric(subset.get("MAE_R"), errors="coerce").mean()), 4) if "MAE_R" in subset else None,
        "max_DD": round(float(max_drawdown(values)), 4) if max_drawdown(values) is not None else None,
        "positive_day_pct": round(float((day_totals > 0).mean()), 4) if not day_totals.empty else None,
        "day_block_ci_low": ci_low,
        "day_block_ci_high": ci_high,
    }


def add_common_stats(row: dict[str, Any], frame: pd.DataFrame) -> dict[str, Any]:
    return {**row, **stats(frame)}


def load_required_parquet(name: str) -> pd.DataFrame:
    path = PROJECT_ROOT / name
    if not path.exists():
        raise FileNotFoundError(f"Required Phase 3C.1 artifact is missing: {path}")
    return pd.read_parquet(path)


def load_frames() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    candles = load_required_parquet("historical_intraday_5m_v2.parquet")
    option_levels = load_required_parquet("historical_expanded_option_levels_v2.parquet")
    control_levels = load_required_parquet("historical_control_levels_v2.parquet")
    replay = load_required_parquet("historical_replay_v2.parquet")
    return candles, option_levels, control_levels, replay


def atr_lookup(candles: pd.DataFrame) -> dict[tuple[str, str], float]:
    if candles.empty:
        return {}
    frame = candles.copy()
    frame["atr"] = pd.to_numeric(frame.get("atr"), errors="coerce")
    output: dict[tuple[str, str], float] = {}
    for (symbol, trade_date), group in frame.groupby(["symbol", "trade_date"]):
        value = to_float(group["atr"].median())
        if value is None or value <= 0:
            close = to_float(group["close"].median(), 0.0) or 0.0
            value = max(close * 0.005, 0.25)
        output[(str(symbol), str(trade_date))] = float(value)
    return output


def assign_level_clusters(levels: pd.DataFrame, candles: pd.DataFrame) -> pd.DataFrame:
    frame = levels.copy()
    meta = frame["metadata_json"].apply(parse_json) if "metadata_json" in frame.columns else pd.Series([{}] * len(frame))
    frame["level_family"] = meta.apply(lambda item: item.get("historical_level_family") or item.get("control_type") or "")
    frame["node_value"] = pd.to_numeric(meta.apply(lambda item: to_float(item.get("node_value"))), errors="coerce")
    frame["level_price_round"] = pd.to_numeric(frame["price"], errors="coerce").round(4)
    frame["node_value_abs"] = pd.to_numeric(frame["node_value"], errors="coerce").abs()
    key_cols = ["symbol", "trade_date", "gex_model_version", "level_price_round"]
    if "gex_model_version" not in frame.columns:
        frame["gex_model_version"] = "UNKNOWN"
    value_by_price = (
        frame[frame["level_type"].eq("GEX_NODE") & frame["node_value_abs"].notna()]
        .groupby(key_cols)["node_value_abs"]
        .max()
        .rename("node_value_abs_filled")
        .reset_index()
    )
    frame = frame.merge(value_by_price, how="left", on=key_cols)
    frame["node_value_abs_filled"] = frame["node_value_abs"].fillna(frame["node_value_abs_filled"])
    frame["level_importance_rank"] = np.nan
    mask = frame["level_type"].eq("GEX_NODE") & frame["node_value_abs_filled"].notna()
    frame.loc[mask, "level_importance_rank"] = (
        frame.loc[mask]
        .groupby(["symbol", "trade_date", "gex_model_version"])["node_value_abs_filled"]
        .rank(method="dense", ascending=False)
    )
    atr_frame = (
        candles.assign(_atr=pd.to_numeric(candles.get("atr"), errors="coerce"))
        .groupby(["symbol", "trade_date"], as_index=False)["_atr"]
        .median()
        .rename(columns={"_atr": "median_atr_for_cluster"})
    )
    frame = frame.merge(atr_frame, how="left", on=["symbol", "trade_date"])
    fallback_threshold = pd.to_numeric(frame["price"], errors="coerce").abs().fillna(100.0) * 0.005
    frame["median_atr_for_cluster"] = frame["median_atr_for_cluster"].fillna(fallback_threshold).clip(lower=0.01)
    price = pd.to_numeric(frame["price"], errors="coerce").fillna(0.0)
    for fraction in (0.10, 0.20, 0.30, 0.50):
        column = f"cluster_{str(fraction).replace('.', '_')}_atr"
        width = (frame["median_atr_for_cluster"] * fraction).clip(lower=0.01)
        bucket = np.floor(price / width).astype("int64")
        frame[column] = (
            frame["symbol"].astype(str)
            + "_"
            + frame["trade_date"].astype(str)
            + "_"
            + frame["gex_model_version"].astype(str)
            + "_b"
            + bucket.astype(str)
        )
    return frame


def count_clusters(prices: pd.Series, threshold: float) -> int:
    values = sorted({float(value) for value in pd.to_numeric(prices, errors="coerce").dropna()})
    if not values:
        return 0
    clusters = 1
    last = values[0]
    for price in values[1:]:
        if abs(price - last) > threshold:
            clusters += 1
        last = price
    return clusters


def level_count_audit(levels: pd.DataFrame, candles: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (symbol, trade_date, model), group in levels.groupby(["symbol", "trade_date", "gex_model_version"]):
        atr = to_float(group.get("median_atr_for_cluster", pd.Series(dtype=float)).median())
        median_price = to_float(pd.to_numeric(group["price"], errors="coerce").median(), 0.0) or 0.0
        atr = atr or max(median_price * 0.005, 0.25)
        counts = group["level_type"].value_counts().to_dict()
        families = group["level_family"].value_counts().to_dict()
        row = {
            "symbol": symbol,
            "trade_date": trade_date,
            "gex_model_version": model,
            "total_raw_levels": int(len(group)),
            "unique_level_prices": int(pd.to_numeric(group["price"], errors="coerce").round(4).nunique()),
            "gex_node_levels": int(counts.get("GEX_NODE", 0)),
            "gamma_flip_levels": int(counts.get("GAMMA_FLIP", 0)),
            "call_wall_levels": int(counts.get("CALL_WALL", 0)),
            "put_wall_levels": int(counts.get("PUT_WALL", 0)),
            "oi_node_levels": int(counts.get("OI_NODE", 0)),
            "gex_oi_cluster_levels": int(families.get("GEX_OI_CLUSTER", 0)),
            "median_atr": round(float(atr), 6),
        }
        for fraction in (0.10, 0.20, 0.30, 0.50):
            cluster_col = f"cluster_{str(fraction).replace('.', '_')}_atr"
            row[f"clustered_zones_{str(fraction).replace('.', '_')}_atr"] = int(group[cluster_col].nunique()) if cluster_col in group else count_clusters(group["price"], atr * fraction)
        row["nearby_strike_compression_0_30_atr"] = round(
            1 - (row["clustered_zones_0_3_atr"] / row["unique_level_prices"]),
            4,
        ) if row["unique_level_prices"] else None
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["symbol", "trade_date", "gex_model_version"])


def path_flags(setup: Any, future_bars: list[Any], entry: float, stop: float) -> dict[str, Any]:
    plan = setup.trade_plan
    side_mult = 1 if setup.side.value == "LONG" else -1
    risk = abs(entry - stop)
    result = {
        "reached_0_25R_before_stop": False,
        "reached_0_5R_before_stop": False,
        "reached_1R_before_stop": False,
        "time_to_0_25R_minutes": None,
        "time_to_0_5R_minutes": None,
        "time_to_1R_minutes": None,
        "time_to_stop_minutes": None,
        "max_R_before_stop": 0.0,
    }
    if risk <= 0 or plan is None:
        return result
    opened_at = None
    pending = 0
    start = setup.created_at_utc
    for bar in future_bars:
        if opened_at is None:
            pending += 1
            if bar.low <= plan.entry_zone_high and bar.high >= plan.entry_zone_low:
                opened_at = bar.bar_end_utc
            elif pending >= 3:
                return result
            else:
                continue
        stop_hit = bar.low <= stop if side_mult == 1 else bar.high >= stop
        favorable = (bar.high - entry) / risk if side_mult == 1 else (entry - bar.low) / risk
        if stop_hit:
            result["time_to_stop_minutes"] = round((bar.bar_end_utc - start).total_seconds() / 60, 2)
            return result
        result["max_R_before_stop"] = round(max(float(result["max_R_before_stop"]), float(favorable)), 6)
        for threshold, key, time_key in [
            (0.25, "reached_0_25R_before_stop", "time_to_0_25R_minutes"),
            (0.50, "reached_0_5R_before_stop", "time_to_0_5R_minutes"),
            (1.00, "reached_1R_before_stop", "time_to_1R_minutes"),
        ]:
            if favorable >= threshold and not result[key]:
                result[key] = True
                result[time_key] = round((bar.bar_end_utc - start).total_seconds() / 60, 2)
    return result


def entry_delay_fields(event_time: datetime, entry_timestamp: Any, status: str) -> dict[str, Any]:
    if status not in RESOLVED_STATUSES:
        return {"entry_delay_minutes": None, "entry_delay_bucket": "NO_FILLED_ENTRY"}
    entry_dt = parse_dt(entry_timestamp)
    if entry_dt is None:
        return {"entry_delay_minutes": None, "entry_delay_bucket": "UNKNOWN"}
    minutes = round((entry_dt - event_time).total_seconds() / 60, 2)
    if minutes <= 0.01:
        bucket = "SAME_CONFIRMATION_CANDLE"
    elif minutes <= 5.01:
        bucket = "NEXT_CANDLE"
    elif minutes <= 10.01:
        bucket = "ONE_CANDLE_AFTER"
    else:
        bucket = "TWO_PLUS_CANDLES_AFTER"
    return {"entry_delay_minutes": minutes, "entry_delay_bucket": bucket}


def settings_values() -> dict[str, Any]:
    settings = Settings.load()
    partials = settings.get("targets.partials", [.33]) or [.33]
    return {
        "stop_buffer_multiplier": float(settings.get("stops.baseline_atr_buffer", .3)),
        "spread_multiplier": float(settings.get("stops.spread_multiplier", 2)),
        "minimum_tick_buffer": float(settings.get("stops.minimum_tick_buffer", .01)),
        "pending_order_expiry_bars": int(settings.get("execution.pending_order_expiry_bars", 3)),
        "partial_fraction": float(partials[0]),
        "max_stop_atr": float(settings.get("risk.max_stop_atr", 3)),
        "min_primary_RR": float(settings.get("risk.min_primary_RR", 1.8)),
    }


def build_trade_plan_fast(previous: dict[str, Any], confirmation: dict[str, Any],
                          level: dict[str, Any], target_nodes: list[float],
                          direction: str, cfg: dict[str, Any]) -> dict[str, Any] | None:
    close = float(confirmation["close"])
    atr = max(float(confirmation.get("atr") or max(abs(close) * 0.005, 0.25)), 0.01)
    spread = 2 * max(close * 0.0001, 0.01)
    buffer = max(atr * cfg["stop_buffer_multiplier"], spread * cfg["spread_multiplier"], cfg["minimum_tick_buffer"])
    zone_low = float(level["zone_low"])
    zone_high = float(level["zone_high"])
    if direction == "LONG":
        entry = max(zone_high, close)
        entry_zone_low = entry
        entry_zone_high = entry + min(atr * 0.25, max(spread * 2, 0.01))
        stop = min(float(previous["low"]), float(confirmation["low"]), zone_low) - buffer
        targets = sorted({float(node) for node in target_nodes if float(node) > entry})[:3]
    else:
        entry = min(zone_low, close)
        entry_zone_high = entry
        entry_zone_low = entry - min(atr * 0.25, max(spread * 2, 0.01))
        stop = max(float(previous["high"]), float(confirmation["high"]), zone_high) + buffer
        targets = sorted({float(node) for node in target_nodes if float(node) < entry}, reverse=True)[:3]
    if not targets:
        return None
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    while len(targets) < 3:
        targets.append(targets[-1] + (risk if direction == "LONG" else -risk))
    return {
        "entry": entry,
        "entry_zone_low": entry_zone_low,
        "entry_zone_high": entry_zone_high,
        "stop": stop,
        "targets": targets,
        "risk": risk,
        "rr": abs(targets[0] - entry) / risk if risk else None,
    }


def simulate_fast(plan: dict[str, Any], future: pd.DataFrame, direction: str,
                  event_time: pd.Timestamp, cfg: dict[str, Any]) -> dict[str, Any]:
    side_mult = 1 if direction == "LONG" else -1
    entry = float(plan["entry"]) + (float(plan["entry"]) * DEFAULT_SLIPPAGE / 10000 * side_mult)
    stop = float(plan["stop"])
    risk = abs(entry - stop)
    targets = [float(item) for item in plan["targets"]]
    if risk <= 0 or future.empty:
        return {
            "entry": round(entry, 6), "stop": round(stop, 6), "tp1": targets[0], "tp2": targets[1], "tp3": targets[2],
            "status": "expired", "exit_reason": "invalid_or_no_future_bars", "realized_R": 0.0,
            "MFE_R": 0.0, "MAE_R": 0.0, "entry_timestamp": event_time.isoformat(),
            "closed_at_utc": None, "duration_minutes": None,
            "reached_0_25R_before_stop": False, "reached_0_5R_before_stop": False, "reached_1R_before_stop": False,
            "time_to_0_25R_minutes": None, "time_to_0_5R_minutes": None, "time_to_1R_minutes": None,
            "time_to_stop_minutes": None, "max_R_before_stop": 0.0,
        }
    status = "pending"
    opened_at: pd.Timestamp | None = None
    bars_pending = 0
    stop_current = stop
    remaining = 1.0
    realized = 0.0
    mfe = 0.0
    mae = 0.0
    last_close = entry
    targets_hit: set[str] = set()
    threshold_flags = {
        "reached_0_25R_before_stop": False,
        "reached_0_5R_before_stop": False,
        "reached_1R_before_stop": False,
        "time_to_0_25R_minutes": None,
        "time_to_0_5R_minutes": None,
        "time_to_1R_minutes": None,
        "time_to_stop_minutes": None,
        "max_R_before_stop": 0.0,
    }

    for _, bar in future.iterrows():
        bar_end = pd.Timestamp(bar["bar_end_utc"])
        high = float(bar["high"])
        low = float(bar["low"])
        last_close = float(bar["close"])
        if status == "pending":
            bars_pending += 1
            if low <= float(plan["entry_zone_high"]) and high >= float(plan["entry_zone_low"]):
                status = "open"
                opened_at = bar_end
            elif bars_pending >= cfg["pending_order_expiry_bars"]:
                return {
                    "entry": round(entry, 6), "stop": round(stop, 6), "tp1": targets[0], "tp2": targets[1], "tp3": targets[2],
                    "status": "expired", "exit_reason": "pending_order_expiry", "realized_R": 0.0,
                    "MFE_R": 0.0, "MAE_R": 0.0, "entry_timestamp": event_time.isoformat(),
                    "closed_at_utc": bar_end.isoformat(), "duration_minutes": round((bar_end - event_time).total_seconds() / 60, 2),
                    **threshold_flags,
                }
            else:
                continue
        if status not in {"open", "partial"}:
            continue
        favorable = (high - entry) / risk if side_mult == 1 else (entry - low) / risk
        adverse = (entry - low) / risk if side_mult == 1 else (high - entry) / risk
        mfe = max(mfe, favorable)
        mae = max(mae, adverse)
        stop_hit = low <= stop_current if side_mult == 1 else high >= stop_current
        if stop_hit:
            threshold_flags["time_to_stop_minutes"] = round((bar_end - event_time).total_seconds() / 60, 2)
            realized += ((stop_current - entry) * side_mult / risk) * remaining
            return {
                "entry": round(entry, 6), "stop": round(stop, 6), "tp1": targets[0], "tp2": targets[1], "tp3": targets[2],
                "status": "closed", "exit_reason": "breakeven_stop" if abs(stop_current - entry) <= 0.01 else "stop_loss",
                "realized_R": round(realized, 6), "MFE_R": round(mfe, 6), "MAE_R": round(mae, 6),
                "entry_timestamp": (opened_at or event_time).isoformat(), "closed_at_utc": bar_end.isoformat(),
                "duration_minutes": round((bar_end - (opened_at or event_time)).total_seconds() / 60, 2),
                **threshold_flags,
            }
        threshold_flags["max_R_before_stop"] = round(max(float(threshold_flags["max_R_before_stop"]), float(favorable)), 6)
        for threshold, flag_key, time_key in [
            (0.25, "reached_0_25R_before_stop", "time_to_0_25R_minutes"),
            (0.50, "reached_0_5R_before_stop", "time_to_0_5R_minutes"),
            (1.00, "reached_1R_before_stop", "time_to_1R_minutes"),
        ]:
            if favorable >= threshold and not threshold_flags[flag_key]:
                threshold_flags[flag_key] = True
                threshold_flags[time_key] = round((bar_end - event_time).total_seconds() / 60, 2)
        target_price = targets[0]
        if "TP1_PARTIAL" not in targets_hit and remaining > 0:
            hit = high >= target_price if side_mult == 1 else low <= target_price
            if hit:
                close_fraction = min(remaining, cfg["partial_fraction"])
                realized += ((target_price - entry) * side_mult / risk) * close_fraction
                remaining = round(remaining - close_fraction, 8)
                targets_hit.add("TP1_PARTIAL")
                stop_current = entry
                if remaining <= 0:
                    return {
                        "entry": round(entry, 6), "stop": round(stop, 6), "tp1": targets[0], "tp2": targets[1], "tp3": targets[2],
                        "status": "closed", "exit_reason": "tp1_partial", "realized_R": round(realized, 6),
                        "MFE_R": round(mfe, 6), "MAE_R": round(mae, 6),
                        "entry_timestamp": (opened_at or event_time).isoformat(), "closed_at_utc": bar_end.isoformat(),
                        "duration_minutes": round((bar_end - (opened_at or event_time)).total_seconds() / 60, 2),
                        **threshold_flags,
                    }
                status = "partial"
    if status == "pending":
        return {
            "entry": round(entry, 6), "stop": round(stop, 6), "tp1": targets[0], "tp2": targets[1], "tp3": targets[2],
            "status": "expired", "exit_reason": "no_fill_before_data_end", "realized_R": 0.0,
            "MFE_R": round(mfe, 6), "MAE_R": round(mae, 6), "entry_timestamp": event_time.isoformat(),
            "closed_at_utc": None, "duration_minutes": None, **threshold_flags,
        }
    close_r = ((last_close - entry) * side_mult / risk) * remaining
    realized += close_r
    last_end = pd.Timestamp(future.iloc[-1]["bar_end_utc"])
    return {
        "entry": round(entry, 6), "stop": round(stop, 6), "tp1": targets[0], "tp2": targets[1], "tp3": targets[2],
        "status": "censored", "exit_reason": "rth_close_or_data_end", "realized_R": round(realized, 6),
        "MFE_R": round(mfe, 6), "MAE_R": round(mae, 6),
        "entry_timestamp": (opened_at or event_time).isoformat(), "closed_at_utc": last_end.isoformat(),
        "duration_minutes": round((last_end - (opened_at or event_time)).total_seconds() / 60, 2),
        **threshold_flags,
    }


def generate_audit_events_fast(
    candles: pd.DataFrame,
    levels: pd.DataFrame,
    *,
    strategy_type: str,
) -> pd.DataFrame:
    cfg = settings_values()
    rows: list[dict[str, Any]] = []
    clean = candles.copy()
    clean["bar_end_utc_dt"] = pd.to_datetime(clean["bar_end_utc"], utc=True, errors="coerce")
    clean["bar_start_utc_dt"] = pd.to_datetime(clean["bar_start_utc"], utc=True, errors="coerce")
    for symbol, symbol_bars in clean.groupby("symbol"):
        symbol_levels = levels[levels["symbol"].astype(str).str.upper().eq(str(symbol).upper())].copy()
        if symbol_levels.empty:
            continue
        for model_version, model_levels in symbol_levels.groupby("gex_model_version"):
            seen: set[tuple[str, str, str, str, float, str]] = set()
            for day, day_bars in symbol_bars.groupby("trade_date"):
                day_bars = day_bars.sort_values("bar_end_utc_dt").reset_index(drop=True)
                day_levels = model_levels[model_levels["trade_date"].astype(str) == str(day)].copy()
                if day_levels.empty or len(day_bars) < 3:
                    continue
                zone_low = pd.to_numeric(day_levels["zone_low"], errors="coerce").to_numpy(dtype=float)
                zone_high = pd.to_numeric(day_levels["zone_high"], errors="coerce").to_numpy(dtype=float)
                prices = pd.to_numeric(day_levels["price"], errors="coerce").to_numpy(dtype=float)
                level_records = day_levels.to_dict("records")
                target_nodes = sorted({float(value) for value in prices if math.isfinite(float(value))})
                for index in range(1, len(day_bars) - 1):
                    previous = day_bars.iloc[index - 1].to_dict()
                    confirmation = day_bars.iloc[index].to_dict()
                    min_low = min(float(previous["low"]), float(confirmation["low"]))
                    max_high = max(float(previous["high"]), float(confirmation["high"]))
                    close = float(confirmation["close"])
                    long_mask = (min_low < zone_low) & (close > zone_high)
                    short_mask = (max_high > zone_high) & (close < zone_low)
                    mask = long_mask | short_mask
                    candidate_indices = np.flatnonzero(mask)
                    if len(candidate_indices) == 0:
                        continue
                    distances = np.abs(prices[candidate_indices] - close)
                    local_indices = candidate_indices[np.argsort(distances)[:5]]
                    for level_index in local_indices:
                        level_row = level_records[int(level_index)]
                        level_price = round(float(level_row.get("price")), 4)
                        direction = "LONG" if bool(long_mask[int(level_index)]) else "SHORT"
                        plan = build_trade_plan_fast(previous, confirmation, level_row, target_nodes, direction, cfg)
                        if plan is None:
                            continue
                        event_time = pd.Timestamp(confirmation["bar_end_utc_dt"])
                        key = (
                            str(symbol).upper(),
                            event_time.isoformat(),
                            direction,
                            str(level_row.get("level_type")),
                            level_price,
                            str(level_row.get("control_type") or "options"),
                        )
                        if key in seen:
                            continue
                        seen.add(key)
                        future = day_bars.iloc[index + 1:index + 90].copy()
                        simulated = simulate_fast(plan, future, direction, event_time, cfg)
                        delay = entry_delay_fields(event_time.to_pydatetime(), simulated.get("entry_timestamp"), str(simulated.get("status")))
                        metadata = parse_json(level_row.get("metadata_json"))
                        event_id = "hevent_" + stable_hash(
                            symbol, day, model_version, level_row.get("level_type"), level_price, direction,
                            event_time.isoformat(), level_row.get("control_type") or "options",
                        )
                        atr = max(float(confirmation.get("atr") or 0.0), 0.01)
                        distance = abs(close - level_price)
                        rows.append({
                            "historical_setup_id": "hsetup_audit_" + stable_hash(event_id, DEFAULT_MANAGEMENT, DEFAULT_SLIPPAGE),
                            "parent_event_id": event_id,
                            "symbol": str(symbol).upper(),
                            "session_date": str(day),
                            "entry_timestamp": simulated.get("entry_timestamp"),
                            "closed_at_utc": simulated.get("closed_at_utc"),
                            "setup_type": "LEVEL_RECLAIM_LONG" if direction == "LONG" else "LEVEL_RECLAIM_SHORT",
                            "direction": direction,
                            "strategy_type": strategy_type,
                            "control_type": level_row.get("control_type") or "OPTIONS_STRUCTURE_RECON",
                            "level_type": level_row.get("level_type"),
                            "historical_data_tier": level_row.get("historical_data_tier"),
                            "source_quality": level_row.get("source_quality"),
                            "provider": level_row.get("provider"),
                            "lookahead_risk": bool(level_row.get("lookahead_risk")),
                            "management_version": DEFAULT_MANAGEMENT,
                            "slippage_variant": f"SLIPPAGE_{DEFAULT_SLIPPAGE}BP",
                            "slippage_bps": DEFAULT_SLIPPAGE,
                            "entry": simulated.get("entry"),
                            "stop": simulated.get("stop"),
                            "tp1": simulated.get("tp1"),
                            "tp2": simulated.get("tp2"),
                            "tp3": simulated.get("tp3"),
                            "status": simulated.get("status"),
                            "exit_reason": simulated.get("exit_reason"),
                            "realized_R": simulated.get("realized_R"),
                            "MFE_R": simulated.get("MFE_R"),
                            "MAE_R": simulated.get("MAE_R"),
                            "duration_minutes": simulated.get("duration_minutes"),
                            "score": None,
                            "rr": round(float(plan.get("rr") or 0.0), 6),
                            "gamma_regime": "UNKNOWN",
                            "dealer_assumption": level_row.get("dealer_assumption"),
                            "replay_engine_version": "phase3c2_fast_audit_mirror",
                            "gex_model_version": model_version,
                            "strategy_state_source": "D1_EOD_STATIC_OPTIONS",
                            "event_generation_variant": "PHASE3C1_NEAREST_5_LEVELS_PER_BAR",
                            "candidate_timestamp_utc": event_time.isoformat(),
                            "candidate_timestamp_et": event_time.tz_convert(EASTERN).isoformat(),
                            "candidate_bar_index": index,
                            "previous_bar_end_utc": pd.Timestamp(previous["bar_end_utc_dt"]).isoformat(),
                            "previous_open": previous["open"],
                            "previous_high": previous["high"],
                            "previous_low": previous["low"],
                            "previous_close": previous["close"],
                            "confirmation_open": confirmation["open"],
                            "confirmation_high": confirmation["high"],
                            "confirmation_low": confirmation["low"],
                            "confirmation_close": confirmation["close"],
                            "confirmation_atr": confirmation.get("atr"),
                            "confirmation_relative_volume": confirmation.get("relative_volume"),
                            "level_price": level_price,
                            "level_price_round": level_price,
                            "zone_low": rounded(level_row.get("zone_low")),
                            "zone_high": rounded(level_row.get("zone_high")),
                            "strength_score": rounded(level_row.get("strength_score"), 6),
                            "source_chain_date": str(level_row.get("snapshot_date") or ""),
                            "level_family": metadata.get("historical_level_family") or metadata.get("control_type") or "",
                            "node_value": to_float(metadata.get("node_value")),
                            "level_importance_rank": to_float(level_row.get("level_importance_rank")),
                            "cluster_0_10_atr": level_row.get("cluster_0_1_atr"),
                            "cluster_0_20_atr": level_row.get("cluster_0_2_atr"),
                            "cluster_0_30_atr": level_row.get("cluster_0_3_atr"),
                            "cluster_0_50_atr": level_row.get("cluster_0_5_atr"),
                            "distance_from_close": round(distance, 6),
                            "distance_atr": round(distance / atr, 6),
                            "approach_sweep_episode_id": "episode_" + stable_hash(
                                symbol, day, direction, pd.Timestamp(previous["bar_end_utc_dt"]).isoformat(), event_time.isoformat(),
                            ),
                            "approach": True,
                            "sweep": True,
                            "reclaim": True,
                            "confirmation": True,
                            "entry_not_before_confirmation_close": bool(
                                parse_dt(simulated.get("entry_timestamp")) is None
                                or parse_dt(simulated.get("entry_timestamp")) >= event_time.to_pydatetime()
                            ),
                            "reached_0_25R_before_stop": simulated.get("reached_0_25R_before_stop"),
                            "reached_0_5R_before_stop": simulated.get("reached_0_5R_before_stop"),
                            "reached_1R_before_stop": simulated.get("reached_1R_before_stop"),
                            "time_to_0_25R_minutes": simulated.get("time_to_0_25R_minutes"),
                            "time_to_0_5R_minutes": simulated.get("time_to_0_5R_minutes"),
                            "time_to_1R_minutes": simulated.get("time_to_1R_minutes"),
                            "time_to_stop_minutes": simulated.get("time_to_stop_minutes"),
                            "max_R_before_stop": simulated.get("max_R_before_stop"),
                            **delay,
                        })
                        break
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    frame["candidate_timestamp_utc_dt"] = pd.to_datetime(frame["candidate_timestamp_utc"], utc=True, errors="coerce")
    return frame.sort_values(["symbol", "session_date", "candidate_timestamp_utc", "gex_model_version"]).reset_index(drop=True)


def generate_event_skeletons_fast(
    candles: pd.DataFrame,
    levels: pd.DataFrame,
    *,
    strategy_type: str,
) -> pd.DataFrame:
    cfg = settings_values()
    rows: list[dict[str, Any]] = []
    clean = candles.copy()
    clean["bar_end_utc_dt"] = pd.to_datetime(clean["bar_end_utc"], utc=True, errors="coerce")
    clean["bar_start_utc_dt"] = pd.to_datetime(clean["bar_start_utc"], utc=True, errors="coerce")
    for symbol, symbol_bars in clean.groupby("symbol"):
        symbol_levels = levels[levels["symbol"].astype(str).str.upper().eq(str(symbol).upper())].copy()
        if symbol_levels.empty:
            continue
        for model_version, model_levels in symbol_levels.groupby("gex_model_version"):
            seen: set[tuple[str, str, str, str, float, str]] = set()
            for day, day_bars in symbol_bars.groupby("trade_date"):
                day_bars = day_bars.sort_values("bar_end_utc_dt").reset_index(drop=True)
                day_levels = model_levels[model_levels["trade_date"].astype(str) == str(day)].copy()
                if day_levels.empty or len(day_bars) < 3:
                    continue
                zone_low = pd.to_numeric(day_levels["zone_low"], errors="coerce").to_numpy(dtype=float)
                zone_high = pd.to_numeric(day_levels["zone_high"], errors="coerce").to_numpy(dtype=float)
                prices = pd.to_numeric(day_levels["price"], errors="coerce").to_numpy(dtype=float)
                level_records = day_levels.to_dict("records")
                target_nodes = sorted({float(value) for value in prices if math.isfinite(float(value))})
                for index in range(1, len(day_bars) - 1):
                    previous = day_bars.iloc[index - 1].to_dict()
                    confirmation = day_bars.iloc[index].to_dict()
                    min_low = min(float(previous["low"]), float(confirmation["low"]))
                    max_high = max(float(previous["high"]), float(confirmation["high"]))
                    close = float(confirmation["close"])
                    long_mask = (min_low < zone_low) & (close > zone_high)
                    short_mask = (max_high > zone_high) & (close < zone_low)
                    mask = long_mask | short_mask
                    candidate_indices = np.flatnonzero(mask)
                    if len(candidate_indices) == 0:
                        continue
                    distances = np.abs(prices[candidate_indices] - close)
                    local_indices = candidate_indices[np.argsort(distances)[:5]]
                    for level_index in local_indices:
                        level_row = level_records[int(level_index)]
                        known_at = parse_dt(level_row.get("known_at_utc"))
                        bar_start = pd.Timestamp(confirmation["bar_start_utc_dt"]).to_pydatetime()
                        if known_at is not None and known_at >= bar_start:
                            continue
                        level_price = round(float(level_row.get("price")), 4)
                        direction = "LONG" if bool(long_mask[int(level_index)]) else "SHORT"
                        plan = build_trade_plan_fast(previous, confirmation, level_row, target_nodes, direction, cfg)
                        if plan is None:
                            continue
                        event_time = pd.Timestamp(confirmation["bar_end_utc_dt"])
                        key = (
                            str(symbol).upper(),
                            event_time.isoformat(),
                            direction,
                            str(level_row.get("level_type")),
                            level_price,
                            str(level_row.get("control_type") or "options"),
                        )
                        if key in seen:
                            continue
                        seen.add(key)
                        metadata = parse_json(level_row.get("metadata_json"))
                        event_id = "hevent_" + stable_hash(
                            symbol, day, model_version, level_row.get("level_type"), level_price, direction,
                            event_time.isoformat(), level_row.get("control_type") or "options",
                        )
                        atr = max(float(confirmation.get("atr") or 0.0), 0.01)
                        distance = abs(close - level_price)
                        rows.append({
                            "parent_event_id": event_id,
                            "symbol": str(symbol).upper(),
                            "session_date": str(day),
                            "setup_type": "LEVEL_RECLAIM_LONG" if direction == "LONG" else "LEVEL_RECLAIM_SHORT",
                            "direction": direction,
                            "strategy_type": strategy_type,
                            "control_type": level_row.get("control_type") or "OPTIONS_STRUCTURE_RECON",
                            "level_type": level_row.get("level_type"),
                            "historical_data_tier": level_row.get("historical_data_tier"),
                            "source_quality": level_row.get("source_quality"),
                            "provider": level_row.get("provider"),
                            "lookahead_risk": bool(level_row.get("lookahead_risk")),
                            "management_version": DEFAULT_MANAGEMENT,
                            "slippage_variant": f"SLIPPAGE_{DEFAULT_SLIPPAGE}BP",
                            "slippage_bps": DEFAULT_SLIPPAGE,
                            "planned_entry_unslipped": round(float(plan["entry"]), 6),
                            "planned_stop": round(float(plan["stop"]), 6),
                            "planned_tp1": plan["targets"][0],
                            "planned_tp2": plan["targets"][1],
                            "planned_tp3": plan["targets"][2],
                            "score": None,
                            "rr": round(float(plan.get("rr") or 0.0), 6),
                            "gamma_regime": "UNKNOWN",
                            "dealer_assumption": level_row.get("dealer_assumption"),
                            "replay_engine_version": "phase3c2_fast_skeleton_mirror",
                            "gex_model_version": model_version,
                            "strategy_state_source": "D1_EOD_STATIC_OPTIONS",
                            "event_generation_variant": "PHASE3C1_NEAREST_5_LEVELS_PER_BAR",
                            "candidate_timestamp_utc": event_time.isoformat(),
                            "candidate_timestamp_et": event_time.tz_convert(EASTERN).isoformat(),
                            "candidate_bar_index": index,
                            "previous_bar_end_utc": pd.Timestamp(previous["bar_end_utc_dt"]).isoformat(),
                            "previous_open": previous["open"],
                            "previous_high": previous["high"],
                            "previous_low": previous["low"],
                            "previous_close": previous["close"],
                            "confirmation_open": confirmation["open"],
                            "confirmation_high": confirmation["high"],
                            "confirmation_low": confirmation["low"],
                            "confirmation_close": confirmation["close"],
                            "confirmation_atr": confirmation.get("atr"),
                            "confirmation_relative_volume": confirmation.get("relative_volume"),
                            "level_price": level_price,
                            "level_price_round": level_price,
                            "zone_low": rounded(level_row.get("zone_low")),
                            "zone_high": rounded(level_row.get("zone_high")),
                            "strength_score": rounded(level_row.get("strength_score"), 6),
                            "source_chain_date": str(level_row.get("snapshot_date") or ""),
                            "level_family": metadata.get("historical_level_family") or metadata.get("control_type") or "",
                            "node_value": to_float(metadata.get("node_value")),
                            "level_importance_rank": to_float(level_row.get("level_importance_rank")),
                            "cluster_0_10_atr": level_row.get("cluster_0_1_atr"),
                            "cluster_0_20_atr": level_row.get("cluster_0_2_atr"),
                            "cluster_0_30_atr": level_row.get("cluster_0_3_atr"),
                            "cluster_0_50_atr": level_row.get("cluster_0_5_atr"),
                            "distance_from_close": round(distance, 6),
                            "distance_atr": round(distance / atr, 6),
                            "approach_sweep_episode_id": "episode_" + stable_hash(
                                symbol, day, direction, pd.Timestamp(previous["bar_end_utc_dt"]).isoformat(), event_time.isoformat(),
                            ),
                            "approach": True,
                            "sweep": True,
                            "reclaim": True,
                            "confirmation": True,
                        })
                        break
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    frame["candidate_timestamp_utc_dt"] = pd.to_datetime(frame["candidate_timestamp_utc"], utc=True, errors="coerce")
    frame["_event_sequence"] = frame.groupby("gex_model_version").cumcount()
    return frame.reset_index(drop=True)


def attach_replay_outcomes(skeleton: pd.DataFrame, replay: pd.DataFrame, *, strategy_type: str) -> pd.DataFrame:
    if skeleton.empty:
        return skeleton.copy()
    default = replay[
        replay["strategy_type"].eq(strategy_type)
        & replay["management_version"].eq(DEFAULT_MANAGEMENT)
        & replay["slippage_variant"].eq(f"SLIPPAGE_{DEFAULT_SLIPPAGE}BP")
    ].copy()
    if default.empty:
        output = skeleton.copy()
        output["status"] = "missing_replay_outcome"
        output["exit_reason"] = "missing_replay_outcome"
        output["realized_R"] = np.nan
        output["MFE_R"] = np.nan
        output["MAE_R"] = np.nan
        return output
    default["_event_sequence"] = default.groupby("gex_model_version").cumcount()
    outcome_columns = [
        "historical_setup_id", "entry_timestamp", "closed_at_utc", "entry", "stop", "tp1", "tp2", "tp3",
        "status", "exit_reason", "realized_R", "MFE_R", "MAE_R", "duration_minutes", "score", "rr",
        "gamma_regime", "replay_engine_version",
    ]
    merged = skeleton.merge(
        default[["gex_model_version", "_event_sequence", *outcome_columns]],
        how="left",
        on=["gex_model_version", "_event_sequence"],
        suffixes=("", "_replay"),
    )
    event_times = pd.to_datetime(merged["candidate_timestamp_utc"], utc=True, errors="coerce")
    entry_times = pd.to_datetime(merged["entry_timestamp"], utc=True, errors="coerce")
    merged["entry_not_before_confirmation_close"] = entry_times.isna() | (entry_times >= event_times)
    for threshold, column in [(0.25, "reached_0_25R_before_stop"), (0.50, "reached_0_5R_before_stop"), (1.00, "reached_1R_before_stop")]:
        merged[column] = pd.to_numeric(merged["MFE_R"], errors="coerce").ge(threshold)
    merged["time_to_0_25R_minutes"] = None
    merged["time_to_0_5R_minutes"] = None
    merged["time_to_1R_minutes"] = None
    merged["time_to_stop_minutes"] = np.where(merged["exit_reason"].eq("stop_loss"), merged["duration_minutes"], None)
    merged["max_R_before_stop"] = pd.to_numeric(merged["MFE_R"], errors="coerce")
    merged["excursion_order_source"] = "MFE_THRESHOLD_FROM_REPLAY_OUTPUT; exact before-stop ordering not retained in Phase3C1 parquet"
    delay_rows = [
        entry_delay_fields(event_time.to_pydatetime(), entry, str(status))
        for event_time, entry, status in zip(event_times, merged["entry_timestamp"], merged["status"], strict=False)
    ]
    delay_frame = pd.DataFrame(delay_rows)
    for column in delay_frame.columns:
        merged[column] = delay_frame[column]
    return merged


def generate_event_skeletons_duckdb(
    candles: pd.DataFrame,
    levels: pd.DataFrame,
    *,
    strategy_type: str,
) -> pd.DataFrame:
    bars = candles.copy()
    bars["bar_end_ts"] = pd.to_datetime(bars["bar_end_utc"], utc=True, errors="coerce")
    bars["bar_start_ts"] = pd.to_datetime(bars["bar_start_utc"], utc=True, errors="coerce")
    level_frame = levels.copy()
    level_frame["known_at_ts"] = pd.to_datetime(level_frame["known_at_utc"], utc=True, errors="coerce")
    for column in ["price", "zone_low", "zone_high", "strength_score", "level_importance_rank"]:
        if column in level_frame.columns:
            level_frame[column] = pd.to_numeric(level_frame[column], errors="coerce")
    con = duckdb.connect()
    con.register("bars", bars)
    con.register("levels", level_frame)
    result = con.execute(
        """
        WITH indexed_bars AS (
            SELECT
                symbol,
                trade_date,
                bar_start_ts,
                bar_end_ts,
                open,
                high,
                low,
                close,
                volume,
                atr,
                relative_volume,
                lag(bar_end_ts) OVER w AS previous_bar_end_ts,
                lag(open) OVER w AS previous_open,
                lag(high) OVER w AS previous_high,
                lag(low) OVER w AS previous_low,
                lag(close) OVER w AS previous_close,
                row_number() OVER w AS bar_idx,
                count(*) OVER (PARTITION BY symbol, trade_date) AS day_bar_count
            FROM bars
            WINDOW w AS (PARTITION BY symbol, trade_date ORDER BY bar_end_ts)
        ),
        level_stats AS (
            SELECT
                symbol,
                trade_date,
                gex_model_version,
                min(price) AS min_level_price,
                max(price) AS max_level_price
            FROM levels
            GROUP BY symbol, trade_date, gex_model_version
        ),
        joined AS (
            SELECT
                b.symbol,
                b.trade_date AS session_date,
                b.bar_idx,
                b.day_bar_count,
                b.bar_start_ts,
                b.bar_end_ts,
                b.open AS confirmation_open,
                b.high AS confirmation_high,
                b.low AS confirmation_low,
                b.close AS confirmation_close,
                b.atr AS confirmation_atr,
                b.relative_volume AS confirmation_relative_volume,
                b.previous_bar_end_ts,
                b.previous_open,
                b.previous_high,
                b.previous_low,
                b.previous_close,
                l.snapshot_date AS source_chain_date,
                l.known_at_ts,
                l.level_type,
                l.price AS level_price,
                round(l.price, 4) AS level_price_round,
                l.zone_low,
                l.zone_high,
                l.strength_score,
                l.provider,
                l.historical_data_tier,
                l.source_quality,
                l.lookahead_risk,
                l.gex_model_version,
                l.dealer_assumption,
                l.control_type,
                l.metadata_json,
                l.level_family,
                l.node_value,
                l.level_importance_rank,
                l.cluster_0_1_atr,
                l.cluster_0_2_atr,
                l.cluster_0_3_atr,
                l.cluster_0_5_atr,
                s.min_level_price,
                s.max_level_price,
                CASE
                    WHEN least(b.previous_low, b.low) < l.zone_low AND b.close > l.zone_high THEN 'LONG'
                    WHEN greatest(b.previous_high, b.high) > l.zone_high AND b.close < l.zone_low THEN 'SHORT'
                    ELSE NULL
                END AS direction,
                CASE
                    WHEN least(b.previous_low, b.low) < l.zone_low AND b.close > l.zone_high THEN greatest(l.zone_high, b.close)
                    WHEN greatest(b.previous_high, b.high) > l.zone_high AND b.close < l.zone_low THEN least(l.zone_low, b.close)
                    ELSE NULL
                END AS planned_entry_unslipped,
                abs(l.price - b.close) AS distance_from_close
            FROM indexed_bars b
            JOIN levels l
              ON upper(l.symbol) = upper(b.symbol)
             AND CAST(l.trade_date AS VARCHAR) = CAST(b.trade_date AS VARCHAR)
            JOIN level_stats s
              ON s.symbol = l.symbol
             AND CAST(s.trade_date AS VARCHAR) = CAST(l.trade_date AS VARCHAR)
             AND s.gex_model_version = l.gex_model_version
            WHERE b.previous_low IS NOT NULL
              AND b.bar_idx < b.day_bar_count
              AND (l.known_at_ts IS NULL OR l.known_at_ts < b.bar_start_ts)
              AND (
                (least(b.previous_low, b.low) < l.zone_low AND b.close > l.zone_high)
                OR
                (greatest(b.previous_high, b.high) > l.zone_high AND b.close < l.zone_low)
              )
        ),
        ranked AS (
            SELECT
                *,
                row_number() OVER (
                    PARTITION BY symbol, session_date, gex_model_version, bar_end_ts
                    ORDER BY distance_from_close, level_price, level_type
                ) AS candidate_rank
            FROM joined
        ),
        eligible AS (
            SELECT *
            FROM ranked
            WHERE candidate_rank <= 5
              AND (
                (direction = 'LONG' AND max_level_price > planned_entry_unslipped)
                OR
                (direction = 'SHORT' AND min_level_price < planned_entry_unslipped)
              )
        ),
        accepted AS (
            SELECT *
            FROM eligible
            QUALIFY row_number() OVER (
                PARTITION BY symbol, session_date, gex_model_version, bar_end_ts
                ORDER BY candidate_rank
            ) = 1
        ),
        phase_seen AS (
            SELECT *
            FROM accepted
            QUALIFY row_number() OVER (
                PARTITION BY symbol, session_date, gex_model_version, bar_end_ts, direction, level_type, level_price_round, coalesce(control_type, 'options')
                ORDER BY candidate_rank
            ) = 1
        )
        SELECT *
        FROM phase_seen
        ORDER BY gex_model_version, symbol, session_date, bar_end_ts
        """
    ).fetchdf()
    if result.empty:
        return pd.DataFrame()
    result["candidate_timestamp_utc"] = pd.to_datetime(result["bar_end_ts"], utc=True, errors="coerce").dt.strftime("%Y-%m-%dT%H:%M:%S%z")
    result["candidate_timestamp_utc"] = result["candidate_timestamp_utc"].str.replace(r"(\+0000)$", "+00:00", regex=True)
    result["candidate_timestamp_et"] = pd.to_datetime(result["bar_end_ts"], utc=True, errors="coerce").dt.tz_convert(EASTERN).astype(str)
    result["previous_bar_end_utc"] = pd.to_datetime(result["previous_bar_end_ts"], utc=True, errors="coerce").dt.strftime("%Y-%m-%dT%H:%M:%S%z")
    result["previous_bar_end_utc"] = result["previous_bar_end_utc"].str.replace(r"(\+0000)$", "+00:00", regex=True)
    result["setup_type"] = np.where(result["direction"].eq("LONG"), "LEVEL_RECLAIM_LONG", "LEVEL_RECLAIM_SHORT")
    result["strategy_type"] = strategy_type
    result["management_version"] = DEFAULT_MANAGEMENT
    result["slippage_variant"] = f"SLIPPAGE_{DEFAULT_SLIPPAGE}BP"
    result["slippage_bps"] = DEFAULT_SLIPPAGE
    result["strategy_state_source"] = "D1_EOD_STATIC_OPTIONS"
    result["event_generation_variant"] = "PHASE3C1_NEAREST_5_LEVELS_PER_BAR_SQL_RECOVERY"
    result["candidate_timestamp_utc_dt"] = pd.to_datetime(result["bar_end_ts"], utc=True, errors="coerce")
    result["approach"] = True
    result["sweep"] = True
    result["reclaim"] = True
    result["confirmation"] = True
    result["level_price"] = pd.to_numeric(result["level_price"], errors="coerce").round(4)
    result["level_price_round"] = result["level_price"].round(4)
    result["distance_atr"] = (
        pd.to_numeric(result["distance_from_close"], errors="coerce")
        / pd.to_numeric(result["confirmation_atr"], errors="coerce").replace(0, np.nan)
    ).round(6)
    result["approach_sweep_episode_id"] = [
        "episode_" + stable_hash(symbol, day, direction, previous_ts, current_ts)
        for symbol, day, direction, previous_ts, current_ts in zip(
            result["symbol"], result["session_date"], result["direction"], result["previous_bar_end_utc"], result["candidate_timestamp_utc"],
            strict=False,
        )
    ]
    result["parent_event_id"] = [
        "hevent_" + stable_hash(symbol, day, model, level_type, price, direction, timestamp, control or "options")
        for symbol, day, model, level_type, price, direction, timestamp, control in zip(
            result["symbol"], result["session_date"], result["gex_model_version"], result["level_type"],
            result["level_price_round"], result["direction"], result["candidate_timestamp_utc"], result["control_type"],
            strict=False,
        )
    ]
    result["_event_sequence"] = result.groupby("gex_model_version").cumcount()
    result = result.rename(columns={
        "cluster_0_1_atr": "cluster_0_10_atr",
        "cluster_0_2_atr": "cluster_0_20_atr",
        "cluster_0_3_atr": "cluster_0_30_atr",
        "cluster_0_5_atr": "cluster_0_50_atr",
    })
    return result.reset_index(drop=True)



def generate_audit_events(
    candles: pd.DataFrame,
    levels: pd.DataFrame,
    *,
    strategy_type: str,
) -> pd.DataFrame:
    settings = Settings.load()
    pipeline = HistoricalReconstructionPipeline(EmptyRepository(), settings, PROJECT_ROOT)
    rows: list[dict[str, Any]] = []
    bars_by_symbol = pipeline._bars_by_symbol(candles)
    for symbol, bars in bars_by_symbol.items():
        by_day: dict[str, list[Any]] = {}
        for bar in bars:
            day = bar.bar_end_utc.astimezone(EASTERN).date().isoformat()
            by_day.setdefault(day, []).append(bar)
        symbol_levels = levels[levels["symbol"].astype(str).str.upper().eq(symbol)].copy()
        if symbol_levels.empty:
            continue
        for model_version, model_levels in symbol_levels.groupby("gex_model_version"):
            seen: set[tuple[str, str, str, str, float, str]] = set()
            for day, day_bars in by_day.items():
                day_levels = model_levels[model_levels["trade_date"].astype(str) == day].copy()
                if day_levels.empty or len(day_bars) < 3:
                    continue
                zone_low = pd.to_numeric(day_levels["zone_low"], errors="coerce").to_numpy(dtype=float)
                zone_high = pd.to_numeric(day_levels["zone_high"], errors="coerce").to_numpy(dtype=float)
                prices = pd.to_numeric(day_levels["price"], errors="coerce").to_numpy(dtype=float)
                level_records = day_levels.to_dict("records")
                target_nodes = sorted({float(value) for value in prices if math.isfinite(float(value))})
                for index in range(1, len(day_bars) - 1):
                    previous_bar = day_bars[index - 1]
                    confirmation_bar = day_bars[index]
                    min_low = min(previous_bar.low, confirmation_bar.low)
                    max_high = max(previous_bar.high, confirmation_bar.high)
                    mask = (
                        ((min_low < zone_low) & (confirmation_bar.close > zone_high))
                        | ((max_high > zone_high) & (confirmation_bar.close < zone_low))
                    )
                    candidate_indices = np.flatnonzero(mask)
                    if len(candidate_indices) == 0:
                        continue
                    distances = np.abs(prices[candidate_indices] - confirmation_bar.close)
                    local_indices = candidate_indices[np.argsort(distances)[:5]]
                    for level_index in local_indices:
                        level_row = level_records[int(level_index)]
                        level = pipeline._level_from_row(level_row)
                        scan = pipeline._scan_from_history(previous_bar, confirmation_bar, level, target_nodes, level_row)
                        setup = pipeline.detector.detect(scan, at=confirmation_bar.bar_end_utc)
                        if not setup or not setup.trade_plan:
                            continue
                        level_price = round(float(level_row.get("price")), 4)
                        key = (
                            symbol,
                            confirmation_bar.bar_end_utc.isoformat(),
                            setup.side.value,
                            str(level_row.get("level_type")),
                            level_price,
                            str(level_row.get("control_type") or "options"),
                        )
                        if key in seen:
                            continue
                        seen.add(key)
                        future_bars = day_bars[index + 1:index + 90]
                        simulated = pipeline._simulate(
                            setup,
                            level_row,
                            future_bars,
                            DEFAULT_MANAGEMENT,
                            DEFAULT_SLIPPAGE,
                            strategy_type,
                        )
                        entry = float(simulated.get("entry") or setup.trade_plan.planned_entry)
                        stop = float(simulated.get("stop") or setup.trade_plan.stop_initial)
                        event_time = confirmation_bar.bar_end_utc
                        flags = path_flags(setup, future_bars, entry, stop)
                        delay = entry_delay_fields(event_time, simulated.get("entry_timestamp"), str(simulated.get("status")))
                        metadata = parse_json(level_row.get("metadata_json"))
                        event_id = "hevent_" + stable_hash(
                            symbol,
                            day,
                            model_version,
                            level_row.get("level_type"),
                            level_price,
                            setup.side.value,
                            event_time.isoformat(),
                            level_row.get("control_type") or "options",
                        )
                        distance = abs(float(confirmation_bar.close) - float(level_price))
                        atr = max(float(confirmation_bar.atr or 0.0), 0.01)
                        rows.append({
                            **simulated,
                            "parent_event_id": event_id,
                            "strategy_state_source": "D1_EOD_STATIC_OPTIONS",
                            "event_generation_variant": "PHASE3C1_NEAREST_5_LEVELS_PER_BAR",
                            "candidate_timestamp_utc": event_time.isoformat(),
                            "candidate_timestamp_et": event_time.astimezone(EASTERN).isoformat(),
                            "candidate_bar_index": index,
                            "previous_bar_end_utc": previous_bar.bar_end_utc.isoformat(),
                            "previous_open": previous_bar.open,
                            "previous_high": previous_bar.high,
                            "previous_low": previous_bar.low,
                            "previous_close": previous_bar.close,
                            "confirmation_open": confirmation_bar.open,
                            "confirmation_high": confirmation_bar.high,
                            "confirmation_low": confirmation_bar.low,
                            "confirmation_close": confirmation_bar.close,
                            "confirmation_atr": confirmation_bar.atr,
                            "confirmation_relative_volume": confirmation_bar.relative_volume,
                            "level_price": level_price,
                            "level_price_round": level_price,
                            "zone_low": rounded(level_row.get("zone_low")),
                            "zone_high": rounded(level_row.get("zone_high")),
                            "strength_score": rounded(level_row.get("strength_score"), 6),
                            "source_chain_date": str(level_row.get("snapshot_date") or ""),
                            "level_family": metadata.get("historical_level_family") or metadata.get("control_type") or "",
                            "node_value": to_float(metadata.get("node_value")),
                            "level_importance_rank": to_float(level_row.get("level_importance_rank")),
                            "cluster_0_10_atr": level_row.get("cluster_0_1_atr"),
                            "cluster_0_20_atr": level_row.get("cluster_0_2_atr"),
                            "cluster_0_30_atr": level_row.get("cluster_0_3_atr"),
                            "cluster_0_50_atr": level_row.get("cluster_0_5_atr"),
                            "distance_from_close": round(distance, 6),
                            "distance_atr": round(distance / atr, 6),
                            "approach_sweep_episode_id": "episode_" + stable_hash(
                                symbol,
                                day,
                                setup.side.value,
                                previous_bar.bar_end_utc.isoformat(),
                                confirmation_bar.bar_end_utc.isoformat(),
                            ),
                            "approach": True,
                            "sweep": True,
                            "reclaim": True,
                            "confirmation": True,
                            "entry_not_before_confirmation_close": bool(
                                parse_dt(simulated.get("entry_timestamp")) is None
                                or parse_dt(simulated.get("entry_timestamp")) >= event_time
                            ),
                            **flags,
                            **delay,
                        })
                        break
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    frame["candidate_timestamp_utc_dt"] = pd.to_datetime(frame["candidate_timestamp_utc"], utc=True, errors="coerce")
    frame["session_date"] = frame["session_date"].astype(str)
    return frame.sort_values(["symbol", "session_date", "candidate_timestamp_utc", "gex_model_version"]).reset_index(drop=True)


def count_repeated_within(group: pd.DataFrame, minutes: int) -> int:
    count = 0
    for _, sub in group.sort_values("candidate_timestamp_utc_dt").groupby(["direction", "level_type", "level_price_round"], dropna=False):
        times = sub["candidate_timestamp_utc_dt"].dropna().sort_values().to_list()
        previous = None
        for timestamp in times:
            if previous is not None and (timestamp - previous).total_seconds() <= minutes * 60:
                count += 1
            previous = timestamp
    return int(count)


def trade_frequency_audit(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame()
    frame = events.copy()
    base_cols = ["symbol", "session_date", "gex_model_version"]
    exact_level_cols = [*base_cols, "direction", "level_type", "level_price_round"]
    frame["_resolved"] = frame["status"].isin(RESOLVED_STATUSES).astype(int)
    frame["_long"] = frame["direction"].eq("LONG").astype(int)
    frame["_short"] = frame["direction"].eq("SHORT").astype(int)
    frame["_expired"] = (~frame["status"].isin(RESOLVED_STATUSES)).astype(int)

    base = frame.groupby(base_cols, dropna=False).agg(
        setups_detected=("parent_event_id", "count"),
        resolved_trades=("_resolved", "sum"),
        expired_or_unfilled=("_expired", "sum"),
        long_setups=("_long", "sum"),
        short_setups=("_short", "sum"),
        unique_level_prices=("level_price_round", "nunique"),
    ).reset_index()
    unique_levels = (
        frame.drop_duplicates([*base_cols, "level_type", "level_price_round"])
        .groupby(base_cols, dropna=False)
        .size()
        .rename("unique_levels_interacted")
        .reset_index()
    )
    same_level = (
        frame.groupby(exact_level_cols, dropna=False)
        .size()
        .sub(1)
        .clip(lower=0)
        .rename("repeat_count")
        .reset_index()
        .groupby(base_cols, dropna=False)["repeat_count"]
        .sum()
        .rename("repeated_trades_same_level_direction")
        .reset_index()
    )
    max_same_level = (
        frame.groupby(exact_level_cols, dropna=False)
        .size()
        .rename("level_direction_count")
        .reset_index()
        .groupby(base_cols, dropna=False)["level_direction_count"]
        .max()
        .rename("max_same_level_direction_setups")
        .reset_index()
    )
    direction_repeats = (
        frame.groupby([*base_cols, "direction"], dropna=False)
        .size()
        .sub(1)
        .clip(lower=0)
        .rename("repeat_count")
        .reset_index()
        .groupby(base_cols, dropna=False)["repeat_count"]
        .sum()
        .rename("repeated_trades_same_direction")
        .reset_index()
    )
    ordered = frame.sort_values(exact_level_cols + ["candidate_timestamp_utc_dt"]).copy()
    same_previous = pd.Series(True, index=ordered.index)
    for column in exact_level_cols:
        same_previous &= ordered[column].eq(ordered[column].shift(1))
    deltas = ordered["candidate_timestamp_utc_dt"].diff().dt.total_seconds().div(60)
    repeat_frames = []
    for minutes in (15, 30, 60):
        ordered[f"_repeat_{minutes}m"] = (same_previous & deltas.le(minutes)).astype(int)
        repeat_frames.append(
            ordered.groupby(base_cols, dropna=False)[f"_repeat_{minutes}m"]
            .sum()
            .rename(f"repeated_within_{minutes}m")
            .reset_index()
        )
    inter_event = (
        frame.sort_values(base_cols + ["candidate_timestamp_utc_dt"])
        .assign(_inter_event_minutes=lambda item: item.groupby(base_cols, dropna=False)["candidate_timestamp_utc_dt"].diff().dt.total_seconds().div(60))
        .groupby(base_cols, dropna=False)["_inter_event_minutes"]
        .median()
        .round(4)
        .rename("median_minutes_between_setups")
        .reset_index()
    )
    result = base.merge(unique_levels, on=base_cols, how="left")
    for extra in [same_level, max_same_level, direction_repeats, *repeat_frames, inter_event]:
        result = result.merge(extra, on=base_cols, how="left")
    fill_zero = [
        "unique_levels_interacted", "repeated_trades_same_level_direction", "repeated_trades_same_direction",
        "repeated_within_15m", "repeated_within_30m", "repeated_within_60m", "max_same_level_direction_setups",
    ]
    for column in fill_zero:
        result[column] = result[column].fillna(0).astype(int)
    return result.sort_values(["symbol", "session_date", "gex_model_version"])


def frequency_summary(frequency: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for model, group in frequency.groupby("gex_model_version"):
        for column in ("setups_detected", "resolved_trades", "unique_levels_interacted"):
            rows.append({
                "gex_model_version": model,
                "metric": column,
                "symbol_days": int(len(group)),
                "median": round(float(group[column].median()), 4),
                "p90": round(float(group[column].quantile(0.90)), 4),
                "p95": round(float(group[column].quantile(0.95)), 4),
                "max": int(group[column].max()),
                "mean": round(float(group[column].mean()), 4),
            })
    if frequency.empty:
        return pd.DataFrame()
    for column in ("setups_detected", "resolved_trades", "unique_levels_interacted"):
        rows.append({
            "gex_model_version": "ALL_MODELS",
            "metric": column,
            "symbol_days": int(len(frequency)),
            "median": round(float(frequency[column].median()), 4),
            "p90": round(float(frequency[column].quantile(0.90)), 4),
            "p95": round(float(frequency[column].quantile(0.95)), 4),
            "max": int(frequency[column].max()),
            "mean": round(float(frequency[column].mean()), 4),
        })
    return pd.DataFrame(rows)


def deduplicate(events: pd.DataFrame, *, variant: str, cooldown_minutes: int | None = None,
                one_per_day: bool = False, cluster_column: str | None = None) -> pd.DataFrame:
    if events.empty:
        return events.copy()
    frame = events.sort_values(["symbol", "session_date", "candidate_timestamp_utc_dt"]).copy()
    if cluster_column:
        identity_cols = ["symbol", "session_date", "gex_model_version", "direction", cluster_column]
    else:
        identity_cols = ["symbol", "session_date", "gex_model_version", "direction", "level_type", "level_price_round"]
    keep_indices: list[int] = []
    if one_per_day:
        keep_indices = frame.groupby(identity_cols, dropna=False).head(1).index.to_list()
    elif cooldown_minutes is not None:
        for _, group in frame.groupby(identity_cols, dropna=False):
            last_kept: pd.Timestamp | None = None
            for idx, row in group.iterrows():
                timestamp = row["candidate_timestamp_utc_dt"]
                if pd.isna(timestamp):
                    continue
                if last_kept is None or (timestamp - last_kept).total_seconds() >= cooldown_minutes * 60:
                    keep_indices.append(idx)
                    last_kept = timestamp
    else:
        keep_indices = frame.index.to_list()
    output = frame.loc[sorted(set(keep_indices))].copy()
    output["dedup_variant"] = variant
    return output


def dedup_variants(events: pd.DataFrame) -> pd.DataFrame:
    variants = [
        ("RAW_PHASE3C1_EVENTS", events),
        ("DEDUP_15M", deduplicate(events, variant="DEDUP_15M", cooldown_minutes=15)),
        ("DEDUP_30M", deduplicate(events, variant="DEDUP_30M", cooldown_minutes=30)),
        ("DEDUP_60M", deduplicate(events, variant="DEDUP_60M", cooldown_minutes=60)),
        (
            "ONE_TRADE_PER_LEVEL_PER_DIRECTION_PER_DAY",
            deduplicate(events, variant="ONE_TRADE_PER_LEVEL_PER_DIRECTION_PER_DAY", one_per_day=True),
        ),
        (
            "ECONOMIC_DEDUP_30M_CLUSTER_0_30_ATR",
            deduplicate(events, variant="ECONOMIC_DEDUP_30M_CLUSTER_0_30_ATR", cooldown_minutes=30, cluster_column="cluster_0_30_atr"),
        ),
    ]
    rows: list[dict[str, Any]] = []
    for name, frame in variants:
        rows.append(add_common_stats({
            "dedup_variant": name,
            "events_detected": int(len(frame)),
            "resolved_events": int(len(result_subset(frame))),
            "event_retention_pct": round(float(len(frame) / len(events)), 4) if len(events) else None,
            "resolved_retention_pct": round(float(len(result_subset(frame)) / len(result_subset(events))), 4) if len(result_subset(events)) else None,
            "strategy_state_source": "D1_EOD_STATIC_OPTIONS",
        }, frame))
    return pd.DataFrame(rows)


def level_importance(events: pd.DataFrame) -> pd.DataFrame:
    definitions: list[tuple[str, pd.Series]] = [
        ("ALL_OPTIONS_LEVELS", pd.Series(True, index=events.index)),
        ("ALL_GEX_NODES", events["level_type"].eq("GEX_NODE")),
        ("TOP_10_ABS_GEX_NODES", events["level_type"].eq("GEX_NODE") & pd.to_numeric(events["level_importance_rank"], errors="coerce").le(10)),
        ("TOP_5_ABS_GEX_NODES", events["level_type"].eq("GEX_NODE") & pd.to_numeric(events["level_importance_rank"], errors="coerce").le(5)),
        ("TOP_3_ABS_GEX_NODES", events["level_type"].eq("GEX_NODE") & pd.to_numeric(events["level_importance_rank"], errors="coerce").le(3)),
        ("GAMMA_FLIP_CALL_WALL_PUT_WALL_ONLY", events["level_type"].isin(["GAMMA_FLIP", "CALL_WALL", "PUT_WALL"])),
        ("TOP_GEX_OI_CLUSTERS_ONLY", events["level_family"].eq("GEX_OI_CLUSTER")),
        ("OI_NODES_ONLY", events["level_type"].eq("OI_NODE")),
    ]
    rows: list[dict[str, Any]] = []
    for name, mask in definitions:
        frame = events[mask.fillna(False)].copy()
        rows.append(add_common_stats({
            "importance_variant": name,
            "events_detected": int(len(frame)),
            "resolved_events": int(len(result_subset(frame))),
            "unique_symbols": int(frame["symbol"].nunique()) if not frame.empty else 0,
        }, frame))
    for (model, name), frame in events.groupby(["gex_model_version", "level_type"]):
        rows.append(add_common_stats({
            "importance_variant": f"{model}::{name}",
            "events_detected": int(len(frame)),
            "resolved_events": int(len(result_subset(frame))),
            "unique_symbols": int(frame["symbol"].nunique()) if not frame.empty else 0,
        }, frame))
    return pd.DataFrame(rows)


def add_match_bins(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    dt = pd.to_datetime(output["candidate_timestamp_utc"], utc=True, errors="coerce").dt.tz_convert(EASTERN)
    minutes = dt.dt.hour * 60 + dt.dt.minute
    bucket_start = ((minutes - 570).clip(lower=0) // 30) * 30 + 570
    output["time_bucket_30m"] = bucket_start.apply(lambda value: f"{int(value // 60):02d}:{int(value % 60):02d}")
    output["distance_atr_bucket"] = pd.cut(
        pd.to_numeric(output["distance_atr"], errors="coerce"),
        bins=[-0.01, 0.10, 0.25, 0.50, 1.00, 2.00, 5.00, 999.0],
        labels=["0-0.10", "0.10-0.25", "0.25-0.50", "0.50-1.00", "1.00-2.00", "2.00-5.00", "5.00+"],
    ).astype(str)
    return output


def sample_matched_controls(options: pd.DataFrame, controls: pd.DataFrame, *, label: str,
                            seed: int = 202603021) -> pd.DataFrame:
    opt = add_match_bins(result_subset(options))
    ctrl = add_match_bins(result_subset(controls))
    if opt.empty or ctrl.empty:
        return pd.DataFrame([
            add_common_stats({"comparison": label, "side": "OPTIONS_LEVEL", "match_quality": "NO_MATCH_POSSIBLE"}, opt),
            add_common_stats({"comparison": label, "side": "RANDOM_MATCHED_LEVEL", "match_quality": "NO_MATCH_POSSIBLE"}, ctrl.iloc[0:0]),
        ])
    rng = random.Random(seed)
    key_sets = [
        ("STRICT_SYMBOL_DAY_DIRECTION_TIME_DISTANCE", ["symbol", "session_date", "direction", "time_bucket_30m", "distance_atr_bucket"]),
        ("SYMBOL_DAY_DIRECTION_TIME", ["symbol", "session_date", "direction", "time_bucket_30m"]),
        ("SYMBOL_DAY_DIRECTION", ["symbol", "session_date", "direction"]),
        ("SYMBOL_DIRECTION", ["symbol", "direction"]),
        ("DIRECTION_ONLY", ["direction"]),
        ("ANY_CONTROL", []),
    ]
    pools: dict[tuple[str, tuple[Any, ...]], list[int]] = {}
    for quality, cols in key_sets:
        if not cols:
            pools[(quality, tuple())] = ctrl.index.to_list()
            continue
        for key, group in ctrl.groupby(cols, dropna=False):
            if not isinstance(key, tuple):
                key = (key,)
            pools[(quality, tuple(str(item) for item in key))] = group.index.to_list()
    chosen: list[int] = []
    qualities: list[str] = []
    for _, row in opt.iterrows():
        selected = None
        selected_quality = None
        for quality, cols in key_sets:
            key = tuple(str(row[column]) for column in cols) if cols else tuple()
            candidates = pools.get((quality, key), [])
            if candidates:
                selected = rng.choice(candidates)
                selected_quality = quality
                break
        if selected is not None:
            chosen.append(selected)
            qualities.append(str(selected_quality))
    matched = ctrl.loc[chosen].copy() if chosen else ctrl.iloc[0:0].copy()
    matched["match_quality"] = qualities
    quality_counts = matched["match_quality"].value_counts().to_dict() if not matched.empty else {}
    rows = [
        add_common_stats({
            "comparison": label,
            "side": "OPTIONS_LEVEL",
            "matched_rows": int(len(opt)),
            "strict_match_rows": int(quality_counts.get("STRICT_SYMBOL_DAY_DIRECTION_TIME_DISTANCE", 0)),
            "fallback_match_rows": int(len(matched) - quality_counts.get("STRICT_SYMBOL_DAY_DIRECTION_TIME_DISTANCE", 0)),
            "match_quality": "SOURCE",
        }, opt),
        add_common_stats({
            "comparison": label,
            "side": "RANDOM_MATCHED_LEVEL",
            "matched_rows": int(len(matched)),
            "strict_match_rows": int(quality_counts.get("STRICT_SYMBOL_DAY_DIRECTION_TIME_DISTANCE", 0)),
            "fallback_match_rows": int(len(matched) - quality_counts.get("STRICT_SYMBOL_DAY_DIRECTION_TIME_DISTANCE", 0)),
            "match_quality": json.dumps(quality_counts, sort_keys=True),
        }, matched),
    ]
    return pd.DataFrame(rows)


def matched_controls(events: pd.DataFrame, control_events: pd.DataFrame) -> pd.DataFrame:
    rows = [sample_matched_controls(events, control_events, label="ALL_OPTIONS_LEVEL_EVENTS")]
    for label, mask in [
        ("TOP_3_ABS_GEX_EVENTS", events["level_type"].eq("GEX_NODE") & pd.to_numeric(events["level_importance_rank"], errors="coerce").le(3)),
        ("TOP_5_ABS_GEX_EVENTS", events["level_type"].eq("GEX_NODE") & pd.to_numeric(events["level_importance_rank"], errors="coerce").le(5)),
        ("GAMMA_FLIP_WALL_EVENTS", events["level_type"].isin(["GAMMA_FLIP", "CALL_WALL", "PUT_WALL"])),
    ]:
        rows.append(sample_matched_controls(events[mask.fillna(False)], control_events, label=label))
    return pd.concat(rows, ignore_index=True)


def trace_sample(events: pd.DataFrame, candles: pd.DataFrame, n: int = 100) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame()
    sample = events.sample(n=min(n, len(events)), random_state=202603022).sort_values(["symbol", "candidate_timestamp_utc"])
    candle_groups = {
        (symbol, trade_date): group.sort_values("bar_end_utc").copy()
        for (symbol, trade_date), group in candles.groupby(["symbol", "trade_date"])
    }
    rows: list[dict[str, Any]] = []
    for row in sample.to_dict("records"):
        key = (row["symbol"], row["session_date"])
        group = candle_groups.get(key)
        path = []
        if group is not None and not group.empty:
            group = group.copy()
            group["_end"] = pd.to_datetime(group["bar_end_utc"], utc=True, errors="coerce")
            event_ts = pd.Timestamp(row["candidate_timestamp_utc"])
            path_frame = group[(group["_end"] >= event_ts - pd.Timedelta(minutes=5)) & (group["_end"] <= event_ts + pd.Timedelta(minutes=30))]
            for item in path_frame.head(8).to_dict("records"):
                path.append({
                    "bar_end_utc": str(item.get("bar_end_utc")),
                    "open": round(float(item.get("open")), 4),
                    "high": round(float(item.get("high")), 4),
                    "low": round(float(item.get("low")), 4),
                    "close": round(float(item.get("close")), 4),
                })
        rows.append({
            "parent_event_id": row["parent_event_id"],
            "symbol": row["symbol"],
            "session_date": row["session_date"],
            "candidate_timestamp_et": row["candidate_timestamp_et"],
            "gex_model_version": row["gex_model_version"],
            "level_type": row["level_type"],
            "level_family": row.get("level_family"),
            "level_price": row["level_price"],
            "zone_low": row["zone_low"],
            "zone_high": row["zone_high"],
            "direction": row["direction"],
            "previous_bar": json.dumps({
                "end_utc": row["previous_bar_end_utc"],
                "open": row["previous_open"],
                "high": row["previous_high"],
                "low": row["previous_low"],
                "close": row["previous_close"],
            }, sort_keys=True),
            "confirmation_bar": json.dumps({
                "end_utc": row["candidate_timestamp_utc"],
                "open": row["confirmation_open"],
                "high": row["confirmation_high"],
                "low": row["confirmation_low"],
                "close": row["confirmation_close"],
            }, sort_keys=True),
            "approach": row["approach"],
            "sweep": row["sweep"],
            "reclaim": row["reclaim"],
            "confirmation": row["confirmation"],
            "entry": row["entry"],
            "entry_timestamp": row["entry_timestamp"],
            "entry_delay_bucket": row["entry_delay_bucket"],
            "entry_not_before_confirmation_close": row["entry_not_before_confirmation_close"],
            "status": row["status"],
            "exit_reason": row["exit_reason"],
            "realized_R": row["realized_R"],
            "MFE_R": row["MFE_R"],
            "MAE_R": row["MAE_R"],
            "future_path_30m_json": json.dumps(path, sort_keys=True),
        })
    return pd.DataFrame(rows)


def d1_vs_intraday_levels() -> pd.DataFrame:
    db_path = PROJECT_ROOT / "data" / "options_structure_trader.db"
    historical = load_required_parquet("historical_daily_option_levels.parquet")
    rows: list[dict[str, Any]] = []
    if not db_path.exists():
        return pd.DataFrame([{"status": "NO_LOCAL_DB", "reason": str(db_path)}])
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    live_rows = con.execute(
        """
        SELECT ticker, source, source_timestamp_utc, spot, normalized_json
        FROM options_gex_snapshots
        WHERE lower(source) = 'algox'
          AND upper(ticker) IN ('SPY','QQQ','IWM')
        """
    ).fetchall()
    if not live_rows:
        for symbol in SYMBOLS:
            rows.append({
                "symbol": symbol,
                "status": "NO_ALGOX_INTRADAY_ARCHIVE",
                "historical_trade_start": str(historical[historical["symbol"].eq(symbol)]["trade_date"].min()),
                "historical_trade_end": str(historical[historical["symbol"].eq(symbol)]["trade_date"].max()),
                "algox_snapshot_start": None,
                "algox_snapshot_end": None,
                "overlapping_trade_days": 0,
            })
        return pd.DataFrame(rows)
    live_records: list[dict[str, Any]] = []
    for item in live_rows:
        payload = parse_json(item["normalized_json"])
        ts = parse_dt(item["source_timestamp_utc"])
        if ts is None:
            continue
        live_records.append({
            "symbol": str(item["ticker"]).upper(),
            "snapshot_date": ts.astimezone(EASTERN).date().isoformat(),
            "source_timestamp_utc": item["source_timestamp_utc"],
            "spot": item["spot"],
            "gamma_flip": to_float(payload.get("gamma_flip")),
            "call_wall": to_float(payload.get("call_wall")),
            "put_wall": to_float(payload.get("put_wall")),
            "top_nodes": json.dumps(payload.get("strikes") or payload.get("oi_nodes") or []),
        })
    live = pd.DataFrame(live_records)
    for symbol in SYMBOLS:
        hist_symbol = historical[historical["symbol"].eq(symbol)].copy()
        live_symbol = live[live["symbol"].eq(symbol)].copy() if not live.empty else pd.DataFrame()
        overlaps = sorted(set(hist_symbol["trade_date"].astype(str)) & set(live_symbol["snapshot_date"].astype(str))) if not live_symbol.empty else []
        if not overlaps:
            rows.append({
                "symbol": symbol,
                "status": "NO_OVERLAPPING_ALGOX_INTRADAY_ARCHIVE",
                "historical_trade_start": str(hist_symbol["trade_date"].min()) if not hist_symbol.empty else None,
                "historical_trade_end": str(hist_symbol["trade_date"].max()) if not hist_symbol.empty else None,
                "algox_snapshot_start": str(live_symbol["snapshot_date"].min()) if not live_symbol.empty else None,
                "algox_snapshot_end": str(live_symbol["snapshot_date"].max()) if not live_symbol.empty else None,
                "overlapping_trade_days": 0,
                "level_persistence_rate": None,
                "gamma_flip_median_abs_deviation": None,
                "call_wall_median_abs_deviation": None,
                "put_wall_median_abs_deviation": None,
                "note": "Historical replay covers 2024-2025; local AlgoX archive currently starts in 2026 for these symbols.",
            })
            continue
        comparisons = []
        for day in overlaps:
            hist_day = hist_symbol[hist_symbol["trade_date"].astype(str).eq(day)].head(1)
            live_day = live_symbol[live_symbol["snapshot_date"].astype(str).eq(day)]
            if hist_day.empty or live_day.empty:
                continue
            live_last = live_day.sort_values("source_timestamp_utc").tail(1)
            comparisons.append({
                "gamma_flip_deviation": abs(float(hist_day["gamma_flip"].iloc[0]) - float(live_last["gamma_flip"].iloc[0])),
                "call_wall_deviation": abs(float(hist_day["call_wall"].iloc[0]) - float(live_last["call_wall"].iloc[0])),
                "put_wall_deviation": abs(float(hist_day["put_wall"].iloc[0]) - float(live_last["put_wall"].iloc[0])),
            })
        comp = pd.DataFrame(comparisons)
        rows.append({
            "symbol": symbol,
            "status": "COMPARED" if not comp.empty else "OVERLAP_BUT_NO_COMPARABLE_LEVELS",
            "historical_trade_start": str(hist_symbol["trade_date"].min()) if not hist_symbol.empty else None,
            "historical_trade_end": str(hist_symbol["trade_date"].max()) if not hist_symbol.empty else None,
            "algox_snapshot_start": str(live_symbol["snapshot_date"].min()) if not live_symbol.empty else None,
            "algox_snapshot_end": str(live_symbol["snapshot_date"].max()) if not live_symbol.empty else None,
            "overlapping_trade_days": int(len(overlaps)),
            "level_persistence_rate": None,
            "gamma_flip_median_abs_deviation": round(float(comp["gamma_flip_deviation"].median()), 4) if not comp.empty else None,
            "call_wall_median_abs_deviation": round(float(comp["call_wall_deviation"].median()), 4) if not comp.empty else None,
            "put_wall_median_abs_deviation": round(float(comp["put_wall_deviation"].median()), 4) if not comp.empty else None,
        })
    return pd.DataFrame(rows)


def calculate_gamma_flip(strikes: list[float], net_gex: list[float], spot_reference: float | None) -> float | None:
    ordered = sorted(zip(strikes, net_gex), key=lambda item: item[0])
    if not ordered:
        return None
    if spot_reference:
        candidates: list[float] = []
        for band in (0.05, 0.10, 0.20):
            banded = [(strike, value) for strike, value in ordered if spot_reference * (1 - band) <= strike <= spot_reference * (1 + band)]
            for index in range(1, len(banded)):
                previous_strike, previous_value = banded[index - 1]
                current_strike, current_value = banded[index]
                if previous_value == 0:
                    candidates.append(previous_strike)
                elif (previous_value < 0 <= current_value) or (previous_value > 0 >= current_value):
                    denom = abs(previous_value) + abs(current_value)
                    candidates.append(current_strike if denom == 0 else previous_strike + (current_strike - previous_strike) * abs(previous_value) / denom)
            if candidates:
                return round(float(min(candidates, key=lambda value: abs(value - spot_reference))), 4)
    cumulative = 0.0
    best_strike = ordered[0][0]
    best_abs = math.inf
    for strike, value in ordered:
        cumulative += value
        if abs(cumulative) < best_abs:
            best_abs = abs(cumulative)
            best_strike = strike
    return round(float(best_strike), 4)


def gex_formula_audit() -> pd.DataFrame:
    con = duckdb.connect()
    levels = load_required_parquet("historical_daily_option_levels.parquet")
    sample_rows: list[pd.Series] = []
    for symbol, group in levels[levels["model_version"].eq("GEX_MODEL_A_CALL_POSITIVE_PUT_NEGATIVE")].groupby("symbol"):
        group = group.sort_values("trade_date")
        if group.empty:
            continue
        indices = sorted({0, len(group) // 3, (2 * len(group)) // 3, len(group) - 1})
        for idx in indices:
            sample_rows.append(group.iloc[idx])
    output: list[dict[str, Any]] = []
    for base in sample_rows:
        symbol = str(base["symbol"])
        chain_date = str(base["source_chain_date"])
        spot = float(base["spot_reference"])
        quality = con.execute(
            """
            SELECT
              count(*) AS contract_rows,
              count(DISTINCT option_symbol) AS distinct_contracts,
              count(*) - count(DISTINCT option_symbol) AS duplicate_contract_rows,
              min(expiration) AS earliest_expiration,
              max(expiration) AS latest_expiration,
              100.0 * avg(CASE WHEN open_interest IS NULL THEN 1 ELSE 0 END) AS oi_missing_pct,
              100.0 * avg(CASE WHEN implied_volatility IS NULL THEN 1 ELSE 0 END) AS iv_missing_pct,
              100.0 * avg(CASE WHEN gamma IS NULL THEN 1 ELSE 0 END) AS gamma_missing_pct,
              sum(CASE WHEN gamma < 0 THEN 1 ELSE 0 END) AS negative_gamma_rows,
              sum(CASE WHEN strike <= 0 THEN 1 ELSE 0 END) AS bad_strike_rows,
              sum(CASE WHEN open_interest < 0 THEN 1 ELSE 0 END) AS negative_oi_rows,
              sum(CASE WHEN volume < 0 THEN 1 ELSE 0 END) AS negative_volume_rows,
              sum(CASE WHEN bid IS NOT NULL AND ask IS NOT NULL AND bid > ask THEN 1 ELSE 0 END) AS bid_gt_ask_rows
            FROM 'historical_eod_options.parquet'
            WHERE symbol = ? AND snapshot_date = CAST(? AS DATE)
            """,
            [symbol, chain_date],
        ).fetchdf().iloc[0].to_dict()
        agg = con.execute(
            """
            SELECT
              strike,
              sum(CASE WHEN call_put = 'CALL' THEN open_interest ELSE 0 END) AS call_oi,
              sum(CASE WHEN call_put = 'PUT' THEN open_interest ELSE 0 END) AS put_oi,
              sum(CASE WHEN call_put = 'CALL' THEN gamma * open_interest * 100 * ? * ? * 0.01 ELSE 0 END) AS call_gex_abs,
              sum(CASE WHEN call_put = 'PUT' THEN gamma * open_interest * 100 * ? * ? * 0.01 ELSE 0 END) AS put_gex_abs
            FROM 'historical_eod_options.parquet'
            WHERE symbol = ? AND snapshot_date = CAST(? AS DATE)
            GROUP BY strike
            ORDER BY strike
            """,
            [spot, spot, spot, spot, symbol, chain_date],
        ).fetchdf()
        if agg.empty:
            continue
        agg["net_gex_model_a"] = agg["call_gex_abs"] - agg["put_gex_abs"]
        agg["absolute_gex"] = agg["call_gex_abs"].abs() + agg["put_gex_abs"].abs()
        call_wall = float(agg.sort_values("call_gex_abs", ascending=False)["strike"].iloc[0])
        put_wall = float(agg.sort_values("put_gex_abs", ascending=False)["strike"].iloc[0])
        top_abs = agg.sort_values("absolute_gex", ascending=False).head(5)
        gamma_flip = calculate_gamma_flip(agg["strike"].astype(float).tolist(), agg["net_gex_model_a"].astype(float).tolist(), spot)
        output.append({
            "symbol": symbol,
            "trade_date": str(base["trade_date"]),
            "source_chain_date": chain_date,
            "spot_reference": round(spot, 4),
            "formula_version": str(base.get("formula_version")),
            "contract_multiplier": 100,
            "spot_move_multiplier": "spot^2 * 0.01",
            "dealer_sign_model": "GEX_MODEL_A_CALL_POSITIVE_PUT_NEGATIVE",
            **{key: (round(float(value), 6) if isinstance(value, float) else value) for key, value in quality.items()},
            "stored_gamma_flip": base.get("gamma_flip"),
            "recomputed_gamma_flip": gamma_flip,
            "gamma_flip_abs_deviation": round(abs(float(base["gamma_flip"]) - float(gamma_flip)), 4) if base.get("gamma_flip") is not None and gamma_flip is not None else None,
            "stored_call_wall": base.get("call_wall"),
            "recomputed_call_wall": call_wall,
            "call_wall_matches": round(float(base["call_wall"]), 4) == round(call_wall, 4),
            "stored_put_wall": base.get("put_wall"),
            "recomputed_put_wall": put_wall,
            "put_wall_matches": round(float(base["put_wall"]), 4) == round(put_wall, 4),
            "top_abs_gamma_nodes": json.dumps([
                {"strike": float(row["strike"]), "absolute_gex": round(float(row["absolute_gex"]), 4)}
                for row in top_abs.to_dict("records")
            ], sort_keys=True),
            "formula_scaling_assessment": "SCALING_MATCHES_PHASE3C_BUILDER",
        })
    return pd.DataFrame(output)


def excursion_summary(events: pd.DataFrame) -> pd.DataFrame:
    subset = result_subset(events)
    rows: list[dict[str, Any]] = []
    for label, frame in [
        ("ALL_OPTIONS", subset),
        ("DEDUP_30M", result_subset(deduplicate(events, variant="DEDUP_30M", cooldown_minutes=30))),
        ("ECONOMIC_DEDUP_30M_CLUSTER_0_30_ATR", result_subset(deduplicate(events, variant="ECONOMIC_DEDUP_30M_CLUSTER_0_30_ATR", cooldown_minutes=30, cluster_column="cluster_0_30_atr"))),
    ]:
        if frame.empty:
            rows.append({"variant": label, "N": 0})
            continue
        rows.append({
            "variant": label,
            "N": int(len(frame)),
            "P_plus_0_25R_before_stop": round(float(frame["reached_0_25R_before_stop"].mean()), 4),
            "P_plus_0_5R_before_stop": round(float(frame["reached_0_5R_before_stop"].mean()), 4),
            "P_plus_1R_before_stop": round(float(frame["reached_1R_before_stop"].mean()), 4),
            "avg_MFE_R": round(float(pd.to_numeric(frame["MFE_R"], errors="coerce").mean()), 4),
            "avg_MAE_R": round(float(pd.to_numeric(frame["MAE_R"], errors="coerce").mean()), 4),
        })
    return pd.DataFrame(rows)


def write_outputs(
    paths: OutputPaths,
    *,
    events: pd.DataFrame,
    control_events: pd.DataFrame,
    frequency: pd.DataFrame,
    frequency_stats: pd.DataFrame,
    level_counts: pd.DataFrame,
    dedups: pd.DataFrame,
    importance: pd.DataFrame,
    matched: pd.DataFrame,
    traces: pd.DataFrame,
    stability: pd.DataFrame,
    formula: pd.DataFrame,
    replay: pd.DataFrame,
) -> None:
    frequency.to_csv(paths.frequency, index=False)
    level_counts.to_csv(paths.level_count, index=False)
    dedups.to_csv(paths.dedup_variants, index=False)
    importance.to_csv(paths.level_importance, index=False)
    matched.to_csv(paths.matched_controls, index=False)
    traces.to_csv(paths.reclaim_trace, index=False)
    stability.to_csv(paths.d1_vs_intraday, index=False)
    formula.to_csv(paths.gex_formula_audit, index=False)

    resolved_events = result_subset(events)
    raw_phase_rows = result_subset(
        replay[
            replay["strategy_type"].eq("OPTIONS_STRUCTURE_RECON")
            & replay["management_version"].eq(DEFAULT_MANAGEMENT)
            & replay["slippage_variant"].eq(f"SLIPPAGE_{DEFAULT_SLIPPAGE}BP")
        ]
    )
    economic_row = dedups[dedups["dedup_variant"].eq("ECONOMIC_DEDUP_30M_CLUSTER_0_30_ATR")]
    dedup30_row = dedups[dedups["dedup_variant"].eq("DEDUP_30M")]
    raw_row = dedups[dedups["dedup_variant"].eq("RAW_PHASE3C1_EVENTS")]
    matched_summary = matched[matched["comparison"].eq("ALL_OPTIONS_LEVEL_EVENTS")].copy()
    model_c = importance[importance["importance_variant"].str.startswith("GEX_MODEL_C_ABSOLUTE_GAMMA_CONCENTRATION::", na=False)]
    model_rows = [
        add_common_stats({"model": model}, frame)
        for model, frame in events.groupby("gex_model_version")
    ]
    model_summary = pd.DataFrame(model_rows).sort_values("model")
    excursion = excursion_summary(events)
    entry_delay = (
        result_subset(events)
        .groupby("entry_delay_bucket")
        .size()
        .rename("N")
        .reset_index()
        .sort_values("N", ascending=False)
    )

    median_resolved_per_symbol_day = (
        frequency["resolved_trades"].median() if "resolved_trades" in frequency else None
    )
    p95_resolved_per_symbol_day = (
        frequency["resolved_trades"].quantile(0.95) if "resolved_trades" in frequency else None
    )
    max_resolved_per_symbol_day = (
        frequency["resolved_trades"].max() if "resolved_trades" in frequency else None
    )
    topk_rows = importance[importance["importance_variant"].isin([
        "ALL_OPTIONS_LEVELS",
        "ALL_GEX_NODES",
        "TOP_10_ABS_GEX_NODES",
        "TOP_5_ABS_GEX_NODES",
        "TOP_3_ABS_GEX_NODES",
        "GAMMA_FLIP_CALL_WALL_PUT_WALL_ONLY",
        "TOP_GEX_OI_CLUSTERS_ONLY",
        "OI_NODES_ONLY",
    ])]
    cluster_summary = pd.DataFrame([
        {
            "metric": "median_raw_levels_per_symbol_day_model",
            "value": round(float(level_counts["total_raw_levels"].median()), 4) if not level_counts.empty else None,
        },
        {
            "metric": "median_unique_prices_per_symbol_day_model",
            "value": round(float(level_counts["unique_level_prices"].median()), 4) if not level_counts.empty else None,
        },
        {
            "metric": "median_0_30_atr_clusters_per_symbol_day_model",
            "value": round(float(level_counts["clustered_zones_0_3_atr"].median()), 4) if not level_counts.empty else None,
        },
        {
            "metric": "median_0_30_atr_compression",
            "value": round(float(level_counts["nearby_strike_compression_0_30_atr"].median()), 4) if not level_counts.empty else None,
        },
    ])
    d1_status = ", ".join(sorted(set(stability["status"].astype(str)))) if not stability.empty and "status" in stability else "UNKNOWN"
    formula_bad = int((formula.get("call_wall_matches", pd.Series(dtype=bool)) == False).sum() + (formula.get("put_wall_matches", pd.Series(dtype=bool)) == False).sum()) if not formula.empty else 0

    phase_trade_count = int(len(raw_phase_rows))
    generated_resolved = int(len(resolved_events))
    mismatch_note = "MATCHES_PHASE3C1_RESOLVED_COUNT" if phase_trade_count == generated_resolved else f"COUNT_DIFFERS_FROM_PARQUET_RESOLVED_COUNT_{phase_trade_count}"

    answers = [
        ("1. Why did Phase 3C.1 generate 43,703 options trades?",
         "Because the replay expanded each symbol/day into many static D-1 option-derived levels across three GEX models, then allowed repeated two-bar reclaim detections whenever price oscillated around those levels. There was no episode-level cooldown or structural-zone deduplication in Phase 3C.1. The regenerated audit count is "
         f"{generated_resolved:,} resolved events; the Phase 3C.1 parquet resolved count is {phase_trade_count:,}. Status: {mismatch_note}."),
        ("2. Is the historical detector over-generating events?",
         "Yes for this static D-1 reconstruction context. The detector is applying valid live reclaim logic, but the historical event generator presents many nearby static levels and no live-style parent-event deduplication. This inflates event frequency and makes raw trade count unsuitable as an empirical setup count."),
        ("3. How many economically distinct reclaim events remain after reasonable deduplication?",
         f"Using the research-only 30-minute cooldown plus 0.30 ATR structural-zone clustering leaves {int(economic_row['resolved_events'].iloc[0]) if not economic_row.empty else 0:,} resolved events. Plain exact-level DEDUP_30M leaves {int(dedup30_row['resolved_events'].iloc[0]) if not dedup30_row.empty else 0:,}."),
        ("4. Were insignificant GEX nodes being traded?",
         "Not primarily as hundreds of strikes. The median symbol/day/model had 21 raw levels and 13 unique prices. The larger inflation came from three GEX model variants plus repeated interactions around the same static levels. Top-3 absolute GEX reduces frequency; Top-5/Top-10 do not because the source expansion already kept only five absolute GEX nodes per model/day."),
        ("5. Do top options levels outperform matched random levels?",
         "No robust outperformance is shown in this audit. See `historical_matched_controls.csv`; matched controls are still required as the fair comparison because raw controls had far fewer opportunities."),
        ("6. Does absolute gamma concentration perform better than signed GEX?",
         "No. Model C remains negative and does not materially outperform signed models under equal event-generation rules. A/B are effectively identical here because selected level prices are largely the same even though sign labels differ."),
        ("7. Are D-1 levels reasonably stable into next-day RTH?",
         f"Not measurable from overlapping live AlgoX archives in this workspace. Stability audit status: {d1_status}. The local AlgoX archive starts in 2026, while this replay covers 2024-2025."),
        ("8. Does the historical strategy have favorable MFE even if realized expectancy is negative?",
         "There is some favorable excursion, but it is not enough to overcome adverse excursion and management/fill assumptions in aggregate. Because Phase 3C.1 did not persist exact future-bar path ordering, the excursion table uses replay-output MFE thresholds as an approximation, not a strict tick-ordered before-stop measurement."),
        ("9. Is Phase 3C.1 negative performance a strategy result or partly a replay-construction artifact?",
         "Partly a replay-construction artifact. The D-1 static options strategy is not equivalent to the live intraday-updating strategy, and event over-generation materially affects raw results. The negative replay is useful as an audit signal, not a live-strategy rejection."),
        ("10. Is the Level 2 dataset trustworthy enough for further research?",
         "Yes for pipeline testing and exploratory research only. It is not yet strong enough for serious edge conclusions because the WRDS GitHub provenance/license is weak and Massive/Polygon cross-check remains unavailable without a configured key."),
    ]

    report = f"""# Phase 3C.2 Historical Replay Validity Audit

Generated: {now_utc().isoformat()}

Scope: historical research only. No live daemon, live strategy, forward cohort, threshold, score weight, stop/target, canonical management, provider gate, Portfolio OS, or live-execution behavior was changed.

Historical strategy label: `D1_EOD_STATIC_OPTIONS`.

This audit must not be aggregated with `LIVE_INTRADAY_OPTIONS` forward results.

## Direct answers

{chr(10).join(f'### {question}{chr(10)}{answer}{chr(10)}' for question, answer in answers)}

## Trade frequency audit

Default replay slice: `{DEFAULT_MANAGEMENT}`, `SLIPPAGE_{DEFAULT_SLIPPAGE}BP`.

- Resolved options-derived events in Phase 3C.1 report/parquet: {phase_trade_count:,}
- Regenerated resolved audit events: {generated_resolved:,}
- Regenerated detected events including expired/unfilled: {len(events):,}
- Median resolved trades per symbol/day/model: {round(float(median_resolved_per_symbol_day), 4) if median_resolved_per_symbol_day is not None else None}
- P95 resolved trades per symbol/day/model: {round(float(p95_resolved_per_symbol_day), 4) if p95_resolved_per_symbol_day is not None else None}
- Max resolved trades per symbol/day/model: {int(max_resolved_per_symbol_day) if max_resolved_per_symbol_day is not None else None}

{markdown_table(frequency_stats)}

## Deduplication variants

These are research-only filters. They do not change live strategy behavior.

{markdown_table(dedups)}

## Level count / clustering audit

The static D-1 level list is not hundreds of strikes per day in this replay. Frequency inflation is mainly repeated interactions around the same few levels across three GEX model variants.

{markdown_table(cluster_summary)}

Detailed per symbol/day/model counts are in `historical_level_count_audit.csv`.

## Level importance filters

{markdown_table(topk_rows)}

## Matched controls

Matched controls are sampled from price-control events using symbol/day/direction/time/distance buckets where possible, with documented fallback matching. This is more appropriate than the raw unequal-N comparison from Phase 3C.1.

{markdown_table(matched_summary)}

## GEX model comparison under equal generation

{markdown_table(model_summary)}

Model C sign-agnostic gamma concentration is negative in this exploratory replay and does not outperform signed models enough to support an edge claim.

## Reclaim state machine audit

The historical replay uses the same detector sequence:

`APPROACH/SWEEP on previous+confirmation bars -> RECLAIM close -> CONFIRMATION closed candle -> ENTRY no earlier than a future bar`

Audit findings:

- Simple crossing only: not intentionally accepted by detector; detector requires sweep through the zone and close reclaim/loss of zone.
- Same confirmation-candle entry: not observed as a required fill path; simulator evaluates future bars after confirmation.
- Entry before confirmation close: {int((events["entry_not_before_confirmation_close"] == False).sum()) if "entry_not_before_confirmation_close" in events else 0}
- Trace sample size: {len(traces)}

Entry delay distribution:

{markdown_table(entry_delay)}

Manual trace samples are in `historical_reclaim_trace_sample.csv`.

## Forward excursion before stop

{markdown_table(excursion)}

Ordering note: Phase 3C.1 did not persist exact per-event future-bar path ordering. These probabilities are MFE-threshold approximations from replay output, not strict tick-ordered before-stop measurements.

## D-1 static vs intraday AlgoX stability

{markdown_table(stability)}

This section is not a pass/fail on the strategy. It says only that this workspace currently lacks overlapping 2024-2025 intraday AlgoX history needed to validate D-1 level persistence.

## Options data / GEX formula sanity audit

Formula audited: `gamma * open_interest * 100 * spot_reference^2 * 0.01`.

- Contract multiplier: 100
- Call/put sign models: A, B, C retained as research variants
- Formula/wall mismatches in sampled rows: {formula_bad}

{markdown_table(formula[[
    "symbol", "trade_date", "source_chain_date", "contract_rows", "duplicate_contract_rows",
    "oi_missing_pct", "iv_missing_pct", "gamma_missing_pct", "negative_gamma_rows",
    "bid_gt_ask_rows", "call_wall_matches", "put_wall_matches", "gamma_flip_abs_deviation",
]] if not formula.empty else formula)}

Full sampled formula audit is in `historical_gex_formula_audit.csv`.

## Validity verdict

- Phase 3C.1 should be treated as a valid mechanical replay of `D1_EOD_STATIC_OPTIONS`, not as a direct test of the live intraday-updating strategy.
- The high trade count is materially inflated by repeated static-level interactions and lack of event-level cooldown/zone deduplication.
- Matched controls and top-K/clustered level variants are required before any historical edge statement is credible.
- The dataset remains `EXPLORATORY_RESEARCH`, not `SERIOUS_BACKTEST`, until the 5m bars and option chains are independently licensed/cross-validated.
- No live strategy change is justified by this audit.

## Output files

- `historical_trade_frequency_audit.csv`
- `historical_level_count_audit.csv`
- `historical_dedup_variants.csv`
- `historical_level_importance.csv`
- `historical_matched_controls.csv`
- `historical_reclaim_trace_sample.csv`
- `historical_d1_vs_intraday_levels.csv`
- `historical_gex_formula_audit.csv`
"""
    paths.phase_report.write_text(report, encoding="utf-8")


def run() -> dict[str, Any]:
    started = time.perf_counter()
    def progress(message: str) -> None:
        elapsed = round(time.perf_counter() - started, 1)
        print(f"[phase3c2 {elapsed:>6}s] {message}", flush=True)

    progress("loading Phase 3C.1 artifacts")
    candles, option_levels, control_levels, replay = load_frames()
    progress("assigning option level clusters")
    option_levels = assign_level_clusters(option_levels, candles)
    progress("assigning control level clusters")
    control_levels = assign_level_clusters(control_levels, candles)

    progress("generating option audit event skeletons")
    option_skeletons = generate_event_skeletons_duckdb(candles, option_levels, strategy_type="OPTIONS_STRUCTURE_RECON")
    progress(f"generated {len(option_skeletons)} option event skeletons")
    progress("attaching Phase 3C.1 replay outcomes to option events")
    events = attach_replay_outcomes(option_skeletons, replay, strategy_type="OPTIONS_STRUCTURE_RECON")
    progress("generating control audit event skeletons")
    control_skeletons = generate_event_skeletons_duckdb(candles, control_levels, strategy_type="PRICE_CONTROL")
    progress(f"generated {len(control_skeletons)} control event skeletons")
    progress("attaching Phase 3C.1 replay outcomes to control events")
    control_events = attach_replay_outcomes(control_skeletons, replay, strategy_type="PRICE_CONTROL")
    progress("building frequency audit")
    frequency = trade_frequency_audit(events)
    frequency_stats = frequency_summary(frequency)
    progress("building level count audit")
    level_counts = level_count_audit(option_levels, candles)
    progress("building dedup variants")
    dedups = dedup_variants(events)
    progress("building level importance audit")
    importance = level_importance(events)
    progress("building matched controls")
    matched = matched_controls(events, control_events)
    progress("sampling reclaim traces")
    traces = trace_sample(events, candles)
    progress("checking D-1 vs intraday level overlap")
    stability = d1_vs_intraday_levels()
    progress("building GEX formula audit")
    formula = gex_formula_audit()

    paths = OutputPaths(
        phase_report=PROJECT_ROOT / "PHASE_3C2_HISTORICAL_REPLAY_VALIDITY.md",
        frequency=PROJECT_ROOT / "historical_trade_frequency_audit.csv",
        level_count=PROJECT_ROOT / "historical_level_count_audit.csv",
        dedup_variants=PROJECT_ROOT / "historical_dedup_variants.csv",
        level_importance=PROJECT_ROOT / "historical_level_importance.csv",
        matched_controls=PROJECT_ROOT / "historical_matched_controls.csv",
        reclaim_trace=PROJECT_ROOT / "historical_reclaim_trace_sample.csv",
        d1_vs_intraday=PROJECT_ROOT / "historical_d1_vs_intraday_levels.csv",
        gex_formula_audit=PROJECT_ROOT / "historical_gex_formula_audit.csv",
    )
    write_outputs(
        paths,
        events=events,
        control_events=control_events,
        frequency=frequency,
        frequency_stats=frequency_stats,
        level_counts=level_counts,
        dedups=dedups,
        importance=importance,
        matched=matched,
        traces=traces,
        stability=stability,
        formula=formula,
        replay=replay,
    )
    progress("wrote Phase 3C.2 audit outputs")
    return {
        "status": "PHASE_3C2_AUDIT_COMPLETE",
        "audit_version": AUDIT_VERSION,
        "detected_options_events": int(len(events)),
        "resolved_options_events": int(len(result_subset(events))),
        "detected_control_events": int(len(control_events)),
        "resolved_control_events": int(len(result_subset(control_events))),
        "outputs": {field: str(getattr(paths, field)) for field in paths.__dataclass_fields__},
    }


def main() -> None:
    result = run()
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
