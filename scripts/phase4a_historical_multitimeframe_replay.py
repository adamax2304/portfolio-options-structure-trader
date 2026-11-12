from __future__ import annotations

import hashlib
import json
import math
import random
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, time, timezone
from pathlib import Path
from statistics import median
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (str(ROOT), str(SRC)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from options_structure_trader.config import Settings  # noqa: E402


EASTERN = ZoneInfo("America/New_York")
PHASE_NAMESPACE = "PHASE_4A_HISTORICAL"
REPLAY_VERSION = "phase4a_historical_multitimeframe_replay_v1"
LEVEL_STRENGTH_VERSION = "phase4a_historical_level_strength_v1"
EVENT_DEDUP_VERSION = "phase4a_historical_60m_level_episode_dedup_v1"
BRANCH_MATRIX_VERSION = "phase4a_historical_A_B_E_matrix_v1"
BOOTSTRAP_ITERATIONS = 200
SYMBOLS = ("SPY", "QQQ", "IWM")
RESOLVED = {"closed", "censored"}
PRIMARY_HISTORICAL_GEX_MODELS = ("GEX_MODEL_C_ABSOLUTE_GAMMA_CONCENTRATION",)

VARIANTS = {
    "VARIANT_A_HIST_5M_CONFIRM_5M_ENTRY": {
        "variant": "A-HIST",
        "confirmation_tf": "5m",
        "execution_tf": "5m",
        "context_tf": "5m",
        "requires_15m": False,
        "requires_30m_context": False,
    },
    "VARIANT_B_HIST_15M_CONFIRM_5M_ENTRY": {
        "variant": "B-HIST",
        "confirmation_tf": "15m",
        "execution_tf": "5m",
        "context_tf": "15m",
        "requires_15m": True,
        "requires_30m_context": False,
    },
    "VARIANT_E_HIST_30M_CONTEXT_15M_SETUP_5M_ENTRY": {
        "variant": "E-HIST",
        "confirmation_tf": "15m",
        "execution_tf": "5m",
        "context_tf": "30m",
        "requires_15m": True,
        "requires_30m_context": True,
    },
}

HISTORICALLY_UNAVAILABLE_VARIANTS = {
    "VARIANT_C_PERSISTENT_INTRADAY_5M": "Requires true intraday options-level persistence/strengthening snapshots.",
    "VARIANT_D_PERSISTENT_INTRADAY_15M_5M": "Requires true intraday options-level persistence/strengthening snapshots.",
}

ENTRY_VARIANTS = {
    "ENTRY_1_CLOSE_RECLAIM": "close reclaim / rejection / acceptance",
    "ENTRY_2_RECLAIM_RETEST": "reclaim + retest",
    "ENTRY_3_SWEEP_RECLAIM_RETEST": "sweep + reclaim + retest",
    "ENTRY_4_VOLUME_CONFIRMATION": "reclaim + volume confirmation",
    "ENTRY_5_MARKET_ALIGNMENT": "reclaim + market alignment",
}

STOP_VARIANTS = {
    "STOP_A_CURRENT_STRUCTURAL": None,
    "STOP_B_STRUCTURE_PLUS_0_15_ATR": 0.15,
    "STOP_C_STRUCTURE_PLUS_0_30_ATR": 0.30,
    "STOP_D_STRUCTURE_PLUS_0_50_ATR": 0.50,
    "STOP_E_ZONE_INVALIDATION": 0.0,
}

MANAGEMENT_VARIANTS = {
    "TM_V0_CURRENT": [(1.0, 0.33, "TP1_PARTIAL"), (1.5, 0.33, "TP2_PARTIAL"), (2.0, 0.34, "TP3_PARTIAL")],
    "TM_V3_TP1_PLUS_RUNNER": [(1.0, 0.50, "TP1_PARTIAL"), (2.0, 0.50, "RUNNER_EXIT")],
    "TM_FIXED_0_5R": [(0.5, 1.0, "FIXED_0_5R")],
    "TM_FIXED_1R": [(1.0, 1.0, "FIXED_1R")],
    "TM_FIXED_1_5R": [(1.5, 1.0, "FIXED_1_5R")],
    "TM_FIXED_2R": [(2.0, 1.0, "FIXED_2R")],
    "TM_HALF_0_5R_RUNNER": [(0.5, 0.50, "HALF_0_5R"), (2.0, 0.50, "RUNNER_EXIT")],
    "TM_HALF_1R_RUNNER": [(1.0, 0.50, "HALF_1R"), (2.0, 0.50, "RUNNER_EXIT")],
    "TM_STRUCTURE_TARGETS": [],
}

CONTROL_TYPES = (
    "MATCHED_RANDOM_NEARBY_LEVEL",
    "PREVIOUS_DAY_HIGH",
    "PREVIOUS_DAY_LOW",
    "VWAP",
    "ROUND_NUMBER",
)
PRIMARY_MANAGEMENT = ("TM_V0_CURRENT", "TM_V3_TP1_PLUS_RUNNER")

TIME_BUCKETS = [
    (time(9, 40), time(10, 30), "09:40-10:30"),
    (time(10, 30), time(11, 30), "10:30-11:30"),
    (time(11, 30), time(13, 0), "11:30-13:00"),
    (time(13, 0), time(14, 30), "13:00-14:30"),
    (time(14, 30), time(16, 1), "14:30-close"),
]


@dataclass(frozen=True)
class LevelCluster:
    cluster_id: str
    symbol: str
    trade_date: str
    gex_model_version: str
    center: float
    low: float
    high: float
    strength: float
    tier: str
    level_type: str
    source_level_types: tuple[str, ...]
    level_filter_memberships: tuple[str, ...]
    component_count: int
    min_source_rank: int
    source_chain_date: str | None
    gamma_regime: str
    historical_data_tier: str
    source_quality: str
    lookahead_safe: bool
    intraday_persistence_state: str
    level_strength_model_version: str


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def stable_hash(*parts: Any, length: int = 24) -> str:
    return hashlib.sha256("|".join("" if part is None else str(part) for part in parts).encode()).hexdigest()[:length]


def safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


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


def markdown_table(frame: pd.DataFrame, *, max_rows: int = 30) -> str:
    if frame.empty:
        return "No rows."
    display = frame.head(max_rows).copy()
    rows = ["| " + " | ".join(str(column) for column in display.columns) + " |"]
    rows.append("| " + " | ".join("---" for _ in display.columns) + " |")
    for item in display.to_dict("records"):
        rows.append("| " + " | ".join("" if pd.isna(item.get(column)) else str(item.get(column)) for column in display.columns) + " |")
    if len(frame) > max_rows:
        rows.append(f"| ... | {len(frame) - max_rows} more rows omitted |" + " |" * (len(display.columns) - 2))
    return "\n".join(rows)


def time_bucket(ts: pd.Timestamp) -> str:
    local = ts.tz_convert(EASTERN).time()
    for start, end, label in TIME_BUCKETS:
        if start <= local < end:
            return label
    return "OUTSIDE_RTH"


def floor_episode(ts: pd.Timestamp, minutes: int = 60) -> str:
    local = ts.tz_convert(EASTERN)
    minute = (local.minute // minutes) * minutes if minutes < 60 else 0
    return f"{local.date()}T{local.hour:02d}:{minute:02d}"


def classify_trend(values: pd.Series, lookback: int, idx: int) -> str:
    if idx - lookback < 0:
        return "UNKNOWN"
    latest = safe_float(values.iloc[idx])
    earlier = safe_float(values.iloc[idx - lookback])
    if latest is None or earlier in {None, 0}:
        return "UNKNOWN"
    change = (latest - earlier) / earlier
    threshold = 0.0015 if lookback <= 3 else 0.003
    if change > threshold:
        return "BULLISH"
    if change < -threshold:
        return "BEARISH"
    return "NEUTRAL"


def alignment(direction: str, trend: str) -> str:
    if trend == "UNKNOWN":
        return "UNKNOWN"
    if trend == "NEUTRAL":
        return "NEUTRAL"
    return "WITH_MARKET_TREND" if (direction == "LONG" and trend == "BULLISH") or (direction == "SHORT" and trend == "BEARISH") else "AGAINST_MARKET_TREND"


def profit_factor(values: pd.Series) -> float | str | None:
    values = pd.to_numeric(values, errors="coerce").dropna()
    if values.empty:
        return None
    wins = float(values[values > 0].sum())
    losses = float(values[values < 0].sum())
    if losses == 0:
        return "infinite" if wins > 0 else None
    return round(wins / abs(losses), 4)


def max_drawdown(values: pd.Series) -> float:
    values = pd.to_numeric(values, errors="coerce").dropna()
    if values.empty:
        return 0.0
    curve = values.cumsum()
    return round(float((curve.cummax() - curve).max()), 4)


def day_block_bootstrap_ci(frame: pd.DataFrame, *, seed: int = 20260905) -> tuple[float | None, float | None]:
    subset = frame[frame["status"].isin(RESOLVED)].copy()
    if subset.empty:
        return None, None
    daily = subset.groupby("trade_date")["result_R"].mean().dropna()
    if daily.empty:
        return None, None
    rng = random.Random(seed)
    values = daily.to_list()
    samples = [float(np.mean([rng.choice(values) for _ in values])) for _ in range(BOOTSTRAP_ITERATIONS)]
    return round(float(np.percentile(samples, 2.5)), 4), round(float(np.percentile(samples, 97.5)), 4)


def stats(frame: pd.DataFrame) -> dict[str, Any]:
    subset = frame[frame["status"].isin(RESOLVED)].copy() if "status" in frame else frame.copy()
    if subset.empty or "result_R" not in subset:
        return {
            "N": 0, "unique_days": 0, "expectancy_R": None, "PF": None, "win_rate": None,
            "median_R": None, "MFE": None, "MAE": None, "max_DD": None, "positive_day_pct": None,
            "day_block_ci_low": None, "day_block_ci_high": None,
        }
    values = pd.to_numeric(subset["result_R"], errors="coerce").dropna()
    if values.empty:
        return stats(pd.DataFrame())
    wins = values[values > 0]
    losses = values[values < 0]
    daily = subset.assign(_r=values).groupby("trade_date")["_r"].sum()
    ci_low, ci_high = day_block_bootstrap_ci(subset)
    return {
        "N": int(len(values)),
        "unique_days": int(subset["trade_date"].nunique()),
        "expectancy_R": round(float(values.mean()), 4),
        "PF": profit_factor(values),
        "win_rate": round(float((values > 0).mean()), 4),
        "median_R": round(float(values.median()), 4),
        "avg_winner": round(float(wins.mean()), 4) if not wins.empty else 0.0,
        "avg_loser": round(float(losses.mean()), 4) if not losses.empty else 0.0,
        "MFE": round(float(pd.to_numeric(subset.get("MFE_R"), errors="coerce").mean()), 4) if "MFE_R" in subset else None,
        "MAE": round(float(pd.to_numeric(subset.get("MAE_R"), errors="coerce").mean()), 4) if "MAE_R" in subset else None,
        "max_DD": max_drawdown(values),
        "positive_day_pct": round(float((daily > 0).mean()), 4) if not daily.empty else None,
        "day_block_ci_low": ci_low,
        "day_block_ci_high": ci_high,
    }


def grouped_stats(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    rows = []
    for keys, group in frame.groupby(columns, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        row = {column: ("UNKNOWN" if pd.isna(value) else value) for column, value in zip(columns, keys)}
        row.update(stats(group))
        rows.append(row)
    return pd.DataFrame(rows)


def serialize_for_parquet(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    for column in output.columns:
        if output[column].map(lambda value: isinstance(value, (dict, list, tuple, set))).any():
            output[column] = output[column].map(lambda value: json.dumps(sorted(value) if isinstance(value, set) else value, sort_keys=True, default=str))
    return output


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    candles_path = ROOT / "historical_intraday_5m_v2.parquet"
    levels_path = ROOT / "historical_expanded_option_levels_v2.parquet"
    daily_path = ROOT / "historical_daily_option_levels.parquet"
    missing = [str(path) for path in (candles_path, levels_path, daily_path) if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing required historical artifacts: {missing}")
    candles = pd.read_parquet(candles_path)
    levels = pd.read_parquet(levels_path)
    daily = pd.read_parquet(daily_path)
    candles = candles[candles["symbol"].isin(SYMBOLS)].copy()
    levels = levels[levels["symbol"].isin(SYMBOLS)].copy()
    daily = daily[daily["symbol"].isin(SYMBOLS)].copy()
    levels = levels[levels["gex_model_version"].isin(PRIMARY_HISTORICAL_GEX_MODELS)].copy()
    daily = daily[daily["model_version"].isin(PRIMARY_HISTORICAL_GEX_MODELS)].copy()
    candles["bar_end_dt"] = pd.to_datetime(candles["bar_end_utc"], utc=True, errors="coerce")
    candles["bar_start_dt"] = pd.to_datetime(candles["bar_start_utc"], utc=True, errors="coerce")
    candles["trade_date"] = candles["trade_date"].astype(str)
    for column in ("open", "high", "low", "close", "volume", "atr", "relative_volume"):
        candles[column] = pd.to_numeric(candles[column], errors="coerce")
    candles = candles.dropna(subset=["bar_end_dt", "open", "high", "low", "close"]).sort_values(["symbol", "bar_end_dt"])
    levels["trade_date"] = levels["trade_date"].astype(str)
    levels["strength_score"] = pd.to_numeric(levels["strength_score"], errors="coerce").fillna(0.0)
    levels["price"] = pd.to_numeric(levels["price"], errors="coerce")
    levels["zone_low"] = pd.to_numeric(levels["zone_low"], errors="coerce")
    levels["zone_high"] = pd.to_numeric(levels["zone_high"], errors="coerce")
    levels = levels.dropna(subset=["price", "zone_low", "zone_high"])
    daily["trade_date"] = daily["trade_date"].astype(str)
    return candles, levels, daily


def add_intraday_features(candles: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for symbol, group in candles.groupby("symbol", sort=False):
        group = group.sort_values("bar_end_dt").copy()
        group["trend_5m"] = [classify_trend(group["close"], 1, idx) for idx in range(len(group))]
        group["trend_15m"] = [classify_trend(group["close"], 3, idx) for idx in range(len(group))]
        group["trend_30m"] = [classify_trend(group["close"], 6, idx) for idx in range(len(group))]
        group["trend_1h"] = [classify_trend(group["close"], 12, idx) for idx in range(len(group))]
        day_frames = []
        for _, day in group.groupby("trade_date", sort=False):
            typical = (day["high"] + day["low"] + day["close"]) / 3
            volume = day["volume"].replace(0, np.nan).fillna(1)
            day = day.copy()
            day["rolling_vwap"] = (typical * volume).cumsum() / volume.cumsum()
            day["time_bucket"] = day["bar_end_dt"].map(time_bucket)
            day["bar_index"] = range(len(day))
            day_frames.append(day)
        frames.append(pd.concat(day_frames, ignore_index=True))
    enriched = pd.concat(frames, ignore_index=True)
    market_context = []
    for symbol in ("SPY", "QQQ"):
        cols = ["trade_date", "bar_index", "trend_15m", "trend_1h"]
        market_context.append(enriched[enriched["symbol"] == symbol][cols].rename(
            columns={"trend_15m": f"{symbol}_15m_trend", "trend_1h": f"{symbol}_1h_trend"}))
    result = enriched
    for context in market_context:
        result = result.merge(context, on=["trade_date", "bar_index"], how="left")
    return result


def source_family(row: pd.Series) -> str:
    metadata = parse_json(row.get("metadata_json"))
    return str(metadata.get("historical_level_family") or row.get("level_type") or "UNKNOWN")


def primary_level_type(types: set[str]) -> str:
    for candidate in ("GAMMA_FLIP", "CALL_WALL", "PUT_WALL", "GEX_OI_CLUSTER", "GEX_NODE", "OI_NODE"):
        if candidate in types:
            return candidate
    return sorted(types)[0] if types else "UNKNOWN"


def strength_tier(score: float) -> str:
    if score >= 0.85:
        return "LEVEL_TIER_S"
    if score >= 0.70:
        return "LEVEL_TIER_A"
    if score >= 0.55:
        return "LEVEL_TIER_B"
    return "LEVEL_TIER_C"


def cluster_levels(candles: pd.DataFrame, levels: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    valid_dates = set(zip(candles["symbol"], candles["trade_date"]))
    levels = levels[
        levels.apply(lambda row: (row["symbol"], row["trade_date"]) in valid_dates, axis=1)
        & (levels["control_type"].fillna("OPTIONS_LEVELS") == "OPTIONS_LEVELS")
        & (~levels["lookahead_risk"].fillna(False).astype(bool))
    ].copy()
    levels["source_family"] = levels.apply(source_family, axis=1)
    daily_lookup = daily.set_index(["symbol", "trade_date", "model_version"]).to_dict("index")
    atr_lookup = candles.groupby(["symbol", "trade_date"])["atr"].median().to_dict()
    rows: list[dict[str, Any]] = []
    for (symbol, trade_date, model), group in levels.groupby(["symbol", "trade_date", "gex_model_version"], sort=False):
        group = group.sort_values(["strength_score", "price"], ascending=[False, True]).copy()
        group["_rank"] = range(1, len(group) + 1)
        memberships_by_idx: dict[int, set[str]] = {}
        for idx, row in group.iterrows():
            memberships: set[str] = set()
            rank = int(row["_rank"])
            family = str(row["source_family"])
            level_type = str(row["level_type"])
            if rank <= 1:
                memberships.add("TOP_1_LEVEL")
            if rank <= 3:
                memberships.add("TOP_3_LEVELS")
            if rank <= 5:
                memberships.add("TOP_5_LEVELS")
            if level_type in {"GAMMA_FLIP", "CALL_WALL", "PUT_WALL"}:
                memberships.add(level_type)
            if family == "GEX_OI_CLUSTER":
                memberships.add("GEX_OI_CLUSTER")
            if family == "GEX_NODE" and rank <= 5:
                memberships.add("STRONGEST_ABSOLUTE_GAMMA_ZONES")
            if memberships:
                memberships_by_idx[idx] = memberships
        selected = group.loc[list(memberships_by_idx)].sort_values("price").copy() if memberships_by_idx else group.iloc[0:0].copy()
        if selected.empty:
            continue
        atr = max(float(atr_lookup.get((symbol, trade_date), 0.5) or 0.5), 0.01)
        cluster_width = max(0.05, 0.30 * atr)
        current: list[pd.Series] = []
        last_price: float | None = None
        clusters: list[list[pd.Series]] = []
        for _, row in selected.iterrows():
            price = float(row["price"])
            if current and last_price is not None and abs(price - last_price) > cluster_width:
                clusters.append(current)
                current = []
            current.append(row)
            last_price = price
        if current:
            clusters.append(current)
        daily_row = daily_lookup.get((symbol, trade_date, model), {})
        for cluster in clusters:
            prices = [float(item["price"]) for item in cluster]
            strengths = [float(item["strength_score"]) for item in cluster]
            weights = [max(value, 0.01) for value in strengths]
            center = float(np.average(prices, weights=weights))
            low = min(float(item["zone_low"]) for item in cluster)
            high = max(float(item["zone_high"]) for item in cluster)
            types = {str(item["source_family"]) for item in cluster} | {str(item["level_type"]) for item in cluster}
            memberships = set()
            ranks = []
            for item in cluster:
                memberships |= memberships_by_idx.get(int(item.name), set())
                ranks.append(int(item["_rank"]))
            score = min(1.0, max(strengths) + 0.03 * min(len(cluster) - 1, 3))
            rows.append({
                "cluster_id": "hcl_" + stable_hash(symbol, trade_date, model, round(center, 3), sorted(types), sorted(memberships)),
                "symbol": symbol,
                "trade_date": trade_date,
                "gex_model_version": model,
                "center": round(center, 6),
                "low": round(low, 6),
                "high": round(high, 6),
                "strength": round(score, 6),
                "tier": strength_tier(score),
                "level_type": primary_level_type(types),
                "source_level_types": tuple(sorted(types)),
                "level_filter_memberships": tuple(sorted(memberships)),
                "component_count": len(cluster),
                "min_source_rank": min(ranks),
                "source_chain_date": str(cluster[0].get("snapshot_date")) if cluster[0].get("snapshot_date") is not None else None,
                "gamma_regime": str(daily_row.get("gamma_regime") or "UNKNOWN"),
                "historical_data_tier": str(cluster[0].get("historical_data_tier") or "H2_EOD_FULL_CHAIN"),
                "source_quality": str(cluster[0].get("source_quality") or "EXPLORATORY_RESEARCH"),
                "lookahead_safe": True,
                "intraday_persistence_state": "HISTORICALLY_UNAVAILABLE",
                "level_strength_model_version": LEVEL_STRENGTH_VERSION,
            })
    return pd.DataFrame(rows)


def detect_interactions(previous: pd.Series, current: pd.Series, level: LevelCluster | dict[str, Any]) -> list[dict[str, str]]:
    low = float(level.low if isinstance(level, LevelCluster) else level["low"])
    high = float(level.high if isinstance(level, LevelCluster) else level["high"])
    center = float(level.center if isinstance(level, LevelCluster) else level["center"])
    prev_close = float(previous["close"])
    close = float(current["close"])
    prev_low = float(previous["low"])
    prev_high = float(previous["high"])
    bar_low = float(current["low"])
    bar_high = float(current["high"])
    interactions: list[dict[str, str]] = []
    if min(prev_low, bar_low) < low and close > high and prev_close <= center:
        interactions.append({"direction": "LONG", "structural_family": "RECLAIM", "confirmation_state": "LONG_RECLAIM"})
    if max(prev_high, bar_high) > high and close < low and prev_close >= center:
        interactions.append({"direction": "SHORT", "structural_family": "RECLAIM", "confirmation_state": "SHORT_RECLAIM"})
    if bar_low <= high and close > high and prev_close >= center:
        interactions.append({"direction": "LONG", "structural_family": "REJECTION", "confirmation_state": "LONG_REJECTION"})
    if bar_high >= low and close < low and prev_close <= center:
        interactions.append({"direction": "SHORT", "structural_family": "REJECTION", "confirmation_state": "SHORT_REJECTION"})
    if prev_close > high and close > high and bar_low >= low:
        interactions.append({"direction": "LONG", "structural_family": "BREAKOUT", "confirmation_state": "BREAKOUT_LONG"})
    if prev_close < low and close < low and bar_high <= high:
        interactions.append({"direction": "SHORT", "structural_family": "BREAKOUT", "confirmation_state": "BREAKOUT_SHORT"})
    dedup = []
    seen = set()
    for item in interactions:
        key = (item["direction"], item["structural_family"])
        if key not in seen:
            seen.add(key)
            dedup.append(item)
    return dedup


def aggregate_bar(group: pd.DataFrame, start: int, end: int) -> dict[str, float] | None:
    if start < 0 or end >= len(group):
        return None
    rows = group.iloc[start:end + 1]
    if rows.empty:
        return None
    return {
        "open": float(rows["open"].iloc[0]),
        "high": float(rows["high"].max()),
        "low": float(rows["low"].min()),
        "close": float(rows["close"].iloc[-1]),
        "volume": float(rows["volume"].sum()),
        "relative_volume": float(rows["relative_volume"].iloc[-1] or 1.0),
    }


def variant_confirmation_ok(
    variant_key: str,
    event: dict[str, Any],
    group: pd.DataFrame,
    idx: int,
    level: dict[str, Any] | None = None,
) -> tuple[bool, list[str]]:
    spec = VARIANTS[variant_key]
    reasons = []
    if spec["requires_15m"]:
        current = aggregate_bar(group, idx - 2, idx)
        previous = aggregate_bar(group, idx - 5, idx - 3)
        if current is None or previous is None:
            reasons.append("15m confirmation unavailable")
        else:
            level_view = level or {
                "low": event["zone_low"],
                "high": event["zone_high"],
                "center": event["level_price"],
            }
            interactions = detect_interactions(pd.Series(previous), pd.Series(current), level_view)
            if not any(item["direction"] == event["direction"] and item["structural_family"] == event["structural_family"] for item in interactions):
                reasons.append("15m confirmation did not match 5m parent interaction")
    if spec["requires_30m_context"] and idx < 6:
        reasons.append("30m context unavailable")
    return not reasons, reasons


def make_events(candles: pd.DataFrame, clusters: pd.DataFrame) -> pd.DataFrame:
    events = []
    clusters_by_key = {
        key: [LevelCluster(**row) for row in group.to_dict("records")]
        for key, group in clusters.groupby(["symbol", "trade_date", "gex_model_version"], sort=False)
    }
    model_versions = sorted(clusters["gex_model_version"].unique())
    for (symbol, trade_date), group in candles.groupby(["symbol", "trade_date"], sort=False):
        group = group.sort_values("bar_end_dt").reset_index(drop=True)
        if len(group) < 8:
            continue
        highs = group["high"].astype(float).to_numpy()
        lows = group["low"].astype(float).to_numpy()
        closes = group["close"].astype(float).to_numpy()
        atrs = group["atr"].fillna(0.01).astype(float).to_numpy()
        relvols = group["relative_volume"].fillna(1.0).astype(float).to_numpy()
        candidate_idx = np.arange(1, len(group) - 1)
        prev_idx = candidate_idx - 1
        prev_high = highs[prev_idx]
        prev_low = lows[prev_idx]
        prev_close = closes[prev_idx]
        cur_high = highs[candidate_idx]
        cur_low = lows[candidate_idx]
        cur_close = closes[candidate_idx]
        for model in model_versions:
            day_levels = clusters_by_key.get((symbol, trade_date, model), [])
            if not day_levels:
                continue
            last_episode_by_key: dict[tuple[str, str, str], int] = {}
            all_centers = sorted({level.center for level in day_levels})
            for level in day_levels:
                touch = (np.maximum(prev_high, cur_high) >= level.low) & (np.minimum(prev_low, cur_low) <= level.high)
                if not bool(touch.any()):
                    continue
                conditions = [
                    ("LONG", "RECLAIM", "LONG_RECLAIM", touch & (np.minimum(prev_low, cur_low) < level.low) & (cur_close > level.high) & (prev_close <= level.center)),
                    ("SHORT", "RECLAIM", "SHORT_RECLAIM", touch & (np.maximum(prev_high, cur_high) > level.high) & (cur_close < level.low) & (prev_close >= level.center)),
                    ("LONG", "REJECTION", "LONG_REJECTION", touch & (np.minimum(prev_low, cur_low) < level.low) & (cur_close > level.center) & (prev_close > level.center)),
                    ("SHORT", "REJECTION", "SHORT_REJECTION", touch & (np.maximum(prev_high, cur_high) > level.high) & (cur_close < level.center) & (prev_close < level.center)),
                    ("LONG", "BREAKOUT", "BREAKOUT_LONG", touch & (prev_close <= level.high) & (cur_close > level.high)),
                    ("SHORT", "BREAKOUT", "BREAKOUT_SHORT", touch & (prev_close >= level.low) & (cur_close < level.low)),
                ]
                for direction, family, confirmation_state, mask in conditions:
                    idx_values = candidate_idx[np.asarray(mask, dtype=bool)]
                    if len(idx_values) == 0:
                        continue
                    for idx in idx_values:
                        current = group.iloc[int(idx)]
                        if current["time_bucket"] == "OUTSIDE_RTH":
                            continue
                        previous = group.iloc[int(idx) - 1]
                        episode_key = (level.cluster_id, direction, family)
                        if idx - last_episode_by_key.get(episode_key, -999) < 12:
                            continue
                        last_episode_by_key[episode_key] = idx
                        side = 1 if direction == "LONG" else -1
                        structural_stop = (
                            min(float(previous["low"]), float(current["low"]), level.low) - float(current["atr"]) * 0.30
                            if direction == "LONG"
                            else max(float(previous["high"]), float(current["high"]), level.high) + float(current["atr"]) * 0.30
                        )
                        entry = float(current["close"])
                        risk = abs(entry - structural_stop)
                        structural_targets = [
                            center for center in all_centers
                            if (center > entry if direction == "LONG" else center < entry)
                        ]
                        structural_targets = sorted(structural_targets, reverse=direction == "SHORT")[:3]
                        event_id = "p4ah_evt_" + stable_hash(symbol, trade_date, model, level.cluster_id, direction,
                                                             family, floor_episode(current["bar_end_dt"]))
                        events.append({
                            "parent_event_id": event_id,
                            "namespace": PHASE_NAMESPACE,
                            "symbol": symbol,
                            "trade_date": trade_date,
                            "bar_index": int(idx),
                            "confirmation_timestamp_utc": current["bar_end_dt"],
                            "confirmation_timestamp_et": current["bar_end_dt"].tz_convert(EASTERN).isoformat(),
                            "time_bucket": time_bucket(current["bar_end_dt"]),
                            "gex_model_version": model,
                            "gamma_regime": level.gamma_regime,
                            "level_cluster_id": level.cluster_id,
                            "level_price": level.center,
                            "zone_low": level.low,
                            "zone_high": level.high,
                            "level_strength": level.strength,
                            "level_tier": level.tier,
                            "level_type": level.level_type,
                            "source_level_types": level.source_level_types,
                            "level_filter_memberships": level.level_filter_memberships,
                            "source_chain_date": level.source_chain_date,
                            "historical_data_tier": level.historical_data_tier,
                            "source_quality": level.source_quality,
                            "lookahead_safe": level.lookahead_safe,
                            "intraday_persistence_state": "HISTORICALLY_UNAVAILABLE",
                            "direction": direction,
                            "structural_family": family,
                            "confirmation_state": confirmation_state,
                            "interaction_episode": floor_episode(current["bar_end_dt"]),
                            "entry_reference_price": entry,
                            "structural_stop": round(structural_stop, 6),
                            "initial_risk_reference": round(risk, 6),
                            "confirmation_relative_volume": float(current["relative_volume"] or 1.0),
                            "confirmation_atr": float(current["atr"] or 0.01),
                            "trend_5m": current["trend_5m"],
                            "trend_15m": current["trend_15m"],
                            "trend_30m": current["trend_30m"],
                            "trend_1h": current["trend_1h"],
                            "SPY_15m_trend": current.get("SPY_15m_trend", "UNKNOWN"),
                            "QQQ_15m_trend": current.get("QQQ_15m_trend", "UNKNOWN"),
                            "market_alignment": alignment(direction, current.get("QQQ_15m_trend") if symbol == "QQQ" else current.get("SPY_15m_trend", "UNKNOWN")),
                            "distance_to_level_ATR": round(abs(entry - level.center) / max(float(current["atr"] or 0.01), 0.01), 4),
                            "approach_velocity": round(abs(float(current["close"]) - float(previous["close"])) / max(float(current["atr"] or 0.01), 0.01), 4),
                            "sweep_depth_ATR": round((max(0.0, level.low - min(float(previous["low"]), float(current["low"]))) if direction == "LONG"
                                                      else max(0.0, max(float(previous["high"]), float(current["high"])) - level.high)) / max(float(current["atr"] or 0.01), 0.01), 4),
                            "structural_targets": tuple(round(value, 6) for value in structural_targets),
                            "event_dedup_version": EVENT_DEDUP_VERSION,
                            "replay_version": REPLAY_VERSION,
                        })
    return pd.DataFrame(events).drop_duplicates("parent_event_id") if events else pd.DataFrame()


def control_level(
    event: dict[str, Any],
    day_group: pd.DataFrame,
    symbol_history: pd.DataFrame,
    control_type: str,
) -> dict[str, Any] | None:
    idx = int(event["bar_index"])
    current = day_group.iloc[idx]
    entry = float(event["entry_reference_price"])
    width = max(abs(float(event["zone_high"]) - float(event["zone_low"])) / 2, float(event["confirmation_atr"]) * 0.05, 0.01)
    if control_type == "MATCHED_RANDOM_NEARBY_LEVEL":
        distance = abs(entry - float(event["level_price"]))
        rng = random.Random(int(stable_hash(event["parent_event_id"], control_type, length=8), 16))
        center = entry + rng.choice([-1, 1]) * max(distance, float(event["confirmation_atr"]) * 0.10)
    elif control_type == "PREVIOUS_DAY_HIGH":
        prev = previous_day_frame(symbol_history, event["trade_date"])
        if prev is None or prev.empty:
            return None
        center = float(prev["high"].max())
    elif control_type == "PREVIOUS_DAY_LOW":
        prev = previous_day_frame(symbol_history, event["trade_date"])
        if prev is None or prev.empty:
            return None
        center = float(prev["low"].min())
    elif control_type == "VWAP":
        center = float(current["rolling_vwap"])
    elif control_type == "ROUND_NUMBER":
        inc = 5.0 if entry >= 100 else 1.0
        center = round(entry / inc) * inc
    else:
        return None
    return {"center": round(center, 6), "low": round(center - width, 6), "high": round(center + width, 6)}


def previous_day_frame(symbol_group: pd.DataFrame, trade_date: str) -> pd.DataFrame | None:
    prior_dates = sorted(day for day in symbol_group["trade_date"].unique() if str(day) < str(trade_date))
    if not prior_dates:
        return None
    return symbol_group[symbol_group["trade_date"] == prior_dates[-1]]


def entry_qualification(entry_variant: str, event: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons = []
    if entry_variant == "ENTRY_3_SWEEP_RECLAIM_RETEST" and event["structural_family"] != "RECLAIM":
        reasons.append("ENTRY_3 requires RECLAIM")
    if entry_variant == "ENTRY_4_VOLUME_CONFIRMATION" and float(event["confirmation_relative_volume"]) < 1.25:
        reasons.append("relative volume confirmation missing")
    if entry_variant == "ENTRY_5_MARKET_ALIGNMENT" and event.get("market_alignment") == "AGAINST_MARKET_TREND":
        reasons.append("market alignment missing")
    return not reasons, reasons


def compute_stop(event: dict[str, Any], stop_variant: str, level: dict[str, Any]) -> float:
    direction = event["direction"]
    atr = max(float(event["confirmation_atr"]), 0.01)
    structural = float(event["structural_stop"])
    if stop_variant == "STOP_A_CURRENT_STRUCTURAL":
        return structural
    if stop_variant == "STOP_E_ZONE_INVALIDATION":
        return float(level["low"]) if direction == "LONG" else float(level["high"])
    buffer = STOP_VARIANTS[stop_variant]
    assert buffer is not None
    return (min(structural, float(level["low"])) - atr * buffer) if direction == "LONG" else (max(structural, float(level["high"])) + atr * buffer)


def compute_control_structural_stop(event: dict[str, Any], group: pd.DataFrame, level: dict[str, Any]) -> float:
    idx = int(event["bar_index"])
    previous = group.iloc[max(0, idx - 1)]
    current = group.iloc[idx]
    atr = max(float(event["confirmation_atr"]), 0.01)
    if event["direction"] == "LONG":
        return min(float(previous["low"]), float(current["low"]), float(level["low"])) - atr * 0.30
    return max(float(previous["high"]), float(current["high"]), float(level["high"])) + atr * 0.30


def r_price(entry: float, risk: float, direction: str, multiple: float) -> float:
    return entry + (1 if direction == "LONG" else -1) * risk * multiple


def targets_for(management: str, event: dict[str, Any], entry: float, risk: float) -> list[tuple[float, float, str, float]]:
    direction = event["direction"]
    if management == "TM_STRUCTURE_TARGETS":
        raw_targets = list(event.get("structural_targets") or [])
        targets = []
        for target, fraction, label in zip(raw_targets[:3], (0.33, 0.33, 0.34), ("STRUCTURE_TP1", "STRUCTURE_TP2", "STRUCTURE_TP3")):
            multiple = abs(float(target) - entry) / risk if risk else 0.0
            if multiple > 0:
                targets.append((float(target), fraction, label, multiple))
        if targets:
            return targets
    return [(r_price(entry, risk, direction, multiple), fraction, label, multiple)
            for multiple, fraction, label in MANAGEMENT_VARIANTS.get(management, MANAGEMENT_VARIANTS["TM_V0_CURRENT"])]


def find_entry(entry_variant: str, event: dict[str, Any], group: pd.DataFrame, level: dict[str, Any]) -> tuple[int | None, float | None, str]:
    idx = int(event["bar_index"])
    if idx + 1 >= len(group):
        return None, None, "no_future_entry_bar"
    direction = event["direction"]
    if entry_variant in {"ENTRY_1_CLOSE_RECLAIM", "ENTRY_4_VOLUME_CONFIRMATION", "ENTRY_5_MARKET_ALIGNMENT"}:
        return idx + 1, float(group.iloc[idx + 1]["open"]), "next_bar_open_after_confirmation"
    for j in range(idx + 1, min(idx + 4, len(group))):
        bar = group.iloc[j]
        if float(bar["low"]) <= float(level["high"]) and float(bar["high"]) >= float(level["low"]):
            fill = max(float(level["high"]), float(bar["open"])) if direction == "LONG" else min(float(level["low"]), float(bar["open"]))
            return j, fill, "retest_fill_after_confirmation"
    return None, None, "retest_not_seen_before_expiry"


def first_true_index(mask: np.ndarray) -> int | None:
    if len(mask) == 0 or not bool(mask.any()):
        return None
    return int(np.argmax(mask))


def first_elapsed_at_or_above(elapsed: np.ndarray, values: np.ndarray, threshold: float) -> float | None:
    idx = first_true_index(values >= threshold)
    return float(elapsed[idx]) if idx is not None else None


def holding_result_at(elapsed: np.ndarray, closes: np.ndarray, entry: float, risk: float, side: int, minutes: int) -> float | None:
    idx = first_true_index(elapsed >= minutes)
    return ((float(closes[idx]) - entry) * side) / risk if idx is not None else None


def simulate_branch(event: dict[str, Any], group: pd.DataFrame, *, strategy_variant: str, entry_variant: str,
                    stop_variant: str, management: str, control_type: str | None = None,
                    control: dict[str, Any] | None = None) -> dict[str, Any]:
    level = control or {"center": event["level_price"], "low": event["zone_low"], "high": event["zone_high"]}
    if control is None and "_variant_results" in event:
        variant_ok, variant_reasons = event["_variant_results"][strategy_variant]
    else:
        variant_ok, variant_reasons = variant_confirmation_ok(strategy_variant, event, group, int(event["bar_index"]), level)
    if "_entry_results" in event:
        entry_ok, entry_reasons = event["_entry_results"][entry_variant]
    else:
        entry_ok, entry_reasons = entry_qualification(entry_variant, event)
    branch_id = "p4ah_br_" + stable_hash(event["parent_event_id"], strategy_variant, entry_variant, stop_variant, management, control_type or "OPTIONS")
    base = {
        "branch_id": branch_id,
        "parent_event_id": event["parent_event_id"],
        "namespace": PHASE_NAMESPACE,
        "symbol": event["symbol"],
        "trade_date": event["trade_date"],
        "strategy_variant": strategy_variant,
        "strategy_variant_label": VARIANTS[strategy_variant]["variant"],
        "confirmation_tf": VARIANTS[strategy_variant]["confirmation_tf"],
        "execution_tf": VARIANTS[strategy_variant]["execution_tf"],
        "context_tf": VARIANTS[strategy_variant]["context_tf"],
        "entry_variant": entry_variant,
        "stop_variant": stop_variant,
        "management_variant": management,
        "is_control": control_type is not None,
        "control_type": control_type or "OPTIONS_STRONG_LEVEL",
        "direction": event["direction"],
        "structural_family": event["structural_family"],
        "level_type": event["level_type"],
        "level_tier": event["level_tier"],
        "level_filter_memberships": event["level_filter_memberships"],
        "time_bucket": event["time_bucket"],
        "gamma_regime": event["gamma_regime"],
        "gex_model_version": event["gex_model_version"],
        "historical_data_tier": event["historical_data_tier"],
        "source_quality": event["source_quality"],
        "lookahead_safe": bool(event["lookahead_safe"]),
        "intraday_persistence_state": "HISTORICALLY_UNAVAILABLE",
        "variant_C_D_unavailable_reason": None,
        "entry_prerequisite_failures": tuple(variant_reasons + entry_reasons),
        "status": "not_qualified",
        "exit_reason": "; ".join(variant_reasons + entry_reasons) or None,
        "result_R": None,
        "MFE_R": None,
        "MAE_R": None,
        "time_to_MFE_minutes": None,
        "time_to_0_5R_minutes": None,
        "time_to_1R_minutes": None,
        "time_to_1_5R_minutes": None,
        "holding_15m_R": None,
        "holding_30m_R": None,
        "holding_60m_R": None,
        "holding_120m_R": None,
        "holding_240m_R": None,
        "holding_EOD_R": None,
        "duration_minutes": None,
        "replay_version": REPLAY_VERSION,
        "branch_matrix_version": BRANCH_MATRIX_VERSION,
    }
    if not variant_ok or not entry_ok:
        return base
    entry_idx, entry, entry_reason = find_entry(entry_variant, event, group, level)
    if entry_idx is None or entry is None:
        return {**base, "status": "expired", "exit_reason": entry_reason, "result_R": 0.0, "MFE_R": 0.0, "MAE_R": 0.0}
    slippage_bps = 3
    entry = entry + (1 if event["direction"] == "LONG" else -1) * entry * slippage_bps / 10000
    stop = compute_control_structural_stop(event, group, level) if control is not None and stop_variant == "STOP_A_CURRENT_STRUCTURAL" else compute_stop(event, stop_variant, level)
    risk = abs(entry - stop)
    if risk <= 0 or (event["direction"] == "LONG" and stop >= entry) or (event["direction"] == "SHORT" and stop <= entry):
        return {**base, "status": "expired", "exit_reason": "invalid_stop_or_zero_risk", "result_R": 0.0, "MFE_R": 0.0, "MAE_R": 0.0}
    side = 1 if event["direction"] == "LONG" else -1
    arrays = group.attrs.get("_p4ah_arrays") or {}
    high_arr = arrays.get("high")
    low_arr = arrays.get("low")
    close_arr = arrays.get("close")
    bar_start_arr = arrays.get("bar_start")
    bar_end_arr = arrays.get("bar_end")
    if high_arr is None or low_arr is None or close_arr is None or bar_start_arr is None or bar_end_arr is None:
        high_arr = group["high"].astype(float).to_numpy()
        low_arr = group["low"].astype(float).to_numpy()
        close_arr = group["close"].astype(float).to_numpy()
        bar_start_arr = list(group["bar_start_dt"])
        bar_end_arr = list(group["bar_end_dt"])
    opened_at = bar_start_arr[entry_idx]
    future_high = high_arr[entry_idx:]
    future_low = low_arr[entry_idx:]
    future_close = close_arr[entry_idx:]
    future_bar_end = bar_end_arr[entry_idx:]
    elapsed_minutes = np.array([(bar_end - opened_at).total_seconds() / 60 for bar_end in future_bar_end], dtype=float)
    favorable_prices = future_high if side == 1 else future_low
    adverse_prices = future_low if side == 1 else future_high
    favorable_r_path = ((favorable_prices - entry) * side) / risk
    adverse_r_path = ((entry - adverse_prices) * side) / risk
    max_favorable_idx = int(np.nanargmax(favorable_r_path)) if len(favorable_r_path) else 0
    mfe = max(0.0, float(favorable_r_path[max_favorable_idx])) if len(favorable_r_path) else 0.0
    mae = max(0.0, float(np.nanmax(adverse_r_path))) if len(adverse_r_path) else 0.0
    realized = 0.0
    remaining = 1.0
    stop_current = stop
    status = "open"
    exit_reason = None
    closed_at = None
    time_to_mfe = float(elapsed_minutes[max_favorable_idx]) if len(elapsed_minutes) and mfe > 0 else None
    threshold_times = {
        "time_to_0_5R_minutes": first_elapsed_at_or_above(elapsed_minutes, favorable_r_path, 0.5),
        "time_to_1R_minutes": first_elapsed_at_or_above(elapsed_minutes, favorable_r_path, 1.0),
        "time_to_1_5R_minutes": first_elapsed_at_or_above(elapsed_minutes, favorable_r_path, 1.5),
    }
    horizon_results = {
        "holding_15m_R": holding_result_at(elapsed_minutes, future_close, entry, risk, side, 15),
        "holding_30m_R": holding_result_at(elapsed_minutes, future_close, entry, risk, side, 30),
        "holding_60m_R": holding_result_at(elapsed_minutes, future_close, entry, risk, side, 60),
        "holding_120m_R": holding_result_at(elapsed_minutes, future_close, entry, risk, side, 120),
        "holding_240m_R": holding_result_at(elapsed_minutes, future_close, entry, risk, side, 240),
    }
    touched_labels: set[str] = set()
    targets = targets_for(management, event, entry, risk)
    relative_start = 0
    while status == "open" and relative_start < len(future_close):
        stop_hits = (future_low[relative_start:] <= stop_current) if side == 1 else (future_high[relative_start:] >= stop_current)
        stop_rel = first_true_index(stop_hits)
        target_candidates: list[tuple[int, float, float, str, float]] = []
        for target_price, fraction, label, target_r in targets:
            if label in touched_labels or remaining <= 0:
                continue
            target_hits = (future_high[relative_start:] >= target_price) if side == 1 else (future_low[relative_start:] <= target_price)
            target_rel = first_true_index(target_hits)
            if target_rel is not None:
                target_candidates.append((target_rel, target_price, fraction, label, target_r))
        next_target_rel = min((item[0] for item in target_candidates), default=None)
        if stop_rel is not None and (next_target_rel is None or stop_rel <= next_target_rel):
            realized += ((stop_current - entry) * side / risk) * remaining
            status = "closed"
            exit_reason = "breakeven_stop" if abs(stop_current - entry) <= 0.01 else "stop_loss"
            closed_at = future_bar_end[relative_start + stop_rel]
            break
        if next_target_rel is None:
            break
        target_abs = relative_start + next_target_rel
        last_label_hit = None
        for target_price, fraction, label, target_r in targets:
            if label in touched_labels or remaining <= 0:
                continue
            target_hit_at_bar = float(future_high[target_abs]) >= target_price if side == 1 else float(future_low[target_abs]) <= target_price
            if not target_hit_at_bar:
                continue
            qty = min(remaining, fraction)
            realized += target_r * qty
            remaining = round(remaining - qty, 8)
            touched_labels.add(label)
            last_label_hit = label
            if label in {"TP1_PARTIAL", "HALF_0_5R", "HALF_1R", "STRUCTURE_TP1"} or management in {"TM_V3_TP1_PLUS_RUNNER", "TM_HALF_0_5R_RUNNER", "TM_HALF_1R_RUNNER", "TM_STRUCTURE_TARGETS"}:
                stop_current = entry
        if remaining <= 0:
            status = "closed"
            exit_reason = last_label_hit or "target_exit"
            closed_at = future_bar_end[target_abs]
            break
        relative_start = target_abs + 1
    if status != "closed":
        realized += ((float(close_arr[-1]) - entry) * side / risk) * remaining
        status = "censored"
        exit_reason = "EOD"
        closed_at = bar_end_arr[-1]
    holding_eod = ((float(close_arr[-1]) - entry) * side) / risk
    duration = (closed_at - opened_at).total_seconds() / 60 if closed_at is not None else None
    return {
        **base,
        "status": status,
        "exit_reason": exit_reason,
        "entry_reason": entry_reason,
        "entry_timestamp_utc": opened_at.isoformat(),
        "closed_at_utc": closed_at.isoformat() if closed_at is not None else None,
        "entry": round(entry, 6),
        "stop": round(stop, 6),
        "initial_risk": round(risk, 6),
        "result_R": round(realized, 6),
        "MFE_R": round(mfe, 6),
        "MAE_R": round(mae, 6),
        "time_to_MFE_minutes": round(time_to_mfe, 2) if time_to_mfe is not None else None,
        **{key: round(value, 2) if value is not None else None for key, value in threshold_times.items()},
        **{key: round(value, 6) if value is not None else None for key, value in horizon_results.items()},
        "holding_EOD_R": round(holding_eod, 6),
        "duration_minutes": round(duration, 2) if duration is not None else None,
        "slippage_bps": slippage_bps,
        "targets_R": tuple(round(item[3], 4) for item in targets),
    }


def option_branch_specs() -> list[tuple[str, str, str, str]]:
    """Controlled matrix: requested one-factor sweeps, not full Cartesian explosion."""
    specs: set[tuple[str, str, str, str]] = set()
    for strategy_variant in VARIANTS:
        for management in MANAGEMENT_VARIANTS:
            specs.add((strategy_variant, "ENTRY_1_CLOSE_RECLAIM", "STOP_A_CURRENT_STRUCTURAL", management))
    baseline_strategy = "VARIANT_A_HIST_5M_CONFIRM_5M_ENTRY"
    for entry_variant in ENTRY_VARIANTS:
        specs.add((baseline_strategy, entry_variant, "STOP_A_CURRENT_STRUCTURAL", "TM_V0_CURRENT"))
    for stop_variant in STOP_VARIANTS:
        specs.add((baseline_strategy, "ENTRY_1_CLOSE_RECLAIM", stop_variant, "TM_V0_CURRENT"))
    return sorted(specs)


def control_branch_specs() -> list[tuple[str, str, str, str]]:
    return [("VARIANT_A_HIST_5M_CONFIRM_5M_ENTRY", "ENTRY_1_CLOSE_RECLAIM", "STOP_A_CURRENT_STRUCTURAL", "TM_V0_CURRENT")]


def prepare_day_group(group: pd.DataFrame) -> pd.DataFrame:
    prepared = group.sort_values("bar_end_dt").reset_index(drop=True).copy()
    prepared.attrs["_p4ah_arrays"] = {
        "high": prepared["high"].astype(float).to_numpy(),
        "low": prepared["low"].astype(float).to_numpy(),
        "close": prepared["close"].astype(float).to_numpy(),
        "bar_start": list(prepared["bar_start_dt"]),
        "bar_end": list(prepared["bar_end_dt"]),
    }
    return prepared


def make_branches(candles: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    bars_by_symbol = {symbol: group.sort_values(["trade_date", "bar_end_dt"]).copy() for symbol, group in candles.groupby("symbol")}
    bars_by_key = {(symbol, day): prepare_day_group(group)
                   for (symbol, day), group in candles.groupby(["symbol", "trade_date"])}
    rows: list[dict[str, Any]] = []
    option_specs = option_branch_specs()
    matched_control_specs = control_branch_specs()
    total_events = len(events)
    for event_number, event in enumerate(events.to_dict("records"), 1):
        if event_number == 1 or event_number % 500 == 0:
            print(f"make_branches {event_number}/{total_events}", flush=True)
        group = bars_by_key.get((event["symbol"], event["trade_date"]))
        if group is None or group.empty:
            continue
        event["_variant_results"] = {strategy_variant: variant_confirmation_ok(strategy_variant, event, group, int(event["bar_index"]))
                                     for strategy_variant in VARIANTS}
        event["_entry_results"] = {entry_variant: entry_qualification(entry_variant, event)
                                   for entry_variant in ENTRY_VARIANTS}
        for strategy_variant, entry_variant, stop_variant, management in option_specs:
            rows.append(simulate_branch(event, group, strategy_variant=strategy_variant,
                                        entry_variant=entry_variant, stop_variant=stop_variant,
                                        management=management))
        symbol_history = bars_by_symbol[event["symbol"]]
        for control_type in CONTROL_TYPES:
            control = control_level(event, group, symbol_history, control_type)
            if control is None:
                continue
            for strategy_variant, entry_variant, stop_variant, management in matched_control_specs:
                rows.append(simulate_branch(event, group, strategy_variant=strategy_variant,
                                            entry_variant=entry_variant, stop_variant=stop_variant,
                                            management=management, control_type=control_type,
                                            control=control))
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def split_discovery_holdout(branches: pd.DataFrame) -> pd.DataFrame:
    if branches.empty:
        return branches
    days = sorted(branches["trade_date"].dropna().unique())
    cutoff_index = max(1, int(len(days) * 0.60))
    discovery_days = set(days[:cutoff_index])
    output = branches.copy()
    output["sample_split"] = output["trade_date"].map(lambda day: "DISCOVERY" if day in discovery_days else "HOLDOUT")
    return output


def comparison_by_exploded_membership(branches: pd.DataFrame, membership_column: str) -> pd.DataFrame:
    if branches.empty:
        return pd.DataFrame()
    rows = []
    for _, row in branches.iterrows():
        value = row.get(membership_column)
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                memberships = parsed if isinstance(parsed, list) else [value]
            except json.JSONDecodeError:
                memberships = [item.strip() for item in value.split(",") if item.strip()]
        elif isinstance(value, (list, tuple, set)):
            memberships = list(value)
        else:
            memberships = ["UNKNOWN"]
        for item in memberships or ["UNKNOWN"]:
            payload = row.to_dict()
            payload["level_filter"] = item
            rows.append(payload)
    return grouped_stats(pd.DataFrame(rows), ["level_filter", "strategy_variant", "management_variant"])


def holding_horizon(branches: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for horizon in ("holding_15m_R", "holding_30m_R", "holding_60m_R", "holding_120m_R", "holding_240m_R", "holding_EOD_R"):
        subset = branches[pd.to_numeric(branches.get(horizon), errors="coerce").notna()].copy()
        if subset.empty:
            continue
        subset["result_R"] = pd.to_numeric(subset[horizon], errors="coerce")
        subset["status"] = "closed"
        rows.append({"holding_horizon": horizon.replace("holding_", "").replace("_R", ""), **stats(subset)})
    return pd.DataFrame(rows)


def discovery_holdout(branches: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if branches.empty:
        return pd.DataFrame()
    columns = ["strategy_variant", "entry_variant", "stop_variant", "management_variant", "direction", "structural_family"]
    for keys, group in branches[~branches["is_control"]].groupby(columns, dropna=False):
        base = dict(zip(columns, keys))
        for split, split_group in group.groupby("sample_split"):
            rows.append({**base, "sample_split": split, **stats(split_group)})
    return pd.DataFrame(rows)


def walkforward(branches: pd.DataFrame) -> pd.DataFrame:
    if branches.empty:
        return pd.DataFrame()
    output = []
    frame = branches[~branches["is_control"]].copy()
    frame["month"] = frame["trade_date"].astype(str).str.slice(0, 7)
    months = sorted(frame["month"].unique())
    for start in range(0, max(0, len(months) - 8), 3):
        discovery_months = months[start:start + 6]
        holdout_months = months[start + 6:start + 9]
        if len(discovery_months) < 6 or len(holdout_months) < 3:
            continue
        discovery = frame[frame["month"].isin(discovery_months)]
        holdout = frame[frame["month"].isin(holdout_months)]
        candidates = grouped_stats(discovery, ["strategy_variant", "entry_variant", "management_variant", "direction"])
        candidates = candidates[(pd.to_numeric(candidates["expectancy_R"], errors="coerce") > 0) & (candidates["PF"].map(lambda value: value == "infinite" or safe_float(value, 0) > 1))]
        if candidates.empty:
            output.append({"window": f"{discovery_months[0]}..{discovery_months[-1]}->{holdout_months[0]}..{holdout_months[-1]}",
                           "discovery_winners": 0, "holdout_survivors": 0})
            continue
        survivors = 0
        for _, candidate in candidates.iterrows():
            mask = (
                (holdout["strategy_variant"] == candidate["strategy_variant"])
                & (holdout["entry_variant"] == candidate["entry_variant"])
                & (holdout["management_variant"] == candidate["management_variant"])
                & (holdout["direction"] == candidate["direction"])
            )
            holdout_stats = stats(holdout[mask])
            if holdout_stats["N"] and holdout_stats["expectancy_R"] and holdout_stats["expectancy_R"] > 0 and (
                holdout_stats["PF"] == "infinite" or safe_float(holdout_stats["PF"], 0) > 1
            ):
                survivors += 1
        output.append({"window": f"{discovery_months[0]}..{discovery_months[-1]}->{holdout_months[0]}..{holdout_months[-1]}",
                       "discovery_winners": int(len(candidates)), "holdout_survivors": int(survivors)})
    return pd.DataFrame(output)


def robustness(branches: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    rows = []
    for keys, group in branches.groupby(group_cols, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        subset = group[group["status"].isin(RESOLVED)].copy()
        if subset.empty:
            continue
        base = dict(zip(group_cols, keys))
        original = stats(subset)
        symbol_totals = subset.groupby("symbol")["result_R"].sum()
        day_totals = subset.groupby("trade_date")["result_R"].sum()
        month_totals = subset.assign(month=subset["trade_date"].astype(str).str.slice(0, 7)).groupby("month")["result_R"].sum()
        best_symbol = symbol_totals.idxmax() if not symbol_totals.empty else None
        best_day = day_totals.idxmax() if not day_totals.empty else None
        best_month = month_totals.idxmax() if not month_totals.empty else None
        reduced_symbol = stats(subset[subset["symbol"] != best_symbol]) if best_symbol else {}
        reduced_day = stats(subset[subset["trade_date"] != best_day]) if best_day else {}
        reduced_month = stats(subset[subset["trade_date"].astype(str).str.slice(0, 7) != best_month]) if best_month else {}
        rows.append({
            **base,
            "N": original["N"],
            "expectancy_R": original["expectancy_R"],
            "PF": original["PF"],
            "best_symbol": best_symbol,
            "remove_best_symbol_expectancy": reduced_symbol.get("expectancy_R"),
            "best_day": best_day,
            "remove_best_day_expectancy": reduced_day.get("expectancy_R"),
            "best_month": best_month,
            "remove_best_month_expectancy": reduced_month.get("expectancy_R"),
        })
    return pd.DataFrame(rows)


def make_outputs(events: pd.DataFrame, branches: pd.DataFrame) -> dict[str, pd.DataFrame]:
    core = branches[(~branches["is_control"]) & branches["status"].isin(RESOLVED)].copy()
    controls = branches[(branches["is_control"]) & branches["status"].isin(RESOLVED)].copy()
    outputs = {
        "phase4a_timeframe_comparison.csv": grouped_stats(core, ["strategy_variant", "confirmation_tf"]),
        "phase4a_level_strength_comparison.csv": comparison_by_exploded_membership(core, "level_filter_memberships"),
        "phase4a_entry_comparison.csv": grouped_stats(core, ["entry_variant", "strategy_variant"]),
        "phase4a_stop_comparison.csv": grouped_stats(core, ["stop_variant", "strategy_variant"]),
        "phase4a_management_comparison.csv": grouped_stats(core, ["management_variant", "strategy_variant"]),
        "phase4a_holding_horizon.csv": holding_horizon(core),
        "phase4a_options_vs_controls.csv": pd.concat([
            pd.DataFrame([{**{"comparison_group": "OPTIONS_STRONG_LEVELS"}, **stats(core)}]),
            grouped_stats(controls, ["control_type"]).rename(columns={"control_type": "comparison_group"}),
        ], ignore_index=True),
        "phase4a_discovery_holdout.csv": discovery_holdout(branches),
        "phase4a_walkforward.csv": walkforward(branches),
        "phase4a_by_symbol.csv": grouped_stats(core, ["symbol"]),
        "phase4a_by_direction.csv": grouped_stats(core, ["direction"]),
        "phase4a_by_family.csv": grouped_stats(core, ["structural_family"]),
        "phase4a_by_time_bucket.csv": grouped_stats(core, ["time_bucket"]),
        "phase4a_by_level_type.csv": grouped_stats(core, ["level_type"]),
        "phase4a_robustness.csv": robustness(core, ["strategy_variant", "entry_variant", "management_variant", "direction"]),
    }
    return outputs


def question_answers(outputs: dict[str, pd.DataFrame], branches: pd.DataFrame) -> list[tuple[str, str]]:
    core = branches[(~branches["is_control"]) & branches["status"].isin(RESOLVED)].copy()
    tf = outputs["phase4a_timeframe_comparison.csv"]
    level = outputs["phase4a_level_strength_comparison.csv"]
    family = outputs["phase4a_by_family.csv"]
    direction = outputs["phase4a_by_direction.csv"]
    controls = outputs["phase4a_options_vs_controls.csv"]
    walk = outputs["phase4a_walkforward.csv"]

    def best_from(frame: pd.DataFrame, label_col: str) -> str:
        if frame.empty:
            return "INSUFFICIENT_SAMPLE"
        frame = frame.copy()
        frame["_e"] = pd.to_numeric(frame["expectancy_R"], errors="coerce")
        row = frame.sort_values(["_e", "N"], ascending=[False, False]).iloc[0]
        return f"{row[label_col]}: expectancy {row['expectancy_R']}, PF {row['PF']}, N {row['N']}, days {row['unique_days']}"

    five = tf[tf["confirmation_tf"] == "5m"] if not tf.empty else pd.DataFrame()
    fifteen = tf[tf["confirmation_tf"] == "15m"] if not tf.empty else pd.DataFrame()
    five_s = stats(core[core["confirmation_tf"] == "5m"])
    fifteen_s = stats(core[core["confirmation_tf"] == "15m"])
    options_row = controls[controls["comparison_group"] == "OPTIONS_STRONG_LEVELS"].iloc[0].to_dict() if not controls.empty and (controls["comparison_group"] == "OPTIONS_STRONG_LEVELS").any() else {}
    non_options = controls[controls["comparison_group"] != "OPTIONS_STRONG_LEVELS"] if not controls.empty else pd.DataFrame()
    best_control = best_from(non_options, "comparison_group") if not non_options.empty else "NO_CONTROL_ROWS"
    holdout = outputs["phase4a_discovery_holdout.csv"]
    holdout_survivors = 0
    discovery_winners = 0
    if not holdout.empty:
        pivot_keys = ["strategy_variant", "entry_variant", "stop_variant", "management_variant", "direction", "structural_family"]
        for _, group in holdout.groupby(pivot_keys):
            disc = group[group["sample_split"] == "DISCOVERY"]
            hold = group[group["sample_split"] == "HOLDOUT"]
            if disc.empty or hold.empty:
                continue
            disc_good = safe_float(disc.iloc[0]["expectancy_R"], 0) > 0 and (disc.iloc[0]["PF"] == "infinite" or safe_float(disc.iloc[0]["PF"], 0) > 1)
            if disc_good:
                discovery_winners += 1
                hold_good = safe_float(hold.iloc[0]["expectancy_R"], 0) > 0 and (hold.iloc[0]["PF"] == "infinite" or safe_float(hold.iloc[0]["PF"], 0) > 1)
                holdout_survivors += int(hold_good)
    return [
        ("Does 15m confirmation beat 5m?",
         f"5m expectancy {five_s['expectancy_R']} / PF {five_s['PF']} / N {five_s['N']}; 15m expectancy {fifteen_s['expectancy_R']} / PF {fifteen_s['PF']} / N {fifteen_s['N']}."),
        ("Do Top-3/Top-5 levels beat all levels?", best_from(level[level["level_filter"].isin(["TOP_3_LEVELS", "TOP_5_LEVELS"])] if not level.empty else level, "level_filter")),
        ("Does reclaim beat rejection?", best_from(family[family["structural_family"].isin(["RECLAIM", "REJECTION"])] if not family.empty else family, "structural_family")),
        ("Does breakout work better in some regimes?", best_from(family[family["structural_family"] == "BREAKOUT"] if not family.empty else family, "structural_family")),
        ("LONG vs SHORT?", best_from(direction, "direction")),
        ("Which holding horizon is natural?", best_from(outputs["phase4a_holding_horizon.csv"], "holding_horizon")),
        ("Which stop width works best without overfitting?", best_from(outputs["phase4a_stop_comparison.csv"], "stop_variant")),
        ("Do options levels beat matched price controls?",
         f"Options expectancy {options_row.get('expectancy_R')} / PF {options_row.get('PF')} / N {options_row.get('N')}; best control {best_control}."),
        ("Does any result survive holdout and walk-forward?",
         f"Discovery winners {discovery_winners}; holdout survivors {holdout_survivors}; walk-forward windows {len(walk)}; total walk-forward survivors {int(walk['holdout_survivors'].sum()) if not walk.empty and 'holdout_survivors' in walk else 0}."),
        ("Is there any historically supported edge?",
         "SUPPORTED only if positive expectancy, PF>1, positive holdout, walk-forward survival, and robustness are all present. See discovery/holdout and robustness CSVs; report does not promote canonical behavior."),
    ]


def write_report(events: pd.DataFrame, branches: pd.DataFrame, clusters: pd.DataFrame, outputs: dict[str, pd.DataFrame]) -> None:
    path = ROOT / "PHASE_4A_HISTORICAL_MULTITIMEFRAME_REPORT.md"
    core = branches[(~branches["is_control"]) & branches["status"].isin(RESOLVED)].copy()
    controls = branches[(branches["is_control"]) & branches["status"].isin(RESOLVED)].copy()
    variant_count = int(branches[["strategy_variant", "entry_variant", "stop_variant", "management_variant", "control_type"]].drop_duplicates().shape[0]) if not branches.empty else 0
    answers = "\n".join(f"{idx}. {question} `{answer}`" for idx, (question, answer) in enumerate(question_answers(outputs, branches), 1))
    unavailable = "\n".join(f"- {name}: HISTORICALLY_UNAVAILABLE — {reason}" for name, reason in HISTORICALLY_UNAVAILABLE_VARIANTS.items())
    markdown = f"""# Phase 4A-H Historical Multi-Timeframe Strategy Replay

Generated: {now_utc().isoformat()}

Namespace: `{PHASE_NAMESPACE}`

This is a separate historical research pipeline. It uses D-1 EOD option-chain-derived levels and validated historical 5m OHLCV. It does not use or modify the prospective Phase 4A tables, canonical paper behavior, live daemon settings, provider gates, Portfolio OS boundaries, or live-execution settings.

## Critical answers

{answers}

## Data and scope

- Symbols: {', '.join(SYMBOLS)}
- Static options model used: {', '.join(PRIMARY_HISTORICAL_GEX_MODELS)}
- Trading days in 5m dataset: {int(events['trade_date'].nunique()) if not events.empty else 0}
- Level clusters considered: {len(clusters)}
- Parent economic level interactions: {len(events)}
- Historical branch rows: {len(branches)}
- Resolved option-branch rows: {len(core)}
- Resolved matched-control rows: {len(controls)}
- Variants tested: {variant_count}
- Replay version: `{REPLAY_VERSION}`
- Event deduplication: `{EVENT_DEDUP_VERSION}`
- Branch matrix: `{BRANCH_MATRIX_VERSION}`

## What could not be reconstructed honestly

{unavailable}

No intraday persistence or strengthening state was fabricated from static D-1 levels.

Signed dealer-assumption models A/B are intentionally not treated as separate Phase 4A-H intraday-equivalent signals here. This run screens strong static D-1 option concentration levels using the sign-agnostic gamma concentration model.

## Overall options-level result

{markdown_table(pd.DataFrame([{**{'comparison_group': 'OPTIONS_STRONG_LEVELS'}, **stats(core)}]))}

## Timeframe comparison

{markdown_table(outputs['phase4a_timeframe_comparison.csv'].sort_values(['expectancy_R', 'N'], ascending=[False, False]) if not outputs['phase4a_timeframe_comparison.csv'].empty else outputs['phase4a_timeframe_comparison.csv'])}

## Level-strength comparison

{markdown_table(outputs['phase4a_level_strength_comparison.csv'].sort_values(['expectancy_R', 'N'], ascending=[False, False]) if not outputs['phase4a_level_strength_comparison.csv'].empty else outputs['phase4a_level_strength_comparison.csv'])}

## Entry comparison

{markdown_table(outputs['phase4a_entry_comparison.csv'].sort_values(['expectancy_R', 'N'], ascending=[False, False]) if not outputs['phase4a_entry_comparison.csv'].empty else outputs['phase4a_entry_comparison.csv'])}

## Stop comparison

{markdown_table(outputs['phase4a_stop_comparison.csv'].sort_values(['expectancy_R', 'N'], ascending=[False, False]) if not outputs['phase4a_stop_comparison.csv'].empty else outputs['phase4a_stop_comparison.csv'])}

## Management comparison

{markdown_table(outputs['phase4a_management_comparison.csv'].sort_values(['expectancy_R', 'N'], ascending=[False, False]) if not outputs['phase4a_management_comparison.csv'].empty else outputs['phase4a_management_comparison.csv'])}

## Options vs matched controls

{markdown_table(outputs['phase4a_options_vs_controls.csv'].sort_values(['expectancy_R', 'N'], ascending=[False, False]) if not outputs['phase4a_options_vs_controls.csv'].empty else outputs['phase4a_options_vs_controls.csv'])}

## Discovery / holdout

{markdown_table(outputs['phase4a_discovery_holdout.csv'].sort_values(['expectancy_R', 'N'], ascending=[False, False]) if not outputs['phase4a_discovery_holdout.csv'].empty else outputs['phase4a_discovery_holdout.csv'])}

## Walk-forward

{markdown_table(outputs['phase4a_walkforward.csv'])}

## Multiple-testing guard

Many predefined combinations are tested. The best discovery result is not treated as an edge unless it also survives chronological holdout, walk-forward, day/symbol/month robustness, and is not dominated by one symbol/month.

## Interpretation boundary

Historical Phase 4A-H uses `D1_EOD_STATIC_OPTIONS`. It is useful for screening whether stronger static option levels and higher-timeframe confirmations reduce noise. It is not equivalent to the live intraday options-level system because true historical intraday GEX/OI persistence snapshots are unavailable.
"""
    path.write_text(markdown, encoding="utf-8")


def write_outputs(events: pd.DataFrame, branches: pd.DataFrame, clusters: pd.DataFrame, outputs: dict[str, pd.DataFrame]) -> None:
    serialize_for_parquet(events).to_parquet(ROOT / "phase4a_historical_events.parquet", index=False)
    serialize_for_parquet(branches).to_parquet(ROOT / "phase4a_historical_branches.parquet", index=False)
    for name, frame in outputs.items():
        frame.to_csv(ROOT / name, index=False)
    write_report(events, branches, clusters, outputs)


def run() -> dict[str, Any]:
    Settings.load()  # Validate config is loadable; no live service/DB side effects.
    candles, levels, daily = load_inputs()
    candles = add_intraday_features(candles)
    clusters = cluster_levels(candles, levels, daily)
    events = make_events(candles, clusters)
    branches = make_branches(candles, events)
    branches = split_discovery_holdout(branches)
    outputs = make_outputs(events, branches)
    write_outputs(events, branches, clusters, outputs)
    return {
        "namespace": PHASE_NAMESPACE,
        "events": int(len(events)),
        "branches": int(len(branches)),
        "resolved_option_branches": int(((~branches["is_control"]) & branches["status"].isin(RESOLVED)).sum()) if not branches.empty else 0,
        "resolved_control_branches": int(((branches["is_control"]) & branches["status"].isin(RESOLVED)).sum()) if not branches.empty else 0,
        "report": str(ROOT / "PHASE_4A_HISTORICAL_MULTITIMEFRAME_REPORT.md"),
        "replay_version": REPLAY_VERSION,
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
