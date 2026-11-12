from __future__ import annotations

import json
import math
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd


PHASE_NAMESPACE = "PHASE_4B1_EDGE_DECOMPOSITION"
DIAGNOSTIC_SCOPE = "RETROSPECTIVE_DIAGNOSTIC_ONLY"
REPORT_NAME = "PHASE_4B1_FULL_EDGE_DECOMPOSITION.md"
DASHBOARD_STATUS_NAME = "phase4b1_dashboard_status.json"


def safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        if isinstance(value, str) and not value.strip():
            return default
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return default
        return number
    except (TypeError, ValueError):
        return default


def safe_json(value: Any) -> Any:
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("{") or text.startswith("["):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return value
        return value
    return value


def json_text(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, default=str)
    except TypeError:
        return json.dumps(str(value))


def percent(value: float | None) -> float | None:
    return None if value is None else round(float(value), 4)


def profit_factor(values: Iterable[Any]) -> float | None:
    vals = [safe_float(value, None) for value in values]
    vals = [value for value in vals if value is not None]
    gains = sum(value for value in vals if value > 0)
    losses = abs(sum(value for value in vals if value < 0))
    if not vals:
        return None
    if losses == 0:
        return None if gains == 0 else 999.0
    return round(gains / losses, 4)


def max_drawdown(values: Iterable[Any]) -> float | None:
    vals = [safe_float(value, None) for value in values]
    vals = [value for value in vals if value is not None]
    if not vals:
        return None
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in vals:
        equity += value
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return round(max_dd, 4)


def stat_summary(values: Iterable[Any]) -> dict[str, Any]:
    vals = pd.Series([safe_float(value, None) for value in values], dtype="float64").dropna()
    if vals.empty:
        return {
            "N": 0,
            "expectancy": None,
            "median_R": None,
            "PF": None,
            "win_rate": None,
            "avg_winner": None,
            "avg_loser": None,
            "total_R": 0.0,
            "max_drawdown": None,
        }
    winners = vals[vals > 0]
    losers = vals[vals < 0]
    return {
        "N": int(vals.shape[0]),
        "expectancy": round(float(vals.mean()), 4),
        "median_R": round(float(vals.median()), 4),
        "PF": profit_factor(vals.tolist()),
        "win_rate": round(float((vals > 0).mean()), 4),
        "avg_winner": round(float(winners.mean()), 4) if not winners.empty else 0.0,
        "avg_loser": round(float(losers.mean()), 4) if not losers.empty else 0.0,
        "total_R": round(float(vals.sum()), 4),
        "max_drawdown": max_drawdown(vals.tolist()),
    }


def grouped_stats(df: pd.DataFrame, by: str, result_col: str = "result_R") -> pd.DataFrame:
    if df.empty or by not in df.columns:
        return pd.DataFrame(columns=[by, "N", "unique_days", "expectancy", "PF", "win_rate", "median_R", "MFE", "MAE", "max_DD"])
    rows: list[dict[str, Any]] = []
    for key, group in df.groupby(by, dropna=False):
        stats = stat_summary(group[result_col])
        rows.append({
            by: "UNKNOWN" if pd.isna(key) else key,
            "N": stats["N"],
            "unique_days": int(group["trade_date"].nunique()) if "trade_date" in group.columns else None,
            "expectancy": stats["expectancy"],
            "PF": stats["PF"],
            "win_rate": stats["win_rate"],
            "median_R": stats["median_R"],
            "MFE": round(float(pd.to_numeric(group.get("MFE_R"), errors="coerce").mean()), 4) if "MFE_R" in group else None,
            "MAE": round(float(pd.to_numeric(group.get("MAE_R"), errors="coerce").mean()), 4) if "MAE_R" in group else None,
            "max_DD": stats["max_drawdown"],
        })
    return pd.DataFrame(rows).sort_values(["N"], ascending=False)


def trend_side(value: Any) -> str:
    text = str(value or "UNKNOWN").upper()
    if text in {"UP", "BULL", "BULLISH", "LONG"}:
        return "LONG"
    if text in {"DOWN", "BEAR", "BEARISH", "SHORT"}:
        return "SHORT"
    return "UNKNOWN"


def level_tier_strength(tier: Any) -> int:
    text = str(tier or "").upper()
    if "TIER_S" in text:
        return 4
    if "TIER_A" in text:
        return 3
    if "TIER_B" in text:
        return 2
    if "TIER_C" in text:
        return 1
    return 0


def classify_structure(row: Mapping[str, Any]) -> dict[str, Any]:
    direction = str(row.get("direction") or "").upper()
    trend_5m = trend_side(row.get("trend_5m") or row.get("short_term_trend"))
    trend_15m = trend_side(row.get("trend_15m") or row.get("SPY_15m_trend"))
    trend_30m = trend_side(row.get("trend_30m"))
    trend_1h = trend_side(row.get("trend_1h"))
    known = [item for item in (trend_5m, trend_15m, trend_30m, trend_1h) if item != "UNKNOWN"]
    aligned = sum(1 for item in known if item == direction)
    opposed = sum(1 for item in known if item != direction)
    if not known or not direction:
        alignment = "UNKNOWN"
    elif opposed == 0 and aligned >= 2:
        alignment = "FULL_ALIGNMENT"
    elif aligned > opposed:
        alignment = "PARTIAL_ALIGNMENT"
    elif opposed > aligned:
        alignment = "COUNTERTREND"
    else:
        alignment = "CONFLICT"
    return {
        "structure_5m": trend_5m,
        "structure_15m": trend_15m,
        "structure_30m": trend_30m,
        "structure_1h": trend_1h,
        "structure_alignment": alignment,
        "BOS_UP": trend_15m == "LONG" and trend_5m == "LONG",
        "BOS_DOWN": trend_15m == "SHORT" and trend_5m == "SHORT",
        "local_swing_state": "DETERMINISTIC_TREND_PROXY",
        "structure_engine_version": "phase4b1_structure_proxy_v1",
    }


def classify_direction(row: Mapping[str, Any]) -> dict[str, Any]:
    """Deterministic research classifier. It does not change canonical entries."""
    direction = str(row.get("direction") or "UNKNOWN").upper()
    family = str(row.get("structural_family") or row.get("setup_family") or "UNKNOWN").upper()
    level_type = str(row.get("level_type") or row.get("reclaimed_level_type") or "UNKNOWN").upper()
    level_state = str(row.get("intraday_persistence_state") or row.get("level_state") or "UNKNOWN").upper()
    market_alignment = str(row.get("market_alignment") or "UNKNOWN").upper()
    tier_score = level_tier_strength(row.get("level_tier"))
    structure = classify_structure(row)
    evidence: list[str] = []
    conflicts: list[str] = []

    if tier_score >= 3:
        evidence.append("strong_options_level")
    elif tier_score == 1:
        conflicts.append("weak_level_tier")

    if level_state in {"PERSISTENT", "STRENGTHENING"}:
        evidence.append(f"level_state_{level_state.lower()}")
    elif level_state in {"HISTORICALLY_UNAVAILABLE", "UNKNOWN"}:
        conflicts.append("intraday_persistence_unavailable")

    if structure["structure_alignment"] in {"FULL_ALIGNMENT", "PARTIAL_ALIGNMENT"}:
        evidence.append(f"structure_{structure['structure_alignment'].lower()}")
    elif structure["structure_alignment"] in {"COUNTERTREND", "CONFLICT"}:
        conflicts.append(f"structure_{structure['structure_alignment'].lower()}")

    if market_alignment in {"WITH_MARKET_TREND", "FULL_ALIGNMENT", "PARTIAL_ALIGNMENT"}:
        evidence.append("broader_market_aligned")
    elif market_alignment in {"AGAINST_MARKET_TREND", "COUNTERTREND"}:
        conflicts.append("broader_market_countertrend")

    if family in {"RECLAIM", "LEVEL_RECLAIM", "LEVEL_RECLAIM_LONG", "LEVEL_RECLAIM_SHORT"}:
        if direction == "LONG":
            direction_class = "BULLISH_SUPPORT"
        elif direction == "SHORT":
            direction_class = "BEARISH_RESISTANCE"
        else:
            direction_class = "DIRECTION_UNCERTAIN"
        evidence.append("reclaim_interaction")
    elif family == "REJECTION":
        if direction == "LONG":
            direction_class = "BULLISH_SUPPORT"
        elif direction == "SHORT":
            direction_class = "BEARISH_RESISTANCE"
        else:
            direction_class = "NEUTRAL_REACTION_ZONE"
        evidence.append("rejection_interaction")
    elif family in {"LEVEL_BREAKOUT", "BREAKOUT"}:
        if direction == "LONG":
            direction_class = "BREAKOUT_SUPPORT"
        elif direction == "SHORT":
            direction_class = "BREAKDOWN_RESISTANCE"
        else:
            direction_class = "DIRECTION_UNCERTAIN"
        evidence.append("acceptance_breakout_interaction")
    elif family == "BREAKDOWN":
        direction_class = "BEARISH_ACCEPTANCE" if direction == "SHORT" else "DIRECTION_UNCERTAIN"
        evidence.append("breakdown_acceptance_interaction")
    else:
        direction_class = "NEUTRAL_REACTION_ZONE"
        conflicts.append("interaction_family_unclear")

    if level_type in {"GAMMA_FLIP", "GEX_NODE", "GEX_OI_CLUSTER", "MULTI_LEVEL_CLUSTER"}:
        evidence.append("level_is_reaction_zone_not_naively_directional")
    if level_type == "CALL_WALL" and direction == "LONG":
        evidence.append("call_wall_broken_or_reclaimed_from_above")
    if level_type == "PUT_WALL" and direction == "SHORT":
        evidence.append("put_wall_broken_or_reclaimed_from_below")

    base = 50
    base += min(16, tier_score * 4)
    base += 8 if structure["structure_alignment"] == "FULL_ALIGNMENT" else 5 if structure["structure_alignment"] == "PARTIAL_ALIGNMENT" else 0
    base += 6 if level_state == "STRENGTHENING" else 4 if level_state == "PERSISTENT" else 0
    base += 5 if market_alignment in {"WITH_MARKET_TREND", "FULL_ALIGNMENT", "PARTIAL_ALIGNMENT"} else 0
    base -= 8 if structure["structure_alignment"] in {"COUNTERTREND", "CONFLICT"} else 0
    base -= 6 if market_alignment in {"AGAINST_MARKET_TREND", "COUNTERTREND"} else 0
    base -= 8 if not direction or direction == "UNKNOWN" else 0
    confidence = max(0, min(100, base))
    if conflicts and confidence < 58:
        direction_class = "DIRECTION_UNCERTAIN" if direction_class != "NEUTRAL_REACTION_ZONE" else direction_class
    predicted_direction = "LONG" if direction_class in {"BULLISH_SUPPORT", "BREAKOUT_SUPPORT", "BULLISH_ACCEPTANCE"} else (
        "SHORT" if direction_class in {"BEARISH_RESISTANCE", "BREAKDOWN_RESISTANCE", "BEARISH_ACCEPTANCE"} else "UNKNOWN"
    )
    naive_direction = "LONG" if level_type == "PUT_WALL" else "SHORT" if level_type == "CALL_WALL" else "UNKNOWN"
    random_direction = "LONG" if hash(str(row.get("parent_event_id") or row.get("parent_setup_id") or "")) % 2 else "SHORT"
    return {
        "direction_class": direction_class,
        "direction_confidence_0_100": confidence,
        "predicted_direction": predicted_direction,
        "direction_evidence": evidence,
        "direction_conflicts": conflicts,
        "naive_level_direction": naive_direction,
        "price_action_direction": direction,
        "options_level_only_direction": naive_direction,
        "random_direction_control": random_direction,
        "direction_classifier_version": "phase4b1_direction_classifier_v1",
    }


def interaction_role(row: Mapping[str, Any]) -> dict[str, Any]:
    level_type = str(row.get("level_type") or row.get("reclaimed_level_type") or "UNKNOWN").upper()
    family = str(row.get("structural_family") or row.get("setup_family") or "UNKNOWN").upper()
    classifier = classify_direction(row)
    before = "NEUTRAL_REACTION_ZONE"
    after = classifier["direction_class"]
    if family in {"LEVEL_BREAKOUT", "BREAKOUT", "BREAKDOWN"}:
        before = "RESISTANCE_OR_SUPPORT_TEST"
    elif family in {"RECLAIM", "LEVEL_RECLAIM", "LEVEL_RECLAIM_LONG", "LEVEL_RECLAIM_SHORT"}:
        before = "FAILED_ACCEPTANCE_THEN_RECLAIM"
    elif family == "REJECTION":
        before = "FIRST_TOUCH_REACTION_ZONE"
    return {
        "level_role_before": before,
        "level_role_after": after,
        "role_transition": f"{before}->{after}",
        "role_transition_version": "phase4b1_level_role_v1",
        "level_type": level_type,
    }


def entry_quality(row: Mapping[str, Any]) -> str:
    distance = safe_float(row.get("entry_distance_from_level_ATR") or row.get("distance_to_level_ATR"), None)
    delay_bars = safe_float(row.get("entry_delay_bars"), None)
    entry_variant = str(row.get("entry_variant") or "").upper()
    if distance is None and delay_bars is None:
        if "ENTRY_1" in entry_variant or entry_variant == "CANONICAL_ENTRY":
            return "ON_TIME_ENTRY"
        if "ENTRY_2" in entry_variant or "ENTRY_3" in entry_variant:
            return "LATER_CONFIRMATION_ENTRY"
        if "ENTRY_4" in entry_variant or "ENTRY_5" in entry_variant:
            return "FILTERED_CONFIRMATION_ENTRY"
        return "UNKNOWN"
    if delay_bars is not None and delay_bars < 0:
        return "EARLY_ENTRY"
    if distance is not None and distance > 0.50:
        return "EXTENDED_ENTRY"
    if delay_bars is not None and delay_bars >= 2:
        return "LATE_ENTRY"
    return "ON_TIME_ENTRY"


def path_shape(row: Mapping[str, Any]) -> str:
    result = safe_float(row.get("result_R"), None)
    mfe = safe_float(row.get("MFE_R") or row.get("MFE"), 0.0) or 0.0
    mae = safe_float(row.get("MAE_R") or row.get("MAE"), 0.0) or 0.0
    exit_reason = str(row.get("exit_reason") or "").lower()
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
    if "stop" in exit_reason and mfe >= 0.5:
        return "STOP_THEN_RECOVERY_CANDIDATE"
    if result == 0:
        return "CHOP_OR_BREAKEVEN"
    return "NO_EDGE"


def giveback_bucket(row: Mapping[str, Any]) -> str:
    result = safe_float(row.get("result_R"), None)
    mfe = safe_float(row.get("MFE_R") or row.get("MFE"), 0.0) or 0.0
    if result is None or result > 0:
        return "NOT_LOSER_OR_UNRESOLVED"
    if mfe < 0.01:
        return "NEVER_POSITIVE"
    if mfe >= 1.5:
        return "REACHED_1_5R_THEN_LOSS"
    if mfe >= 1.0:
        return "REACHED_1R_THEN_LOSS"
    if mfe >= 0.7:
        return "REACHED_0_7R_THEN_LOSS"
    if mfe >= 0.5:
        return "REACHED_0_5R_THEN_LOSS"
    return "SMALL_MFE_THEN_LOSS"


def loss_reason(row: Mapping[str, Any]) -> tuple[str, str]:
    result = safe_float(row.get("result_R"), None)
    if result is None or result >= 0:
        return "NOT_LOSS", "N/A"
    data_quality = str(row.get("diagnostic_data_quality") or row.get("historical_data_tier") or row.get("data_quality_tier") or "").upper()
    mfe = safe_float(row.get("MFE_R") or row.get("MFE"), 0.0) or 0.0
    mae = safe_float(row.get("MAE_R") or row.get("MAE"), 0.0) or 0.0
    direction_class = str(row.get("direction_class") or "").upper()
    predicted_direction = str(row.get("predicted_direction") or "").upper()
    direction = str(row.get("direction") or "").upper()
    structure_alignment = str(row.get("structure_alignment") or "").upper()
    entry_class = str(row.get("entry_quality_class") or "").upper()
    exit_reason = str(row.get("exit_reason") or "").lower()
    if "INSUFFICIENT" in data_quality or "INVALID" in data_quality:
        return "DATA_INVALID", "ATTRIBUTABLE"
    if mfe < 0.25 and mae >= 0.75:
        return "NO_LEVEL_EDGE", "ASSOCIATED"
    if predicted_direction not in {"", "UNKNOWN", direction} or direction_class == "DIRECTION_UNCERTAIN":
        return "WRONG_DIRECTION", "ASSOCIATED"
    if structure_alignment in {"COUNTERTREND", "CONFLICT"}:
        return "STRUCTURE_MISREAD", "ASSOCIATED"
    if entry_class in {"EARLY_ENTRY", "LATE_ENTRY", "EXTENDED_ENTRY"}:
        return "BAD_ENTRY_TIMING", "ASSOCIATED"
    if "stop" in exit_reason and mfe >= 0.5:
        return "BAD_STOP", "ASSOCIATED"
    if mfe >= 0.7 and result < 0:
        return "BAD_TARGET", "ASSOCIATED"
    if mfe >= 1.0 and result <= 0:
        return "BAD_MANAGEMENT", "ASSOCIATED"
    return "UNKNOWN", "UNKNOWN"


def to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return json.loads(df.replace({pd.NA: None}).to_json(orient="records", date_format="iso"))


class Phase4B1EdgeDecomposer:
    """Builds Phase 4B.1 diagnostic artifacts without mutating live state."""

    REPORT_VERSION = "phase4b1_full_edge_decomposition_v1"

    def __init__(self, root: Path):
        self.root = Path(root)
        self.db_path = self.root / "data" / "options_structure_trader.db"
        self.generated_at = datetime.now(timezone.utc).isoformat()

    def run(self) -> dict[str, Any]:
        hist_events = self._load_parquet("phase4a_historical_events.parquet")
        hist_branches = self._load_parquet("phase4a_historical_branches.parquet")
        live_master = self._load_parquet("edge_master_dataset.parquet")
        live_setups, live_trades = self._load_live_tables()

        master = self._build_master_events(hist_events, hist_branches, live_master, live_setups, live_trades)
        branches = self._build_branch_dataset(hist_branches, live_master, master)
        if not master.empty:
            self._write_parquet(master, self.root / "phase4b1_master_events.parquet")
            self._write_parquet(master, self.root / "phase4b1_retrospective_events.parquet")
        if not branches.empty:
            self._write_parquet(branches, self.root / "phase4b1_counterfactual_branches.parquet")

        outputs = self._write_analysis_files(master, branches)
        dashboard = self._dashboard_status(master, branches, outputs)
        (self.root / DASHBOARD_STATUS_NAME).write_text(json.dumps(dashboard, indent=2, default=str), encoding="utf-8")
        report = self._render_report(master, branches, outputs, dashboard, len(live_setups), len(live_trades))
        (self.root / REPORT_NAME).write_text(report, encoding="utf-8")
        return {
            "generated_at_utc": self.generated_at,
            "report_path": str(self.root / REPORT_NAME),
            "dashboard_status_path": str(self.root / DASHBOARD_STATUS_NAME),
            "master_events": int(len(master)),
            "counterfactual_branches": int(len(branches)),
            "research_only": True,
            "canonical_strategy_unchanged": True,
            "live_trading_disabled": True,
            "portfolio_os_isolated": True,
            "outputs": outputs,
        }

    def status(self) -> dict[str, Any]:
        path = self.root / DASHBOARD_STATUS_NAME
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                payload["artifact_exists"] = True
                payload["artifact_mtime_utc"] = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
                return payload
            except json.JSONDecodeError:
                pass
        return {
            "artifact_exists": False,
            "status": "NOT_GENERATED",
            "research_only": True,
            "canonical_strategy_unchanged": True,
            "live_trading_disabled": True,
            "portfolio_os_isolated": True,
        }

    def _load_parquet(self, name: str) -> pd.DataFrame:
        path = self.root / name
        if not path.exists():
            return pd.DataFrame()
        return pd.read_parquet(path)

    @staticmethod
    def _write_parquet(df: pd.DataFrame, path: Path) -> None:
        frame = df.copy()
        for column in frame.columns:
            if frame[column].dtype == "object":
                frame[column] = frame[column].map(
                    lambda value: None
                    if value is None or (isinstance(value, float) and math.isnan(value))
                    else json_text(value) if isinstance(value, (dict, list, tuple, set)) else str(value)
                )
        frame.to_parquet(path, index=False)

    def _load_live_tables(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        if not self.db_path.exists():
            return [], []
        uri = f"file:{self.db_path.as_posix()}?mode=ro"
        try:
            with sqlite3.connect(uri, uri=True, timeout=5) as con:
                return self._read_json_table(con, "setup_events"), self._read_json_table(con, "paper_trades")
        except sqlite3.OperationalError:
            snapshot = self.root / "data" / "phase4b1_readonly_snapshot.db"
            try:
                with sqlite3.connect(str(self.db_path), timeout=5) as src, sqlite3.connect(str(snapshot)) as dst:
                    src.backup(dst)
                with sqlite3.connect(str(snapshot)) as con:
                    return self._read_json_table(con, "setup_events"), self._read_json_table(con, "paper_trades")
            except sqlite3.Error:
                return [], []

    @staticmethod
    def _read_json_table(con: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
        try:
            rows = con.execute(f"SELECT normalized_json FROM {table}").fetchall()
        except sqlite3.Error:
            return []
        records = []
        for (payload,) in rows:
            try:
                records.append(json.loads(payload))
            except (TypeError, json.JSONDecodeError):
                continue
        return records

    @staticmethod
    def _is_synthetic(row: Mapping[str, Any]) -> bool:
        source_mode = str(row.get("source_mode") or row.get("trade_mode") or row.get("mode") or "").upper()
        if source_mode.startswith("DEMO") or "FIXTURE" in source_mode or "SYNTHETIC" in source_mode:
            return True
        eligibility = row.get("eligibility") or row.get("data_quality") or {}
        if isinstance(eligibility, Mapping) and eligibility.get("synthetic_present"):
            return True
        providers = row.get("providers") or {}
        if isinstance(providers, Mapping) and "demo_fixture" in json_text(providers).lower():
            return True
        return False

    def _build_master_events(
        self,
        hist_events: pd.DataFrame,
        hist_branches: pd.DataFrame,
        live_master: pd.DataFrame,
        live_setups: list[dict[str, Any]],
        live_trades: list[dict[str, Any]],
    ) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        if not hist_events.empty:
            primary = pd.DataFrame()
            if not hist_branches.empty:
                filt = (
                    (hist_branches.get("is_control") == False)  # noqa: E712
                    & (hist_branches.get("strategy_variant") == "VARIANT_A_HIST_5M_CONFIRM_5M_ENTRY")
                    & (hist_branches.get("entry_variant") == "ENTRY_1_CLOSE_RECLAIM")
                    & (hist_branches.get("stop_variant") == "STOP_A_CURRENT_STRUCTURAL")
                    & (hist_branches.get("management_variant") == "TM_V0_CURRENT")
                )
                primary = hist_branches[filt].drop_duplicates("parent_event_id")
                if primary.empty:
                    primary = hist_branches[hist_branches.get("is_control") == False].drop_duplicates("parent_event_id")  # noqa: E712
                primary = primary.set_index("parent_event_id")
            for raw in hist_events.to_dict("records"):
                event_id = raw.get("parent_event_id")
                branch = primary.loc[event_id].to_dict() if not primary.empty and event_id in primary.index else {}
                base = {
                    "parent_event_id": event_id,
                    "namespace": PHASE_NAMESPACE,
                    "source_namespace": "PHASE_4A_HISTORICAL",
                    "diagnostic_scope": DIAGNOSTIC_SCOPE,
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
                    "component_strikes": raw.get("source_level_types"),
                    "level_rank": self._rank_from_filter_memberships(raw.get("level_filter_memberships")),
                    "GEX": None,
                    "absolute_GEX": None,
                    "OI": None,
                    "combined_GEX": None,
                    "combined_OI": None,
                    "distance_from_spot_ATR": raw.get("distance_to_level_ATR"),
                    "distance_from_spot_pct": None,
                    "level_strength": raw.get("level_strength"),
                    "level_tier": raw.get("level_tier"),
                    "intraday_persistence_state": raw.get("intraday_persistence_state"),
                    "first_seen": None,
                    "last_seen": None,
                    "age_minutes": None,
                    "snapshot_count": None,
                    "strength_now": raw.get("level_strength"),
                    "strength_5m_ago": None,
                    "strength_15m_ago": None,
                    "strength_30m_ago": None,
                    "migration_distance": None,
                    "migration_direction": None,
                    "gamma_regime": raw.get("gamma_regime"),
                    "trend_5m": raw.get("trend_5m"),
                    "trend_15m": raw.get("trend_15m"),
                    "trend_30m": raw.get("trend_30m"),
                    "trend_1h": raw.get("trend_1h"),
                    "SPY_15m_trend": raw.get("SPY_15m_trend"),
                    "QQQ_15m_trend": raw.get("QQQ_15m_trend"),
                    "market_alignment": raw.get("market_alignment"),
                    "interaction_episode": raw.get("interaction_episode"),
                    "entry": branch.get("entry"),
                    "stop": branch.get("stop") or raw.get("structural_stop"),
                    "initial_risk": branch.get("initial_risk") or raw.get("initial_risk_reference"),
                    "result_R": branch.get("result_R"),
                    "MFE_R": branch.get("MFE_R"),
                    "MAE_R": branch.get("MAE_R"),
                    "time_to_MFE_minutes": branch.get("time_to_MFE_minutes"),
                    "time_to_0_5R_minutes": branch.get("time_to_0_5R_minutes"),
                    "time_to_1R_minutes": branch.get("time_to_1R_minutes"),
                    "exit_reason": branch.get("exit_reason"),
                    "canonical_trade_id": None,
                    "historical_data_tier": raw.get("historical_data_tier"),
                    "diagnostic_data_quality": "FULL" if raw.get("lookahead_safe") else "LIMITED",
                    "lookahead_safe": bool(raw.get("lookahead_safe")),
                    "synthetic_excluded": True,
                }
                rows.append(self._decorate_master_row(base))

        if not live_master.empty:
            live_master = live_master[live_master.apply(lambda item: not self._is_synthetic(item), axis=1)]
            for raw in live_master.to_dict("records"):
                base = {
                    "parent_event_id": raw.get("parent_setup_id") or raw.get("dedupe_key"),
                    "namespace": PHASE_NAMESPACE,
                    "source_namespace": "LIVE_NATURAL_PAPER",
                    "diagnostic_scope": DIAGNOSTIC_SCOPE,
                    "strategy_state_source": "LIVE_INTRADAY_OPTIONS",
                    "symbol": raw.get("symbol"),
                    "trade_date": raw.get("session_date"),
                    "timestamp": raw.get("timestamp"),
                    "time_bucket": raw.get("time_bucket"),
                    "direction": raw.get("direction"),
                    "structural_family": str(raw.get("setup_family") or "").replace("LEVEL_", "").replace("_LONG", "").replace("_SHORT", "") or "RECLAIM",
                    "level_cluster_id": raw.get("dedupe_key"),
                    "level_price": raw.get("gamma_flip") if raw.get("reclaimed_level_type") == "GAMMA_FLIP" else raw.get("primary_target"),
                    "zone_low": None,
                    "zone_high": None,
                    "level_type": raw.get("reclaimed_level_type"),
                    "component_strikes": None,
                    "level_rank": None,
                    "GEX": raw.get("local_GEX"),
                    "absolute_GEX": abs(safe_float(raw.get("local_GEX"), 0.0) or 0.0),
                    "OI": None,
                    "combined_GEX": raw.get("net_GEX"),
                    "combined_OI": None,
                    "distance_from_spot_ATR": raw.get("distance_to_gamma_flip_R"),
                    "distance_from_spot_pct": raw.get("distance_to_gamma_flip_pct"),
                    "level_strength": raw.get("level_strength"),
                    "level_tier": self._tier_from_live_score(raw.get("adjusted_score"), raw.get("level_strength")),
                    "intraday_persistence_state": "UNKNOWN",
                    "first_seen": None,
                    "last_seen": None,
                    "age_minutes": None,
                    "snapshot_count": None,
                    "strength_now": raw.get("level_strength"),
                    "strength_5m_ago": None,
                    "strength_15m_ago": None,
                    "strength_30m_ago": None,
                    "migration_distance": None,
                    "migration_direction": None,
                    "gamma_regime": raw.get("gamma_regime"),
                    "trend_5m": raw.get("short_term_trend"),
                    "trend_15m": raw.get("SPY_trend") if raw.get("symbol") == "SPY" else raw.get("QQQ_trend"),
                    "trend_30m": None,
                    "trend_1h": None,
                    "SPY_15m_trend": raw.get("SPY_trend"),
                    "QQQ_15m_trend": raw.get("QQQ_trend"),
                    "market_alignment": raw.get("market_alignment"),
                    "interaction_episode": raw.get("dedupe_key"),
                    "entry": raw.get("entry_price") or raw.get("planned_entry"),
                    "stop": raw.get("structural_stop"),
                    "initial_risk": raw.get("risk_per_share"),
                    "result_R": raw.get("canonical_R"),
                    "MFE_R": raw.get("MFE_R"),
                    "MAE_R": raw.get("MAE_R"),
                    "time_to_MFE_minutes": None,
                    "time_to_0_5R_minutes": None,
                    "time_to_1R_minutes": None,
                    "exit_reason": raw.get("exit_reason"),
                    "canonical_trade_id": raw.get("parent_setup_id"),
                    "historical_data_tier": None,
                    "diagnostic_data_quality": self._live_quality(raw),
                    "lookahead_safe": True,
                    "synthetic_excluded": True,
                    "raw_score": raw.get("raw_score"),
                    "adjusted_score": raw.get("adjusted_score"),
                    "confidence_score": raw.get("confidence_score"),
                    "data_quality_tier": raw.get("data_quality_tier"),
                    "candle_provider": raw.get("candle_provider"),
                    "options_provider": raw.get("options_provider"),
                }
                rows.append(self._decorate_master_row(base))

        if not rows and live_setups:
            trades_by_setup = {row.get("setup_event_id"): row for row in live_trades if not self._is_synthetic(row)}
            for setup in live_setups:
                if self._is_synthetic(setup):
                    continue
                trade = trades_by_setup.get(setup.get("setup_event_id"), {})
                signal = setup.get("signal_snapshot") or {}
                level = signal.get("level") or {}
                base = {
                    "parent_event_id": setup.get("setup_event_id"),
                    "namespace": PHASE_NAMESPACE,
                    "source_namespace": "LIVE_DB_NATURAL",
                    "diagnostic_scope": DIAGNOSTIC_SCOPE,
                    "strategy_state_source": "LIVE_INTRADAY_OPTIONS",
                    "symbol": setup.get("ticker"),
                    "trade_date": str(setup.get("created_at_utc") or "")[:10],
                    "timestamp": setup.get("created_at_utc"),
                    "direction": "LONG" if "LONG" in str(setup.get("setup_type")) else "SHORT",
                    "structural_family": "RECLAIM",
                    "level_type": setup.get("level_type") or level.get("level_type"),
                    "level_price": level.get("price"),
                    "level_tier": self._tier_from_live_score((setup.get("score") or {}).get("total"), None),
                    "intraday_persistence_state": "UNKNOWN",
                    "trend_5m": None,
                    "trend_15m": None,
                    "trend_30m": None,
                    "trend_1h": None,
                    "market_alignment": "UNKNOWN",
                    "entry": trade.get("actual_fill_price") or (setup.get("trade_plan") or {}).get("entry_zone_low"),
                    "stop": trade.get("stop_initial") or (setup.get("trade_plan") or {}).get("stop_initial"),
                    "result_R": trade.get("realized_r"),
                    "MFE_R": trade.get("mfe_r"),
                    "MAE_R": trade.get("mae_r"),
                    "exit_reason": trade.get("exit_reason"),
                    "canonical_trade_id": trade.get("trade_id"),
                    "diagnostic_data_quality": "LIMITED",
                    "lookahead_safe": True,
                    "synthetic_excluded": True,
                }
                rows.append(self._decorate_master_row(base))

        return pd.DataFrame(rows).drop_duplicates("parent_event_id") if rows else pd.DataFrame()

    @staticmethod
    def _rank_from_filter_memberships(value: Any) -> int | None:
        text = json_text(safe_json(value)).upper()
        if "TOP_1" in text:
            return 1
        if "TOP_3" in text:
            return 3
        if "TOP_5" in text:
            return 5
        return None

    @staticmethod
    def _tier_from_live_score(score: Any, level_strength: Any) -> str:
        value = safe_float(level_strength, None)
        if value is None:
            raw_score = safe_float(score, 0.0) or 0.0
            value = raw_score / 100 if raw_score > 1 else raw_score
        if value >= 0.85:
            return "LEVEL_TIER_S"
        if value >= 0.70:
            return "LEVEL_TIER_A"
        if value >= 0.55:
            return "LEVEL_TIER_B"
        return "LEVEL_TIER_C"

    @staticmethod
    def _live_quality(row: Mapping[str, Any]) -> str:
        quality = str(row.get("data_quality_tier") or "").upper()
        if "FREE" in quality or "LIMITED" in quality:
            return "LIMITED"
        if "FULL" in quality or "HIGH" in quality:
            return "FULL"
        return "PARTIAL"

    def _decorate_master_row(self, base: dict[str, Any]) -> dict[str, Any]:
        structure = classify_structure(base)
        direction = classify_direction({**base, **structure})
        role = interaction_role({**base, **structure, **direction})
        base.update(structure)
        base.update(direction)
        base.update(role)
        mfe = safe_float(base.get("MFE_R"), 0.0) or 0.0
        result = safe_float(base.get("result_R"), None)
        base["raw_directional_success_0_5R"] = mfe >= 0.5
        base["raw_directional_success_1R"] = mfe >= 1.0
        base["giveback_R"] = round(mfe - result, 4) if result is not None else None
        base["path_shape"] = path_shape(base)
        base["entry_quality_class"] = entry_quality(base)
        return base

    def _build_branch_dataset(self, hist_branches: pd.DataFrame, live_master: pd.DataFrame, master: pd.DataFrame) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        master_lookup = master.set_index("parent_event_id").to_dict("index") if not master.empty else {}
        if not hist_branches.empty:
            for raw in hist_branches.to_dict("records"):
                parent = master_lookup.get(raw.get("parent_event_id"), {})
                row = {
                    "branch_id": raw.get("branch_id"),
                    "parent_event_id": raw.get("parent_event_id"),
                    "namespace": PHASE_NAMESPACE,
                    "source_namespace": "PHASE_4A_HISTORICAL",
                    "diagnostic_scope": DIAGNOSTIC_SCOPE,
                    "strategy_state_source": "D1_EOD_STATIC_OPTIONS",
                    "symbol": raw.get("symbol"),
                    "trade_date": raw.get("trade_date"),
                    "strategy_variant": raw.get("strategy_variant"),
                    "confirmation_tf": raw.get("confirmation_tf"),
                    "execution_tf": raw.get("execution_tf"),
                    "context_tf": raw.get("context_tf"),
                    "entry_variant": raw.get("entry_variant"),
                    "stop_variant": raw.get("stop_variant"),
                    "management_variant": raw.get("management_variant"),
                    "is_control": bool(raw.get("is_control")),
                    "control_type": raw.get("control_type"),
                    "direction": raw.get("direction"),
                    "structural_family": raw.get("structural_family"),
                    "level_type": raw.get("level_type"),
                    "level_tier": raw.get("level_tier"),
                    "time_bucket": raw.get("time_bucket"),
                    "gamma_regime": raw.get("gamma_regime"),
                    "status": raw.get("status"),
                    "exit_reason": raw.get("exit_reason"),
                    "result_R": raw.get("result_R"),
                    "MFE_R": raw.get("MFE_R"),
                    "MAE_R": raw.get("MAE_R"),
                    "time_to_MFE_minutes": raw.get("time_to_MFE_minutes"),
                    "time_to_0_25R_minutes": None,
                    "time_to_0_5R_minutes": raw.get("time_to_0_5R_minutes"),
                    "time_to_0_7R_minutes": None,
                    "time_to_1R_minutes": raw.get("time_to_1R_minutes"),
                    "time_to_1_5R_minutes": raw.get("time_to_1_5R_minutes"),
                    "time_to_2R_minutes": None,
                    "holding_15m_R": raw.get("holding_15m_R"),
                    "holding_30m_R": raw.get("holding_30m_R"),
                    "holding_60m_R": raw.get("holding_60m_R"),
                    "holding_120m_R": raw.get("holding_120m_R"),
                    "holding_240m_R": raw.get("holding_240m_R"),
                    "holding_EOD_R": raw.get("holding_EOD_R"),
                    "duration_minutes": raw.get("duration_minutes"),
                    "entry": raw.get("entry"),
                    "stop": raw.get("stop"),
                    "initial_risk": raw.get("initial_risk"),
                    "slippage_bps": raw.get("slippage_bps"),
                    "diagnostic_data_quality": "FULL" if raw.get("lookahead_safe") else "LIMITED",
                    "sequence_quality": "FIVE_MIN_CONSERVATIVE_REPLAY",
                    "post_stop_tracking_available": False,
                    "synthetic_excluded": True,
                    "direction_class": parent.get("direction_class"),
                    "predicted_direction": parent.get("predicted_direction"),
                    "direction_confidence_0_100": parent.get("direction_confidence_0_100"),
                    "structure_alignment": parent.get("structure_alignment"),
                }
                rows.append(self._decorate_branch_row(row))
        if not live_master.empty:
            live_master = live_master[live_master.apply(lambda item: not self._is_synthetic(item), axis=1)]
            for raw in live_master.to_dict("records"):
                parent_id = raw.get("parent_setup_id") or raw.get("dedupe_key")
                parent = master_lookup.get(parent_id, {})
                candidates = [
                    ("LIVE_CANONICAL", "CANONICAL_ENTRY", "STOP_A_CURRENT_STRUCTURAL", "TM_V0_CURRENT", raw.get("canonical_R"), raw.get("canonical_status")),
                    ("LIVE_FORWARD_AB", "CANONICAL_ENTRY", "STOP_A_CURRENT_STRUCTURAL", "TM_V0_CURRENT", raw.get("branch_A_R"), raw.get("branch_A_status")),
                    ("LIVE_FORWARD_AB", "CANONICAL_ENTRY", "STOP_A_CURRENT_STRUCTURAL", "TM_V3_TP1_PLUS_RUNNER", raw.get("branch_B_R"), raw.get("branch_B_status")),
                ]
                for strategy, entry_variant_name, stop_variant, management, result, status in candidates:
                    if result is None and strategy != "LIVE_CANONICAL":
                        continue
                    row = {
                        "branch_id": f"p4b1_live_{parent_id}_{strategy}_{management}",
                        "parent_event_id": parent_id,
                        "namespace": PHASE_NAMESPACE,
                        "source_namespace": "LIVE_NATURAL_PAPER",
                        "diagnostic_scope": DIAGNOSTIC_SCOPE,
                        "strategy_state_source": "LIVE_INTRADAY_OPTIONS",
                        "symbol": raw.get("symbol"),
                        "trade_date": raw.get("session_date"),
                        "strategy_variant": strategy,
                        "confirmation_tf": "5m",
                        "execution_tf": "5m",
                        "context_tf": "live",
                        "entry_variant": entry_variant_name,
                        "stop_variant": stop_variant,
                        "management_variant": management,
                        "is_control": False,
                        "control_type": None,
                        "direction": raw.get("direction"),
                        "structural_family": raw.get("setup_family"),
                        "level_type": raw.get("reclaimed_level_type"),
                        "level_tier": parent.get("level_tier"),
                        "time_bucket": raw.get("time_bucket"),
                        "gamma_regime": raw.get("gamma_regime"),
                        "status": status or raw.get("canonical_status"),
                        "exit_reason": raw.get("exit_reason"),
                        "result_R": result,
                        "MFE_R": raw.get("MFE_R"),
                        "MAE_R": raw.get("MAE_R"),
                        "time_to_MFE_minutes": None,
                        "time_to_0_25R_minutes": None,
                        "time_to_0_5R_minutes": None,
                        "time_to_0_7R_minutes": None,
                        "time_to_1R_minutes": None,
                        "time_to_1_5R_minutes": None,
                        "time_to_2R_minutes": None,
                        "holding_15m_R": raw.get("R_after_15m"),
                        "holding_30m_R": raw.get("R_after_30m"),
                        "holding_60m_R": raw.get("R_after_60m"),
                        "holding_120m_R": raw.get("R_after_120m"),
                        "holding_240m_R": None,
                        "holding_EOD_R": raw.get("R_at_close"),
                        "duration_minutes": None,
                        "entry": raw.get("entry_price"),
                        "stop": raw.get("structural_stop"),
                        "initial_risk": raw.get("risk_per_share"),
                        "slippage_bps": None,
                        "diagnostic_data_quality": self._live_quality(raw),
                        "sequence_quality": "LIVE_STORED_EXCURSION",
                        "post_stop_tracking_available": False,
                        "synthetic_excluded": True,
                        "direction_class": parent.get("direction_class"),
                        "predicted_direction": parent.get("predicted_direction"),
                        "direction_confidence_0_100": parent.get("direction_confidence_0_100"),
                        "structure_alignment": parent.get("structure_alignment"),
                    }
                    rows.append(self._decorate_branch_row(row))
        return pd.DataFrame(rows) if rows else pd.DataFrame()

    def _decorate_branch_row(self, row: dict[str, Any]) -> dict[str, Any]:
        mfe = safe_float(row.get("MFE_R"), 0.0) or 0.0
        mae = safe_float(row.get("MAE_R"), 0.0) or 0.0
        result = safe_float(row.get("result_R"), None)
        for threshold in (0.25, 0.5, 0.7, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0):
            key = str(threshold).replace(".", "_").rstrip("0").rstrip("_")
            row[f"reached_{key}R"] = mfe >= threshold
            row[f"hit_{key}R_before_minus_1R"] = mfe >= threshold and mae < 1.0
        row["MFE_MAE_ratio"] = round(mfe / mae, 4) if mae > 0 else None
        row["giveback_R"] = round(mfe - result, 4) if result is not None else None
        row["giveback_bucket"] = giveback_bucket(row)
        row["path_shape"] = path_shape(row)
        row["entry_quality_class"] = entry_quality(row)
        primary, certainty = loss_reason(row)
        row["primary_loss_reason"] = primary
        row["loss_reason_certainty"] = certainty
        row["capture_efficiency"] = round(result / mfe, 4) if result is not None and mfe > 0 else None
        row["directional_efficiency"] = round(((mfe - mae) / (mfe + mae)), 4) if (mfe + mae) > 0 else None
        return row

    def _write_analysis_files(self, master: pd.DataFrame, branches: pd.DataFrame) -> dict[str, str]:
        outputs: dict[str, str] = {}

        def write_csv(name: str, frame: pd.DataFrame) -> None:
            path = self.root / name
            frame.to_csv(path, index=False)
            outputs[name] = str(path)

        direction_rows = []
        if not master.empty:
            for row in master.to_dict("records"):
                mfe = safe_float(row.get("MFE_R"), 0.0) or 0.0
                result = safe_float(row.get("result_R"), None)
                actual = row.get("direction") if mfe >= 0.5 or (result is not None and result > 0) else "NO_FAVORABLE_MOVE"
                for model, prediction_key in (
                    ("MODEL_DIRECTION_CLASSIFIER", "predicted_direction"),
                    ("NAIVE_LEVEL_DIRECTION", "naive_level_direction"),
                    ("PRICE_ACTION_ONLY", "price_action_direction"),
                    ("OPTIONS_LEVEL_ONLY", "options_level_only_direction"),
                    ("RANDOM_DIRECTION_CONTROL", "random_direction_control"),
                ):
                    pred = row.get(prediction_key)
                    direction_rows.append({
                        "parent_event_id": row.get("parent_event_id"),
                        "source_namespace": row.get("source_namespace"),
                        "symbol": row.get("symbol"),
                        "trade_date": row.get("trade_date"),
                        "direction_model": model,
                        "predicted_direction": pred,
                        "actual_direction_proxy": actual,
                        "direction_correct_0_5R_proxy": bool(pred == row.get("direction") and mfe >= 0.5),
                        "direction_class": row.get("direction_class"),
                        "direction_confidence_0_100": row.get("direction_confidence_0_100"),
                        "MFE_R": row.get("MFE_R"),
                        "MAE_R": row.get("MAE_R"),
                        "result_R": row.get("result_R"),
                        "evidence": json_text(row.get("direction_evidence")),
                        "conflicts": json_text(row.get("direction_conflicts")),
                    })
        write_csv("phase4b1_direction_classifier.csv", pd.DataFrame(direction_rows))

        structure = grouped_stats(branches[branches.get("is_control") == False] if not branches.empty else branches, "structure_alignment") if not branches.empty else pd.DataFrame()
        write_csv("phase4b1_structure_analysis.csv", structure)

        entry = grouped_stats(branches[branches.get("is_control") == False] if not branches.empty else branches, "entry_variant") if not branches.empty else pd.DataFrame()
        if not branches.empty:
            quality = grouped_stats(branches[branches.get("is_control") == False], "entry_quality_class")
            entry = pd.concat([entry.assign(group_type="entry_variant"), quality.assign(group_type="entry_quality_class")], ignore_index=True)
        write_csv("phase4b1_entry_analysis.csv", entry)

        raw_cols = [
            "branch_id", "parent_event_id", "source_namespace", "symbol", "trade_date", "direction", "strategy_variant",
            "entry_variant", "management_variant", "stop_variant", "result_R", "MFE_R", "MAE_R",
            "time_to_MFE_minutes", "time_to_0_5R_minutes", "time_to_1R_minutes", "time_to_1_5R_minutes",
            "holding_15m_R", "holding_30m_R", "holding_60m_R", "holding_120m_R", "holding_240m_R", "holding_EOD_R",
            "hit_0_25R_before_minus_1R", "hit_0_5R_before_minus_1R", "hit_0_7R_before_minus_1R",
            "hit_1R_before_minus_1R", "hit_1_5R_before_minus_1R", "sequence_quality",
        ]
        write_csv("phase4b1_raw_excursion.csv", self._cols(branches, raw_cols))

        giveback = branches[pd.to_numeric(branches.get("result_R"), errors="coerce").fillna(0) <= 0] if not branches.empty else pd.DataFrame()
        write_csv("phase4b1_giveback_analysis.csv", self._cols(giveback, [
            "branch_id", "parent_event_id", "source_namespace", "symbol", "direction", "management_variant",
            "result_R", "MFE_R", "MAE_R", "giveback_R", "giveback_bucket", "path_shape", "exit_reason",
        ]))

        stop_rows = []
        if not branches.empty:
            for (stop_variant, direction), group in branches[branches.get("is_control") == False].groupby(["stop_variant", "direction"], dropna=False):
                stats = stat_summary(group["result_R"])
                winners = group[pd.to_numeric(group["result_R"], errors="coerce") > 0]
                stopped = group[group["exit_reason"].astype(str).str.lower().str.contains("stop", na=False)]
                stopped_then_mfe = stopped[pd.to_numeric(stopped["MFE_R"], errors="coerce") >= 0.5]
                stop_rows.append({
                    "stop_variant": stop_variant,
                    "direction": direction,
                    **stats,
                    "stop_frequency": round(float(len(stopped) / len(group)), 4) if len(group) else None,
                    "stopped_trade_avg_MFE": round(float(pd.to_numeric(stopped.get("MFE_R"), errors="coerce").mean()), 4) if len(stopped) else None,
                    "stopped_trades_later_or_before_reached_0_5R_proxy": round(float(len(stopped_then_mfe) / len(stopped)), 4) if len(stopped) else None,
                    "winner_MAE_P10": self._percentile(winners, "MAE_R", 0.10),
                    "winner_MAE_P25": self._percentile(winners, "MAE_R", 0.25),
                    "winner_MAE_median": self._percentile(winners, "MAE_R", 0.50),
                    "winner_MAE_P75": self._percentile(winners, "MAE_R", 0.75),
                    "winner_MAE_P90": self._percentile(winners, "MAE_R", 0.90),
                    "winner_MAE_P95": self._percentile(winners, "MAE_R", 0.95),
                    "stop_preserves_80pct_winners_MAE_R": self._percentile(winners, "MAE_R", 0.80),
                    "stop_preserves_90pct_winners_MAE_R": self._percentile(winners, "MAE_R", 0.90),
                    "stop_preserves_95pct_winners_MAE_R": self._percentile(winners, "MAE_R", 0.95),
                })
        write_csv("phase4b1_stop_efficiency.csv", pd.DataFrame(stop_rows))

        stop_recovery = branches[branches["exit_reason"].astype(str).str.lower().str.contains("stop", na=False)].copy() if not branches.empty else pd.DataFrame()
        if not stop_recovery.empty:
            stop_recovery["stop_recovery_class"] = stop_recovery.apply(
                lambda row: "STOP_TOO_TIGHT_CANDIDATE" if safe_float(row.get("MFE_R"), 0.0) >= 0.5 else "THESIS_WRONG_OR_LEVEL_FAILED",
                axis=1,
            )
            stop_recovery["post_stop_recovery_tracking"] = "UNAVAILABLE_IN_CURRENT_REPLAY_ARTIFACT"
        write_csv("phase4b1_stop_recovery.csv", self._cols(stop_recovery, [
            "branch_id", "parent_event_id", "source_namespace", "symbol", "direction", "stop_variant", "management_variant",
            "result_R", "MFE_R", "MAE_R", "exit_reason", "stop_recovery_class", "post_stop_recovery_tracking",
        ]))

        target_rows = []
        if not branches.empty:
            options = branches[branches.get("is_control") == False]
            for (direction, level_type, family), group in options.groupby(["direction", "level_type", "structural_family"], dropna=False):
                row = {"direction": direction, "level_type": level_type, "structural_family": family, "N": int(len(group))}
                mfe = pd.to_numeric(group["MFE_R"], errors="coerce")
                for threshold in (0.25, 0.5, 0.7, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0):
                    label = str(threshold).replace(".", "_").rstrip("0").rstrip("_")
                    row[f"reach_{label}R_rate"] = round(float((mfe >= threshold).mean()), 4) if len(mfe.dropna()) else None
                target_rows.append(row)
        write_csv("phase4b1_target_efficiency.csv", pd.DataFrame(target_rows))

        be_rows = []
        if not branches.empty:
            for management, group in branches[branches.get("is_control") == False].groupby("management_variant", dropna=False):
                be = group[group["exit_reason"].astype(str).str.lower().str.contains("breakeven|be", na=False)]
                stats = stat_summary(group["result_R"])
                be_rows.append({
                    "management_variant": management,
                    **stats,
                    "BE_exits": int(len(be)),
                    "BE_frequency": round(float(len(be) / len(group)), 4) if len(group) else None,
                    "BE_then_target_tracking": "UNAVAILABLE_IN_CURRENT_REPLAY_ARTIFACT",
                })
        write_csv("phase4b1_breakeven_analysis.csv", pd.DataFrame(be_rows))

        horizon_rows = []
        if not branches.empty:
            for horizon_col in ("holding_15m_R", "holding_30m_R", "holding_60m_R", "holding_120m_R", "holding_240m_R", "holding_EOD_R"):
                label = horizon_col.replace("holding_", "").replace("_R", "")
                stats = stat_summary(branches[horizon_col]) if horizon_col in branches.columns else stat_summary([])
                horizon_rows.append({"horizon": label, **stats})
        write_csv("phase4b1_holding_horizon.csv", pd.DataFrame(horizon_rows))

        capture = grouped_stats(branches[branches.get("is_control") == False] if not branches.empty else branches, "management_variant") if not branches.empty else pd.DataFrame()
        if not branches.empty and not capture.empty:
            cap_extra = branches.groupby("management_variant", dropna=False)["capture_efficiency"].mean(numeric_only=True).reset_index()
            cap_extra["median_capture_efficiency"] = branches.groupby("management_variant", dropna=False)["capture_efficiency"].median(numeric_only=True).values
            capture = capture.merge(cap_extra, on="management_variant", how="left")
        write_csv("phase4b1_management_capture.csv", capture)

        role = grouped_stats(branches[branches.get("is_control") == False] if not branches.empty else branches, "direction_class") if not branches.empty else pd.DataFrame()
        write_csv("phase4b1_level_role_analysis.csv", role)

        loss = pd.DataFrame()
        if not branches.empty:
            losses = branches[pd.to_numeric(branches["result_R"], errors="coerce") < 0].copy()
            if not losses.empty:
                agg = losses.groupby(["primary_loss_reason", "loss_reason_certainty"], dropna=False).agg(
                    N=("result_R", "size"),
                    negative_R=("result_R", lambda s: round(float(pd.to_numeric(s, errors="coerce").sum()), 4)),
                    avg_MFE=("MFE_R", lambda s: round(float(pd.to_numeric(s, errors="coerce").mean()), 4)),
                    avg_MAE=("MAE_R", lambda s: round(float(pd.to_numeric(s, errors="coerce").mean()), 4)),
                ).reset_index()
                total_negative = abs(float(agg["negative_R"].sum())) if not agg.empty else 0.0
                agg["share_of_negative_R"] = agg["negative_R"].apply(lambda x: round(abs(float(x)) / total_negative, 4) if total_negative else None)
                loss = agg.sort_values("share_of_negative_R", ascending=False)
        write_csv("phase4b1_loss_attribution.csv", loss)

        winner = pd.DataFrame()
        if not branches.empty:
            wins = branches[pd.to_numeric(branches["result_R"], errors="coerce") > 0].copy()
            winner = grouped_stats(wins, "path_shape") if not wins.empty else pd.DataFrame()
        write_csv("phase4b1_winner_analysis.csv", winner)

        rescue = self._counterfactual_rescue(branches)
        write_csv("phase4b1_counterfactual_rescue.csv", rescue)

        score_audit = self._score_audit(master, branches)
        write_csv("phase4b1_score_audit.csv", score_audit)

        audit_outputs = self._write_manual_audit_samples(master, branches)
        outputs.update(audit_outputs)
        return outputs

    @staticmethod
    def _cols(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame(columns=columns)
        result = df.copy()
        for column in columns:
            if column not in result.columns:
                result[column] = None
        return result[columns]

    @staticmethod
    def _percentile(df: pd.DataFrame, column: str, q: float) -> float | None:
        if df.empty or column not in df.columns:
            return None
        values = pd.to_numeric(df[column], errors="coerce").dropna()
        if values.empty:
            return None
        return round(float(values.quantile(q)), 4)

    def _counterfactual_rescue(self, branches: pd.DataFrame) -> pd.DataFrame:
        if branches.empty:
            return pd.DataFrame(columns=["parent_event_id", "branch_id", "loss_rescue_stage"])
        options = branches[branches.get("is_control") == False].copy()
        best_by_parent = options.groupby("parent_event_id")["result_R"].max(numeric_only=True).to_dict()
        v3_by_parent = options[options["management_variant"] == "TM_V3_TP1_PLUS_RUNNER"].groupby("parent_event_id")["result_R"].max(numeric_only=True).to_dict()
        wider_stop_by_parent = options[options["stop_variant"].astype(str).str.contains("0_50_ATR", na=False)].groupby("parent_event_id")["result_R"].max(numeric_only=True).to_dict()
        rows = []
        for row in options[pd.to_numeric(options["result_R"], errors="coerce") < 0].to_dict("records"):
            stage = "UNRESCUED"
            if row.get("predicted_direction") not in {None, "", "UNKNOWN", row.get("direction")}:
                stage = "DIRECTION_CLASSIFIER_WOULD_AVOID"
            elif row.get("structure_alignment") in {"COUNTERTREND", "CONFLICT"}:
                stage = "STRUCTURE_CONFIRMATION_WOULD_AVOID"
            elif safe_float(best_by_parent.get(row["parent_event_id"]), -999) > 0:
                stage = "ALTERNATIVE_ENTRY_OR_MANAGEMENT_RESCUES"
            elif safe_float(wider_stop_by_parent.get(row["parent_event_id"]), -999) > 0:
                stage = "ALTERNATIVE_STOP_RESCUES"
            elif safe_float(v3_by_parent.get(row["parent_event_id"]), -999) > 0:
                stage = "ALTERNATIVE_TP_BE_RESCUES"
            rows.append({
                "parent_event_id": row.get("parent_event_id"),
                "branch_id": row.get("branch_id"),
                "symbol": row.get("symbol"),
                "direction": row.get("direction"),
                "result_R": row.get("result_R"),
                "MFE_R": row.get("MFE_R"),
                "primary_loss_reason": row.get("primary_loss_reason"),
                "loss_rescue_stage": stage,
                "diagnostic_only": True,
            })
        return pd.DataFrame(rows)

    def _score_audit(self, master: pd.DataFrame, branches: pd.DataFrame) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        if not master.empty:
            for score_col in ("level_strength", "raw_score", "adjusted_score", "confidence_score", "direction_confidence_0_100"):
                if score_col not in master.columns:
                    continue
                score = pd.to_numeric(master[score_col], errors="coerce")
                for outcome_col in ("result_R", "MFE_R", "MAE_R"):
                    if outcome_col not in master.columns:
                        continue
                    outcome = pd.to_numeric(master[outcome_col], errors="coerce")
                    valid = pd.concat([score, outcome], axis=1).dropna()
                    corr = round(float(valid.iloc[:, 0].corr(valid.iloc[:, 1], method="spearman")), 4) if len(valid) >= 10 else None
                    rows.append({
                        "score_component": score_col,
                        "outcome": outcome_col,
                        "N": int(len(valid)),
                        "spearman_rank_corr": corr,
                        "status": "SCORE_NOT_PREDICTIVE" if corr is not None and abs(corr) < 0.05 else "WEAK_OR_NEEDS_MORE_DATA",
                    })
        if not branches.empty:
            for score_col in ("direction_confidence_0_100",):
                score = pd.to_numeric(branches.get(score_col), errors="coerce")
                outcome = pd.to_numeric(branches.get("result_R"), errors="coerce")
                valid = pd.concat([score, outcome], axis=1).dropna()
                corr = round(float(valid.iloc[:, 0].corr(valid.iloc[:, 1], method="spearman")), 4) if len(valid) >= 10 else None
                rows.append({"score_component": score_col, "outcome": "branch_result_R", "N": int(len(valid)),
                             "spearman_rank_corr": corr,
                             "status": "DIRECTION_CONFIDENCE_NOT_CALIBRATED" if corr is not None and abs(corr) < 0.05 else "WEAK_OR_NEEDS_MORE_DATA"})
        return pd.DataFrame(rows)

    def _write_manual_audit_samples(self, master: pd.DataFrame, branches: pd.DataFrame) -> dict[str, str]:
        outputs: dict[str, str] = {}

        def write(name: str, frame: pd.DataFrame) -> None:
            path = self.root / name
            frame.to_csv(path, index=False)
            outputs[name] = str(path)

        audit_cols = [
            "branch_id", "parent_event_id", "source_namespace", "symbol", "trade_date", "direction",
            "structural_family", "level_type", "level_tier", "time_bucket", "strategy_variant",
            "entry_variant", "stop_variant", "management_variant", "result_R", "MFE_R", "MAE_R",
            "time_to_MFE_minutes", "exit_reason", "path_shape", "primary_loss_reason",
            "direction_class", "direction_confidence_0_100", "structure_alignment",
        ]
        options = branches[branches.get("is_control") == False] if not branches.empty else pd.DataFrame()
        canonical = options[
            (options.get("management_variant") == "TM_V0_CURRENT")
            & (options.get("stop_variant") == "STOP_A_CURRENT_STRUCTURAL")
        ] if not options.empty else pd.DataFrame()
        resolved = canonical[pd.to_numeric(canonical.get("result_R"), errors="coerce").notna()] if not canonical.empty else pd.DataFrame()

        if not resolved.empty:
            write("phase4b1_manual_audit_best_trades.csv", self._cols(
                resolved.sort_values("result_R", ascending=False).head(100), audit_cols))
            write("phase4b1_manual_audit_worst_trades.csv", self._cols(
                resolved.sort_values("result_R", ascending=True).head(100), audit_cols))
            write("phase4b1_manual_audit_stop_then_recovery.csv", self._cols(
                resolved[(resolved["primary_loss_reason"] == "BAD_STOP") | (resolved["path_shape"] == "STOP_THEN_RECOVERY_CANDIDATE")].head(100),
                audit_cols))
            write("phase4b1_manual_audit_large_giveback.csv", self._cols(
                resolved[(pd.to_numeric(resolved["giveback_R"], errors="coerce") >= 1.0) & (pd.to_numeric(resolved["result_R"], errors="coerce") <= 0)].head(100),
                audit_cols))
            write("phase4b1_manual_audit_wrong_direction.csv", self._cols(
                resolved[resolved["primary_loss_reason"] == "WRONG_DIRECTION"].head(100), audit_cols))
            write("phase4b1_manual_audit_structure_misread.csv", self._cols(
                resolved[resolved["primary_loss_reason"] == "STRUCTURE_MISREAD"].head(100), audit_cols))
        else:
            for name in (
                "phase4b1_manual_audit_best_trades.csv",
                "phase4b1_manual_audit_worst_trades.csv",
                "phase4b1_manual_audit_stop_then_recovery.csv",
                "phase4b1_manual_audit_large_giveback.csv",
                "phase4b1_manual_audit_wrong_direction.csv",
                "phase4b1_manual_audit_structure_misread.csv",
            ):
                write(name, pd.DataFrame(columns=audit_cols))

        structure_cols = [
            "parent_event_id", "source_namespace", "symbol", "trade_date", "timestamp", "direction",
            "level_type", "level_tier", "structural_family", "structure_5m", "structure_15m",
            "structure_30m", "structure_1h", "BOS_UP", "BOS_DOWN", "structure_alignment",
            "direction_class", "direction_confidence_0_100", "entry", "stop", "result_R", "MFE_R", "MAE_R",
        ]
        if not master.empty:
            long_sample = master[master["direction"] == "LONG"].head(100)
            short_sample = master[master["direction"] == "SHORT"].head(100)
            write("phase4b1_structure_label_validation_sample.csv", self._cols(
                pd.concat([long_sample, short_sample], ignore_index=True), structure_cols))
            write("phase4b1_options_level_validation_sample.csv", self._cols(
                master.sort_values(["level_strength"], ascending=False).head(150),
                [
                    "parent_event_id", "source_namespace", "symbol", "trade_date", "timestamp",
                    "level_cluster_id", "level_price", "zone_low", "zone_high", "level_type",
                    "component_strikes", "level_rank", "GEX", "absolute_GEX", "OI", "combined_GEX",
                    "combined_OI", "distance_from_spot_ATR", "level_strength", "level_tier",
                    "intraday_persistence_state", "direction_class", "direction_confidence_0_100",
                    "direction_evidence", "direction_conflicts",
                ]))
        else:
            write("phase4b1_structure_label_validation_sample.csv", pd.DataFrame(columns=structure_cols))
            write("phase4b1_options_level_validation_sample.csv", pd.DataFrame())
        return outputs

    def _dashboard_status(self, master: pd.DataFrame, branches: pd.DataFrame, outputs: dict[str, str]) -> dict[str, Any]:
        options = branches[branches.get("is_control") == False] if not branches.empty else pd.DataFrame()
        canonical = options[
            (options.get("management_variant") == "TM_V0_CURRENT")
            & (options.get("stop_variant") == "STOP_A_CURRENT_STRUCTURAL")
        ] if not options.empty else pd.DataFrame()
        losses = canonical[pd.to_numeric(canonical.get("result_R"), errors="coerce") < 0] if not canonical.empty else pd.DataFrame()
        winners = canonical[pd.to_numeric(canonical.get("result_R"), errors="coerce") > 0] if not canonical.empty else pd.DataFrame()
        raw_directional_edge = round(float(pd.to_numeric(master.get("MFE_R"), errors="coerce").mean()), 4) if not master.empty and "MFE_R" in master else None
        canonical_stats = stat_summary(canonical["result_R"]) if not canonical.empty else stat_summary([])
        direction_correct = None
        if not master.empty:
            mfe = pd.to_numeric(master.get("MFE_R"), errors="coerce").fillna(0)
            direction_correct = round(float(((master["predicted_direction"] == master["direction"]) & (mfe >= 0.5)).mean()), 4)
        loss_reason_counts = Counter(losses.get("primary_loss_reason", [])) if not losses.empty else Counter()
        biggest_loss_source = "UNKNOWN"
        if not losses.empty:
            by_reason = (
                losses.assign(negative_abs_R=pd.to_numeric(losses["result_R"], errors="coerce").abs())
                .groupby("primary_loss_reason", dropna=False)["negative_abs_R"]
                .sum()
                .sort_values(ascending=False)
            )
            if not by_reason.empty:
                biggest_loss_source = str(by_reason.index[0])
        dashboard = {
            "generated_at_utc": self.generated_at,
            "status": "GENERATED",
            "research_only": True,
            "canonical_strategy_unchanged": True,
            "live_trading_disabled": True,
            "portfolio_os_isolated": True,
            "parent_events": int(len(master)),
            "counterfactual_branches": int(len(branches)),
            "raw_directional_edge": raw_directional_edge,
            "canonical_expectancy": canonical_stats["expectancy"],
            "canonical_profit_factor": canonical_stats["PF"],
            "loser_reached_0_5R_rate": self._rate(losses, "reached_0_5R"),
            "loser_reached_0_7R_rate": self._rate(losses, "reached_0_7R"),
            "loser_reached_1R_rate": self._rate(losses, "reached_1R"),
            "median_winner_MAE": self._percentile(winners, "MAE_R", 0.5),
            "median_MFE": self._percentile(canonical, "MFE_R", 0.5),
            "median_time_to_MFE": self._percentile(canonical, "time_to_MFE_minutes", 0.5),
            "stop_too_tight_rate": self._rate(losses[losses.get("primary_loss_reason") == "BAD_STOP"] if not losses.empty else losses, None, denominator=len(losses)),
            "stop_then_recovery_rate": self._rate(losses[losses.get("path_shape") == "STOP_THEN_RECOVERY_CANDIDATE"] if not losses.empty else losses, None, denominator=len(losses)),
            "giveback_rate": self._rate(losses[losses.get("giveback_bucket").astype(str).str.contains("THEN_LOSS", na=False)] if not losses.empty else losses, None, denominator=len(losses)),
            "BE_then_target_rate": None,
            "direction_classifier_accuracy": direction_correct,
            "structure_confirmed_expectancy": stat_summary(canonical[canonical.get("structure_alignment").isin(["FULL_ALIGNMENT", "PARTIAL_ALIGNMENT"])]["result_R"])["expectancy"] if not canonical.empty else None,
            "current_biggest_loss_source": biggest_loss_source,
            "component_scorecard": self._component_scorecard(master, canonical),
            "outputs": outputs,
        }
        return dashboard

    @staticmethod
    def _rate(df: pd.DataFrame, column: str | None, denominator: int | None = None) -> float | None:
        if df is None or df.empty:
            return 0.0 if denominator else None
        if column is None:
            return round(float(len(df) / denominator), 4) if denominator else None
        if column not in df.columns:
            return None
        return round(float(df[column].fillna(False).astype(bool).mean()), 4)

    def _component_scorecard(self, master: pd.DataFrame, canonical: pd.DataFrame) -> dict[str, dict[str, Any]]:
        base_expectancy = stat_summary(canonical["result_R"])["expectancy"] if not canonical.empty else None
        strong = canonical[canonical.get("level_tier").isin(["LEVEL_TIER_S", "LEVEL_TIER_A"])] if not canonical.empty else pd.DataFrame()
        structure = canonical[canonical.get("structure_alignment").isin(["FULL_ALIGNMENT", "PARTIAL_ALIGNMENT"])] if not canonical.empty else pd.DataFrame()
        direction = canonical[canonical.get("predicted_direction") == canonical.get("direction")] if not canonical.empty else pd.DataFrame()
        entries = canonical[canonical.get("entry_quality_class") == "ON_TIME_ENTRY"] if not canonical.empty else pd.DataFrame()
        high_quality = canonical[canonical.get("diagnostic_data_quality").isin(["FULL", "PARTIAL", "LIMITED"])] if not canonical.empty else pd.DataFrame()
        strong_stats = stat_summary(strong["result_R"]) if not strong.empty else stat_summary([])
        direction_stats = stat_summary(direction["result_R"]) if not direction.empty else stat_summary([])
        structure_stats = stat_summary(structure["result_R"]) if not structure.empty else stat_summary([])
        entry_stats = stat_summary(entries["result_R"]) if not entries.empty else stat_summary([])
        return {
            "OPTIONS_LEVEL_SELECTION": self._scorecard_item(base_expectancy, strong_stats["expectancy"], strong_stats["N"]),
            "DIRECTION_CLASSIFICATION": self._scorecard_item(base_expectancy, direction_stats["expectancy"], direction_stats["N"]),
            "MARKET_STRUCTURE": self._scorecard_item(base_expectancy, structure_stats["expectancy"], structure_stats["N"]),
            "ENTRY_TIMING": self._scorecard_item(base_expectancy, entry_stats["expectancy"], entry_stats["N"]),
            "STOP_LOGIC": {"status": "WEAK", "evidence": "Stop variants are diagnostic only; stopped-trade recovery requires lower-timeframe/post-stop tracking."},
            "TARGET_LOGIC": {"status": "WEAK", "evidence": "MFE reach rates exceed realized capture in several loss/giveback buckets."},
            "BREAKEVEN_LOGIC": {"status": "UNKNOWN", "evidence": "Current artifacts do not reliably store post-BE path continuation."},
            "MANAGEMENT": {"status": "WEAK" if base_expectancy is not None and base_expectancy < 0 else "UNKNOWN", "evidence": f"Canonical diagnostic expectancy {base_expectancy}."},
            "DATA_QUALITY": {"status": "PASS" if len(high_quality) else "UNKNOWN", "evidence": f"{len(high_quality)} branches have usable diagnostic data-quality labels."},
        }

    @staticmethod
    def _scorecard_item(base: float | None, filtered: float | None, n: int) -> dict[str, Any]:
        if filtered is None or n < 30:
            return {"status": "UNKNOWN", "evidence": f"N={n}; insufficient or unavailable filtered sample."}
        if base is not None and filtered > base and filtered > 0:
            status = "PASS"
        elif base is not None and filtered > base:
            status = "WEAK"
        else:
            status = "FAIL" if filtered < 0 else "WEAK"
        return {"status": status, "evidence": f"N={n}; expectancy={filtered}; base_expectancy={base}."}

    def _render_report(
        self,
        master: pd.DataFrame,
        branches: pd.DataFrame,
        outputs: dict[str, str],
        dashboard: dict[str, Any],
        live_setup_rows: int,
        live_trade_rows: int,
    ) -> str:
        options = branches[branches.get("is_control") == False] if not branches.empty else pd.DataFrame()
        controls = branches[branches.get("is_control") == True] if not branches.empty else pd.DataFrame()
        canonical = options[
            (options.get("management_variant") == "TM_V0_CURRENT")
            & (options.get("stop_variant") == "STOP_A_CURRENT_STRUCTURAL")
        ] if not options.empty else pd.DataFrame()
        losses = canonical[pd.to_numeric(canonical.get("result_R"), errors="coerce") < 0] if not canonical.empty else pd.DataFrame()
        tm0 = stat_summary(options[options.get("management_variant") == "TM_V0_CURRENT"]["result_R"]) if not options.empty else stat_summary([])
        tm3 = stat_summary(options[options.get("management_variant") == "TM_V3_TP1_PLUS_RUNNER"]["result_R"]) if not options.empty else stat_summary([])
        control_stats = stat_summary(controls["result_R"]) if not controls.empty else stat_summary([])
        canonical_stats = stat_summary(canonical["result_R"]) if not canonical.empty else stat_summary([])
        direction_rows = pd.read_csv(self.root / "phase4b1_direction_classifier.csv") if (self.root / "phase4b1_direction_classifier.csv").exists() else pd.DataFrame()
        classifier_stats = self._classifier_answer(direction_rows)
        loss_attr = pd.read_csv(self.root / "phase4b1_loss_attribution.csv") if (self.root / "phase4b1_loss_attribution.csv").exists() else pd.DataFrame()
        top_loss = loss_attr.head(5).to_dict("records") if not loss_attr.empty else []
        edge_funnel = self._edge_funnel(canonical)
        info_contribution = self._information_contribution(canonical, controls)

        lines = [
            "# Phase 4B.1 Full Edge Decomposition",
            "",
            f"Generated: {self.generated_at}",
            "",
            "Research-only diagnostic. Canonical strategy behavior, paper gates, watchlist, macro guard, live-trading disabled state, and Portfolio OS isolation were not changed.",
            "",
            "## Top questions",
            "",
            f"1. Raw options-level interactions show mean MFE of `{dashboard['raw_directional_edge']}` R before exits. This is directional excursion, not tradable edge by itself.",
            f"2. Direction classifier accuracy proxy: `{dashboard['direction_classifier_accuracy']}`. {classifier_stats}",
            f"3. Structure-confirmed canonical expectancy: `{dashboard['structure_confirmed_expectancy']}` R versus overall canonical `{dashboard['canonical_expectancy']}` R.",
            f"4. Entry timing is classified from stored delay/distance fields; current artifacts are strongest for historical Phase 4A-H and limited for live DB records.",
            f"5. Losers reaching +0.5R/+0.7R/+1R before final loss: `{dashboard['loser_reached_0_5R_rate']}` / `{dashboard['loser_reached_0_7R_rate']}` / `{dashboard['loser_reached_1R_rate']}`.",
            f"6. Median MFE: `{dashboard['median_MFE']}` R. Median time-to-MFE: `{dashboard['median_time_to_MFE']}` minutes where available.",
            f"7. Canonical stop efficiency is weak/unknown, because post-stop continuation is not fully stored. Winner MAE percentiles are exported in `phase4b1_stop_efficiency.csv`.",
            "8. Stop preservation thresholds are in `phase4b1_stop_efficiency.csv`; they are diagnostic thresholds, not recommendations.",
            "9. Stop-then-recovery is only a candidate label until lower-timeframe/post-stop continuation is captured prospectively.",
            "10. Target ambition is evaluated with the target-reach ladder in `phase4b1_target_efficiency.csv`.",
            "11. Natural MFE distribution and horizons are exported in `phase4b1_raw_excursion.csv` and `phase4b1_holding_horizon.csv`.",
            "12. Breakeven leakage is not fully measurable from current artifacts; the report marks post-BE path tracking unavailable.",
            f"13. TM_V0 expectancy `{tm0['expectancy']}` / PF `{tm0['PF']}`; TM_V3 expectancy `{tm3['expectancy']}` / PF `{tm3['PF']}`.",
            "14. Management capture is exported in `phase4b1_management_capture.csv`.",
            "15. Level roles with directional value are summarized in `phase4b1_level_role_analysis.csv`.",
            "16. 15m-vs-5m structure comparison remains Phase 4A/4A-H context; this layer decomposes why branches win/lose.",
            f"17. Largest associated loss source: `{dashboard['current_biggest_loss_source']}`.",
            "18. Single largest avoidable-loss candidate is the largest loss-attribution bucket; it must become a prospective branch before any canonical change.",
            "",
            "## Dataset reconciliation",
            "",
            f"- Master parent events: `{len(master)}`",
            f"- Counterfactual/research branches: `{len(branches)}`",
            f"- Live setup rows read-only inspected: `{live_setup_rows}`",
            f"- Live paper trade rows read-only inspected: `{live_trade_rows}`",
            f"- Historical Phase 4A-H source: `{int((master.get('source_namespace') == 'PHASE_4A_HISTORICAL').sum()) if not master.empty else 0}` parent events",
            f"- Live natural paper source: `{int((master.get('source_namespace') == 'LIVE_NATURAL_PAPER').sum()) if not master.empty else 0}` parent events",
            "- Synthetic/test rows are excluded from the live-derived natural diagnostic set.",
            "- Branches are not counted as independent empirical setup events.",
            "",
            "## Canonical and control baseline",
            "",
            self._markdown_stats("Canonical/options branches", canonical_stats),
            self._markdown_stats("Matched/ordinary controls", control_stats),
            "",
            "## Edge funnel",
            "",
            self._table(edge_funnel),
            "",
            "## Information contribution test",
            "",
            self._table(info_contribution),
            "",
            "## Loss attribution",
            "",
            self._table(pd.DataFrame(top_loss)),
            "",
            "Use `ATTRIBUTABLE` only for data invalidity. Other rows are association tags, not causal proof.",
            "",
            "## Component scorecard",
            "",
        ]
        for component, item in dashboard["component_scorecard"].items():
            lines.append(f"- {component}: `{item['status']}` — {item['evidence']}")
        lines += [
            "",
            "## Next prospective experiments, ranked",
            "",
            "1. Direction/structure confirmation branch: freeze the Phase 4B.1 direction classifier plus deterministic 15m structure confirmation; require at least 100 parent events and 10+ independent trading days.",
            "2. Stop/invalidation branch: if prospective stop-then-recovery remains high, test structure/zone invalidation stops as a separate research branch; fail if max drawdown worsens materially.",
            "3. Target/capture branch: if raw MFE remains positive while capture stays weak, test fixed 0.7R/1R and runner variants separately for LONG and SHORT; fail if PF does not improve in forward holdout.",
            "",
            "No canonical promotion is justified from this retrospective diagnostic alone.",
            "",
            "## Output files",
            "",
        ]
        for name in sorted(outputs):
            lines.append(f"- `{name}`")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _markdown_stats(label: str, stats: Mapping[str, Any]) -> str:
        return (
            f"- {label}: N `{stats.get('N')}`, expectancy `{stats.get('expectancy')}` R, "
            f"PF `{stats.get('PF')}`, win rate `{stats.get('win_rate')}`, max DD `{stats.get('max_drawdown')}` R."
        )

    @staticmethod
    def _table(df: pd.DataFrame) -> str:
        if df.empty:
            return "_No rows available._"
        rows = df.head(20).copy()
        columns = [str(column) for column in rows.columns]
        lines = [
            "| " + " | ".join(columns) + " |",
            "| " + " | ".join("---" for _ in columns) + " |",
        ]
        for record in rows.to_dict("records"):
            values = []
            for column in rows.columns:
                value = record.get(column)
                text = "" if value is None or (isinstance(value, float) and math.isnan(value)) else str(value)
                values.append(text.replace("|", "\\|").replace("\n", " "))
            lines.append("| " + " | ".join(values) + " |")
        return "\n".join(lines)

    def _classifier_answer(self, rows: pd.DataFrame) -> str:
        if rows.empty:
            return "Classifier output unavailable."
        summary = rows.groupby("direction_model")["direction_correct_0_5R_proxy"].mean().reset_index()
        best = summary.sort_values("direction_correct_0_5R_proxy", ascending=False).head(1)
        if best.empty:
            return "Classifier comparison unavailable."
        return f"Best direction proxy in this pass: `{best.iloc[0]['direction_model']}` at `{round(float(best.iloc[0]['direction_correct_0_5R_proxy']), 4)}`."

    def _edge_funnel(self, canonical: pd.DataFrame) -> pd.DataFrame:
        if canonical.empty:
            return pd.DataFrame()
        layers = []
        current = canonical
        definitions = [
            ("LAYER_0_ALL_VALID_OPTIONS_LEVEL_INTERACTIONS", current),
            ("LAYER_1_STRONG_OPTIONS_LEVEL", current[current["level_tier"].isin(["LEVEL_TIER_S", "LEVEL_TIER_A"])]),
            ("LAYER_2_CORRECT_DIRECTION_CLASSIFICATION", current[current["predicted_direction"] == current["direction"]]),
            ("LAYER_3_MARKET_STRUCTURE_CONFIRMATION", current[current["structure_alignment"].isin(["FULL_ALIGNMENT", "PARTIAL_ALIGNMENT"])]),
            ("LAYER_4_TIMEFRAME_CONFIRMATION_15M", current[current["confirmation_tf"].astype(str).str.contains("15m", na=False)]),
            ("LAYER_5_ENTRY_TIMING_ON_TIME", current[current["entry_quality_class"] == "ON_TIME_ENTRY"]),
            ("LAYER_6_STOP_INVALIDATION_DIAGNOSTIC", current[current["primary_loss_reason"] != "BAD_STOP"]),
            ("LAYER_7_TARGET_MANAGEMENT_DIAGNOSTIC", current[current["primary_loss_reason"] != "BAD_MANAGEMENT"]),
        ]
        for layer, frame in definitions:
            stats = stat_summary(frame["result_R"])
            layers.append({
                "layer": layer,
                "N": stats["N"],
                "unique_days": int(frame["trade_date"].nunique()) if "trade_date" in frame else None,
                "MFE": round(float(pd.to_numeric(frame.get("MFE_R"), errors="coerce").mean()), 4) if not frame.empty else None,
                "MAE": round(float(pd.to_numeric(frame.get("MAE_R"), errors="coerce").mean()), 4) if not frame.empty else None,
                "directional_success_0_5R": self._rate(frame, "reached_0_5R"),
                "P_0_7R_before_minus_1R": self._rate(frame, "hit_0_7R_before_minus_1R"),
                "P_1R_before_minus_1R": self._rate(frame, "hit_1R_before_minus_1R"),
                "expectancy": stats["expectancy"],
                "PF": stats["PF"],
            })
        return pd.DataFrame(layers)

    def _information_contribution(self, canonical: pd.DataFrame, controls: pd.DataFrame) -> pd.DataFrame:
        rows = []
        groups = [
            ("BASE_PRICE_INTERACTION_ONLY", controls),
            ("PLUS_OPTIONS_LEVEL", canonical),
            ("PLUS_LEVEL_STRENGTH", canonical[canonical["level_tier"].isin(["LEVEL_TIER_S", "LEVEL_TIER_A"])] if not canonical.empty else canonical),
            ("PLUS_LEVEL_DIRECTION", canonical[canonical["predicted_direction"] == canonical["direction"]] if not canonical.empty else canonical),
            ("PLUS_MARKET_STRUCTURE", canonical[canonical["structure_alignment"].isin(["FULL_ALIGNMENT", "PARTIAL_ALIGNMENT"])] if not canonical.empty else canonical),
            ("PLUS_MARKET_ALIGNMENT", canonical[canonical["structure_alignment"] == "FULL_ALIGNMENT"] if not canonical.empty else canonical),
            ("PLUS_LEVEL_PERSISTENCE", canonical[canonical.get("intraday_persistence_state", pd.Series(dtype=str)).isin(["PERSISTENT", "STRENGTHENING"])] if not canonical.empty and "intraday_persistence_state" in canonical else pd.DataFrame()),
        ]
        for label, frame in groups:
            stats = stat_summary(frame["result_R"]) if not frame.empty and "result_R" in frame else stat_summary([])
            rows.append({
                "component_set": label,
                "N": stats["N"],
                "unique_days": int(frame["trade_date"].nunique()) if not frame.empty and "trade_date" in frame else 0,
                "directional_hit_0_5R": self._rate(frame, "reached_0_5R") if not frame.empty else None,
                "P_1R_before_minus_1R": self._rate(frame, "hit_1R_before_minus_1R") if not frame.empty else None,
                "MFE_MAE_ratio": round(float(pd.to_numeric(frame.get("MFE_MAE_ratio"), errors="coerce").mean()), 4) if not frame.empty and "MFE_MAE_ratio" in frame else None,
                "expectancy": stats["expectancy"],
                "PF": stats["PF"],
            })
        return pd.DataFrame(rows)
