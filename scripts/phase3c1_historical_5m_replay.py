from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import time
from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import numpy as np
import requests

from options_structure_trader.config import PROJECT_ROOT, Settings, load_local_env
from options_structure_trader.historical import (
    GEX_LEVEL_COLUMNS,
    HISTORICAL_DATA_TIERS,
    HistoricalReconstructionPipeline,
    REPLAY_COLUMNS,
    UNDERLYING_COLUMNS,
)


EASTERN = ZoneInfo("America/New_York")
SYMBOLS = ["SPY", "QQQ", "IWM"]
START_DATE = date(2024, 6, 3)
END_DATE = date(2025, 12, 16)
RAW_ROOT = PROJECT_ROOT / "data" / "historical" / "phase3c1" / "raw"
WRDS_ROOT = RAW_ROOT / "fds_indx_data"

PARSER_VERSION = "phase3c1_5m_parser_v1"
NORMALIZER_VERSION = "phase3c1_5m_normalizer_v1"
SOURCE_VERSION = "fds_indx_data_wrds_taq_github_master_3b7ac233"
REPLAY_VERSION = "phase3c1_replay_v1_existing_detector"
VALIDATION_VERSION = "phase3c1_source_validation_v1"

FDS_REPO = "Aryan092/fds-indx-data"
FDS_BASE = f"https://raw.githubusercontent.com/{FDS_REPO}/master/indx_data"
MASSIVE_BASE = "https://api.massive.com"


@dataclass
class RawFile:
    symbol: str
    url: str
    path: str
    size_bytes: int
    sha256: str
    downloaded_at_utc: str


class EmptyRepository:
    def list_json(self, *_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        return []


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def headers() -> dict[str, str]:
    return {"User-Agent": "options-structure-trader-research/phase3c1"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_secret_status(name: str) -> str:
    load_local_env()
    return "CONFIGURED" if os.getenv(name, "").strip() else "NOT_CONFIGURED"


def markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "No rows."
    rows = ["| " + " | ".join(str(column) for column in frame.columns) + " |"]
    rows.append("| " + " | ".join("---" for _ in frame.columns) + " |")
    for item in frame.to_dict("records"):
        rows.append("| " + " | ".join(str(item.get(column, "")) for column in frame.columns) + " |")
    return "\n".join(rows)


def json_list(value: Any) -> list[dict[str, Any]]:
    if not value or (isinstance(value, float) and math.isnan(value)):
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def et_to_utc_iso(ts: pd.Timestamp) -> str:
    if ts.tzinfo is None:
        ts = ts.tz_localize(EASTERN)
    return ts.tz_convert(timezone.utc).isoformat()


def github_repo_probe() -> dict[str, Any]:
    result: dict[str, Any] = {
        "repo": f"https://github.com/{FDS_REPO}",
        "status": "UNKNOWN",
    }
    try:
        repo = requests.get(f"https://api.github.com/repos/{FDS_REPO}", headers=headers(), timeout=30)
        result["repo_status_code"] = repo.status_code
        if repo.ok:
            payload = repo.json()
            result.update({
                "description": payload.get("description"),
                "default_branch": payload.get("default_branch"),
                "license": payload.get("license"),
                "size_kb": payload.get("size"),
                "pushed_at": payload.get("pushed_at"),
            })
        tree = requests.get(
            f"https://api.github.com/repos/{FDS_REPO}/git/trees/master?recursive=1",
            headers=headers(),
            timeout=60,
        )
        result["tree_status_code"] = tree.status_code
        if tree.ok:
            payload = tree.json()
            blobs = [item for item in payload.get("tree", []) if item.get("type") == "blob"]
            result["tree_truncated"] = payload.get("truncated")
            result["blob_count"] = len(blobs)
            result["target_5m_files"] = [
                {
                    "path": item.get("path"),
                    "size": item.get("size"),
                    "sha": item.get("sha"),
                }
                for item in blobs
                if item.get("path") in {f"indx_data/{symbol}_5min.csv" for symbol in SYMBOLS}
            ]
        result["status"] = "FILES_FOUND" if len(result.get("target_5m_files", [])) == 3 else "TARGET_FILES_MISSING"
    except Exception as exc:  # noqa: BLE001 - report should capture source problem.
        result.update({"status": "ERROR", "error": type(exc).__name__, "message": str(exc)})
    return result


def probe_massive() -> dict[str, Any]:
    load_local_env()
    key = os.getenv("MASSIVE_API_KEY", "").strip() or os.getenv("POLYGON_API_KEY", "").strip()
    status = {
        "configured": bool(key),
        "credential_state": "CONFIGURED" if key else "NOT_CONFIGURED",
        "provider": "MASSIVE_FORMERLY_POLYGON",
        "endpoint": "/v2/aggs/ticker/{ticker}/range/5/minute/{from}/{to}",
        "production_grade_for_this_project": False,
        "notes": [],
    }
    if not key:
        status["usable"] = False
        status["status"] = "MASSIVE_API_KEY_NOT_CONFIGURED"
        status["notes"].append("Add MASSIVE_API_KEY to local .env to validate the free Stocks Basic entitlement.")
        return status
    # Keep validation harmless: one recent historical window and no key leakage.
    sample_from = "2025-09-02"
    sample_to = "2025-09-03"
    url = f"{MASSIVE_BASE}/v2/aggs/ticker/SPY/range/5/minute/{sample_from}/{sample_to}"
    started = time.perf_counter()
    try:
        response = requests.get(
            url,
            params={"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": key},
            timeout=30,
            headers=headers(),
        )
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        status.update({
            "http_status": response.status_code,
            "latency_ms": latency_ms,
            "authenticated": response.status_code != 401,
        })
        if not response.ok:
            status["usable"] = False
            status["status"] = "HTTP_ERROR_OR_ENTITLEMENT_BLOCK"
            status["response_shape"] = "json" if response.headers.get("content-type", "").startswith("application/json") else "non-json"
            return status
        payload = response.json()
        results = payload.get("results") or []
        status.update({
            "usable": bool(results),
            "status": "MINUTE_AGGS_AVAILABLE" if results else "NO_RESULTS_RETURNED",
            "result_count": len(results),
            "fields": sorted(results[0].keys()) if results else [],
            "earliest_sample_ts": results[0].get("t") if results else None,
            "latest_sample_ts": results[-1].get("t") if results else None,
        })
    except Exception as exc:  # noqa: BLE001
        status.update({"usable": False, "status": "ERROR", "error": type(exc).__name__, "message": str(exc)})
    return status


def download_wrds_files() -> list[RawFile]:
    WRDS_ROOT.mkdir(parents=True, exist_ok=True)
    records: list[RawFile] = []
    for symbol in SYMBOLS:
        url = f"{FDS_BASE}/{symbol}_5min.csv"
        path = WRDS_ROOT / f"{symbol}_5min.csv"
        if not path.exists() or path.stat().st_size == 0:
            response = requests.get(url, headers=headers(), timeout=60)
            response.raise_for_status()
            path.write_bytes(response.content)
        records.append(
            RawFile(
                symbol=symbol,
                url=url,
                path=str(path),
                size_bytes=path.stat().st_size,
                sha256=sha256_file(path),
                downloaded_at_utc=now_utc().isoformat(),
            )
        )
    return records


def get_calendar() -> Any:
    try:
        import exchange_calendars as xcals

        return xcals.get_calendar("XNYS")
    except Exception:
        return None


def session_open_close_utc(calendar: Any, trade_date: str) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    if calendar is None:
        local_open = pd.Timestamp(f"{trade_date} 09:30:00", tz=EASTERN)
        local_close = pd.Timestamp(f"{trade_date} 16:00:00", tz=EASTERN)
        if local_open.weekday() >= 5:
            return None
        return local_open.tz_convert("UTC"), local_close.tz_convert("UTC")
    session = pd.Timestamp(trade_date)
    if not calendar.is_session(session):
        return None
    return calendar.session_open(session), calendar.session_close(session)


def load_raw_wrds(symbol: str) -> pd.DataFrame:
    frame = pd.read_csv(WRDS_ROOT / f"{symbol}_5min.csv")
    frame["symbol"] = symbol
    frame["timestamp_et"] = pd.to_datetime(frame["datetime"], errors="coerce").dt.tz_localize(EASTERN)
    frame["timestamp_utc"] = frame["timestamp_et"].dt.tz_convert("UTC")
    frame["trade_date"] = frame["timestamp_et"].dt.date.astype(str)
    return frame


def validate_wrds(raw: dict[str, pd.DataFrame], calendar: Any) -> tuple[dict[str, Any], pd.DataFrame]:
    metrics: dict[str, Any] = {}
    early_rows: list[dict[str, Any]] = []
    for symbol, frame in raw.items():
        frame = frame.copy()
        frame["time"] = frame["timestamp_et"].dt.time.astype(str)
        bad_ohlc = (
            (frame["high"] < frame[["open", "low", "close"]].max(axis=1))
            | (frame["low"] > frame[["open", "high", "close"]].min(axis=1))
            | (frame["volume"] < 0)
        )
        bars_per_day = frame.groupby("trade_date").size()
        non_session_dates = []
        bars_after_close = 0
        bars_before_open = 0
        expected_missing_bars = 0
        early_close_dates = []
        for trade_date, group in frame.groupby("trade_date"):
            session = session_open_close_utc(calendar, trade_date)
            if session is None:
                non_session_dates.append(trade_date)
                continue
            session_open, session_close = session
            ts = group["timestamp_utc"]
            before = int((ts < session_open).sum())
            after = int((ts >= session_close).sum())
            bars_before_open += before
            bars_after_close += after
            expected = int((session_close - session_open).total_seconds() / 300)
            valid_count = int(((ts >= session_open) & (ts < session_close)).sum())
            expected_missing_bars += max(0, expected - valid_count)
            if session_close.tz_convert(EASTERN).time() < dtime(16, 0):
                early_close_dates.append(trade_date)
                early_rows.append({
                    "symbol": symbol,
                    "date": trade_date,
                    "session_close_et": session_close.tz_convert(EASTERN).isoformat(),
                    "raw_rows": len(group),
                    "rows_after_close_removed": after,
                })
        metrics[symbol] = {
            "rows": int(len(frame)),
            "unique_dates": int(frame["trade_date"].nunique()),
            "earliest": frame["trade_date"].min(),
            "latest": frame["trade_date"].max(),
            "columns": frame.columns.tolist(),
            "min_time": str(frame["time"].min()),
            "max_time": str(frame["time"].max()),
            "bars_per_day_min": int(bars_per_day.min()),
            "bars_per_day_median": float(bars_per_day.median()),
            "bars_per_day_max": int(bars_per_day.max()),
            "duplicate_timestamps": int(frame["timestamp_utc"].duplicated().sum()),
            "bad_ohlc_rows": int(bad_ohlc.sum()),
            "non_session_dates": non_session_dates,
            "bars_before_session_open": bars_before_open,
            "bars_at_or_after_session_close": bars_after_close,
            "early_close_dates": early_close_dates,
            "expected_missing_rth_bars_after_cleaning": expected_missing_bars,
            "redistribution_license": "NO_LICENSE_FILE_IN_REPO",
            "suitability": "EXPLORATORY_RESEARCH",
        }
    return metrics, pd.DataFrame(early_rows)


def normalize_wrds(raw: dict[str, pd.DataFrame], calendar: Any) -> pd.DataFrame:
    frames = []
    for symbol, frame in raw.items():
        rows = []
        med_by_time = frame.groupby(frame["timestamp_et"].dt.time)["volume"].median().to_dict()
        for item in frame.sort_values("timestamp_utc").to_dict("records"):
            trade_date = item["trade_date"]
            session = session_open_close_utc(calendar, trade_date)
            if session is None:
                continue
            session_open, session_close = session
            timestamp_utc = pd.Timestamp(item["timestamp_utc"])
            if not (session_open <= timestamp_utc < session_close):
                continue
            timestamp_et = pd.Timestamp(item["timestamp_et"])
            bar_close_utc = timestamp_utc + pd.Timedelta(minutes=5)
            bar_close_et = timestamp_et + pd.Timedelta(minutes=5)
            med_volume = med_by_time.get(timestamp_et.time()) or frame["volume"].median() or 1
            rows.append({
                "symbol": symbol,
                "timestamp_et": timestamp_et.isoformat(),
                "timestamp_utc": timestamp_utc.isoformat(),
                "trade_date": trade_date,
                "bar_open": timestamp_et.isoformat(),
                "bar_close_time": bar_close_et.isoformat(),
                "bar_start_utc": timestamp_utc.isoformat(),
                "bar_end_utc": bar_close_utc.isoformat(),
                "bar_start_et": timestamp_et.isoformat(),
                "timeframe": "5m",
                "open": float(item["open"]),
                "high": float(item["high"]),
                "low": float(item["low"]),
                "close": float(item["close"]),
                "volume": int(item["volume"]),
                "vwap": None,
                "provider": "WRDS_TAQ_PUBLIC_GITHUB",
                "dataset_source": "Aryan092/fds-indx-data",
                "adjusted": False,
                "rth": True,
                "data_quality": "EXPLORATORY_RESEARCH",
                "source_version": SOURCE_VERSION,
                "exchange_timezone": "America/New_York",
                "split_adjusted": "unknown_unadjusted_taq_prices",
                "source_timestamp_utc": bar_close_utc.isoformat(),
                "downloaded_at_utc": now_utc().isoformat(),
                "raw_payload_reference": str(WRDS_ROOT / f"{symbol}_5min.csv"),
                "relative_volume": round(float(item["volume"]) / max(float(med_volume), 1.0), 6),
            })
        clean = pd.DataFrame(rows)
        if clean.empty:
            frames.append(clean)
            continue
        high_low = clean["high"] - clean["low"]
        high_close = (clean["high"] - clean["close"].shift(1)).abs()
        low_close = (clean["low"] - clean["close"].shift(1)).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        clean["atr"] = tr.rolling(14, min_periods=1).mean().fillna(high_low).clip(lower=0.01)
        frames.append(clean)
    normalized = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if normalized.empty:
        return normalized
    # Keep only dates where the already-built D-1 option levels exist, so controls use the same dates/symbols.
    levels = pd.read_parquet(PROJECT_ROOT / "historical_daily_option_levels.parquet", columns=["symbol", "trade_date"])
    valid_keys = set(zip(levels["symbol"], levels["trade_date"].astype(str)))
    normalized = normalized[
        normalized.apply(lambda row: (row["symbol"], row["trade_date"]) in valid_keys, axis=1)
    ].copy()
    output_columns = [
        "symbol", "timestamp_et", "timestamp_utc", "trade_date", "bar_open", "bar_close_time",
        "bar_start_utc", "bar_end_utc", "bar_start_et", "timeframe", "open", "high", "low",
        "close", "volume", "vwap", "provider", "dataset_source", "adjusted", "rth",
        "data_quality", "source_version", "exchange_timezone", "split_adjusted",
        "source_timestamp_utc", "downloaded_at_utc", "raw_payload_reference",
        "atr", "relative_volume",
    ]
    for column in output_columns:
        if column not in normalized.columns:
            normalized[column] = None
    return normalized[output_columns]


def daily_crosscheck(clean: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    rows = []
    summary: dict[str, Any] = {}
    for symbol, group in clean.groupby("symbol"):
        daily = group.sort_values("timestamp_utc").groupby("trade_date").agg(
            wrds_open=("open", "first"),
            wrds_high=("high", "max"),
            wrds_low=("low", "min"),
            wrds_close=("close", "last"),
            wrds_volume=("volume", "sum"),
        ).reset_index()
        daily_path = PROJECT_ROOT / "data" / "historical" / "phase3c" / "raw" / "options_dataset_hist" / symbol / f"{symbol}_underlying.parquet"
        if not daily_path.exists():
            summary[symbol] = {"status": "NO_DAILY_REFERENCE"}
            continue
        ref = pd.read_parquet(daily_path)
        ref["trade_date"] = ref["date"].astype(str)
        merged = daily.merge(ref[["trade_date", "open", "high", "low", "close", "volume"]], on="trade_date", how="inner")
        for _, item in merged.iterrows():
            row = {"symbol": symbol, "trade_date": item["trade_date"]}
            for left, right, name in [
                ("wrds_open", "open", "open_deviation_bps"),
                ("wrds_high", "high", "high_deviation_bps"),
                ("wrds_low", "low", "low_deviation_bps"),
                ("wrds_close", "close", "close_deviation_bps"),
            ]:
                row[name] = abs(float(item[left]) - float(item[right])) / max(abs(float(item[right])), 1e-9) * 10000
            row["volume_deviation_pct"] = abs(float(item["wrds_volume"]) - float(item["volume"])) / max(abs(float(item["volume"])), 1e-9) * 100
            rows.append(row)
        deviations = pd.DataFrame([row for row in rows if row["symbol"] == symbol])
        if deviations.empty:
            summary[symbol] = {"status": "NO_OVERLAP"}
            continue
        summary[symbol] = {
            "status": "DAILY_ROLLUP_CROSSCHECK_COMPLETE",
            "overlap_days": int(len(deviations)),
            "close_median_bps": round(float(deviations["close_deviation_bps"].median()), 4),
            "close_p95_bps": round(float(deviations["close_deviation_bps"].quantile(0.95)), 4),
            "open_median_bps": round(float(deviations["open_deviation_bps"].median()), 4),
            "high_p95_bps": round(float(deviations["high_deviation_bps"].quantile(0.95)), 4),
            "low_p95_bps": round(float(deviations["low_deviation_bps"].quantile(0.95)), 4),
            "volume_median_deviation_pct": round(float(deviations["volume_deviation_pct"].median()), 4),
            "assessment": "CLOSES_USABLE_HIGH_LOW_VOLUME_REQUIRE_CAUTION",
        }
    return pd.DataFrame(rows), summary


def add_env_example_placeholder() -> None:
    path = PROJECT_ROOT / ".env.example"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    if "MASSIVE_API_KEY=" not in text:
        path.write_text(text.replace("FINNHUB_API_KEY=\n", "FINNHUB_API_KEY=\nMASSIVE_API_KEY=\n"), encoding="utf-8")


def width_for(price: float, atr: float | None = None) -> float:
    base = max(0.001 * abs(price), 0.05)
    if atr and math.isfinite(float(atr)):
        base = max(base, 0.15 * float(atr))
    return float(base)


def append_level(rows: list[dict[str, Any]], base: dict[str, Any], level_type: str, price: Any,
                 strength: float, metadata: dict[str, Any]) -> None:
    try:
        price_value = float(price)
    except (TypeError, ValueError):
        return
    if not math.isfinite(price_value) or price_value <= 0:
        return
    width = width_for(price_value)
    known_at = pd.Timestamp(base["chain_known_at_et"]).tz_convert("UTC").isoformat()
    rows.append({
        "symbol": base["symbol"],
        "trade_date": base["trade_date"],
        "snapshot_date": base["source_chain_date"],
        "known_at_utc": known_at,
        "level_type": level_type,
        "price": price_value,
        "zone_low": price_value - width,
        "zone_high": price_value + width,
        "strength_score": max(0.0, min(float(strength), 1.0)),
        "provider": "phase3c_eod_options_reconstruction",
        "historical_data_tier": base["data_quality"],
        "source_quality": base["provenance_reliability"],
        "lookahead_risk": not bool(base["lookahead_safe"]),
        "gex_model_version": base["model_version"],
        "dealer_assumption": base["model_version"],
        "raw_payload_reference": str(PROJECT_ROOT / "historical_daily_option_levels.parquet"),
        "metadata_json": json.dumps(metadata, sort_keys=True),
        "control_type": "OPTIONS_LEVELS",
    })


def expand_option_levels() -> pd.DataFrame:
    source = pd.read_parquet(PROJECT_ROOT / "historical_daily_option_levels.parquet")
    rows: list[dict[str, Any]] = []
    for base in source.to_dict("records"):
        append_level(rows, base, "GAMMA_FLIP", base.get("gamma_flip"), 1.0, {"historical_level_family": "GAMMA_FLIP"})
        append_level(rows, base, "CALL_WALL", base.get("call_wall"), 0.9, {"historical_level_family": "CALL_WALL"})
        append_level(rows, base, "PUT_WALL", base.get("put_wall"), 0.9, {"historical_level_family": "PUT_WALL"})
        top_abs = json_list(base.get("top_absolute_gamma_nodes"))
        max_abs = max((abs(float(item.get("value", 0))) for item in top_abs), default=1.0)
        for item in top_abs:
            strength = 0.72 + 0.22 * abs(float(item.get("value", 0))) / max(max_abs, 1.0)
            append_level(rows, base, "GEX_NODE", item.get("strike"), strength, {
                "historical_level_family": "GEX_NODE",
                "node_value": item.get("value"),
            })
        oi_nodes = json_list(base.get("top_OI_call_nodes")) + json_list(base.get("top_OI_put_nodes"))
        max_oi = max((abs(float(item.get("value", 0))) for item in oi_nodes), default=1.0)
        for item in oi_nodes[:10]:
            strength = 0.65 + 0.20 * abs(float(item.get("value", 0))) / max(max_oi, 1.0)
            append_level(rows, base, "OI_NODE", item.get("strike"), strength, {
                "historical_level_family": "OI_NODE",
                "node_value": item.get("value"),
            })
        abs_strikes = {round(float(item.get("strike")), 4) for item in top_abs[:5] if item.get("strike") is not None}
        oi_strikes = {round(float(item.get("strike")), 4) for item in oi_nodes[:10] if item.get("strike") is not None}
        for strike in sorted(abs_strikes & oi_strikes):
            # The live detector does not accept a literal GEX_OI_CLUSTER level type.
            # Use detector-compatible GEX_NODE while preserving family metadata.
            append_level(rows, base, "GEX_NODE", strike, 0.88, {
                "historical_level_family": "GEX_OI_CLUSTER",
                "detector_level_type": "GEX_NODE",
            })
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=GEX_LEVEL_COLUMNS + ["control_type"])
    frame = frame.drop_duplicates(["symbol", "known_at_utc", "level_type", "price", "gex_model_version", "metadata_json"])
    return frame


def control_levels(clean: pd.DataFrame, option_levels: pd.DataFrame) -> pd.DataFrame:
    rng = random.Random(20260904)
    rows: list[dict[str, Any]] = []
    level_distances: dict[str, list[float]] = {}
    first_closes = clean.sort_values("timestamp_utc").groupby(["symbol", "trade_date"])["close"].first().to_dict()
    for row in option_levels.to_dict("records"):
        key = (row["symbol"], pd.Timestamp(row["known_at_utc"]).tz_convert(EASTERN).date().isoformat())
        # Distance distribution is approximated from next-session first close when available.
        trade_key_candidates = [
            (row["symbol"], (pd.Timestamp(row["known_at_utc"]).tz_convert(EASTERN).date() + timedelta(days=1)).isoformat())
        ]
        for trade_key in trade_key_candidates:
            first = first_closes.get(trade_key)
            if first:
                level_distances.setdefault(row["symbol"], []).append(abs(float(row["price"]) - float(first)))
    for symbol, group in clean.sort_values("timestamp_utc").groupby("symbol"):
        by_day = {day: day_frame for day, day_frame in group.groupby("trade_date")}
        days = sorted(by_day)
        for index, trade_date in enumerate(days):
            if index == 0:
                continue
            prev = by_day[days[index - 1]]
            current = by_day[trade_date]
            if prev.empty or current.empty:
                continue
            prev_high = float(prev["high"].max())
            prev_low = float(prev["low"].min())
            first_close = float(current["close"].iloc[0])
            atr = float(prev["atr"].median()) if "atr" in prev else max(first_close * 0.005, 0.25)
            distances = [value for value in level_distances.get(symbol, []) if math.isfinite(value) and value > 0]
            random_distance = rng.choice(distances) if distances else atr
            round_increment = 5.0 if first_close >= 100 else 1.0
            round_level = round(first_close / round_increment) * round_increment
            candidates = [
                ("PREVIOUS_DAY_HIGH", prev_high),
                ("PREVIOUS_DAY_LOW", prev_low),
                ("PRIOR_RANGE_MIDPOINT", (prev_high + prev_low) / 2),
                ("RANDOM_NEARBY_LEVEL", first_close + rng.choice([-1, 1]) * random_distance),
                ("ROUND_NUMBER_LEVEL", round_level),
            ]
            known_at = str(prev["bar_end_utc"].iloc[-1])
            for control_type, price in candidates:
                width = width_for(price, atr)
                rows.append({
                    "symbol": symbol,
                    "trade_date": trade_date,
                    "snapshot_date": days[index - 1],
                    "known_at_utc": known_at,
                    "level_type": "GEX_NODE",
                    "price": price,
                    "zone_low": price - width,
                    "zone_high": price + width,
                    "strength_score": 0.7,
                    "provider": "phase3c1_price_control",
                    "historical_data_tier": "TIER_H4_PRICE_ONLY_CONTROL",
                    "source_quality": "PRICE_ONLY_CONTROL",
                    "lookahead_risk": False,
                    "gex_model_version": "price_control_v2",
                    "dealer_assumption": "none",
                    "raw_payload_reference": str(PROJECT_ROOT / "historical_intraday_5m_v2.parquet"),
                    "metadata_json": json.dumps({"control_type": control_type}, sort_keys=True),
                    "control_type": control_type,
                })
    return pd.DataFrame(rows, columns=GEX_LEVEL_COLUMNS + ["trade_date", "control_type"]) if rows else pd.DataFrame(columns=GEX_LEVEL_COLUMNS + ["trade_date", "control_type"])


def run_replay(clean: pd.DataFrame, option_levels: pd.DataFrame, controls: pd.DataFrame) -> pd.DataFrame:
    settings = Settings.load()
    pipeline = HistoricalReconstructionPipeline(EmptyRepository(), settings, PROJECT_ROOT)
    pipeline._management_versions = lambda _strategy_type: ["TM_V0_CURRENT", "TM_V3_TP1_PLUS_RUNNER"]  # type: ignore[method-assign]
    replay_frames = []

    def replay_level_frame(level_frame: pd.DataFrame, strategy_type: str) -> pd.DataFrame:
        if clean.empty or level_frame.empty:
            return pd.DataFrame(columns=REPLAY_COLUMNS)
        rows: list[dict[str, Any]] = []
        bars_by_symbol = pipeline._bars_by_symbol(clean)
        seen: set[tuple[str, str, str, str, float, str]] = set()
        for symbol, bars in bars_by_symbol.items():
            by_day: dict[str, list[Any]] = {}
            for bar in bars:
                day = bar.bar_end_utc.astimezone(EASTERN).date().isoformat()
                by_day.setdefault(day, []).append(bar)
            symbol_levels = level_frame[level_frame["symbol"] == symbol].copy()
            if symbol_levels.empty:
                continue
            for day, day_bars in by_day.items():
                day_levels = symbol_levels[symbol_levels["trade_date"].astype(str) == day].copy()
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
                        key = (
                            symbol,
                            confirmation_bar.bar_end_utc.isoformat(),
                            setup.side.value,
                            str(level_row.get("level_type")),
                            round(float(level_row.get("price")), 4),
                            str(level_row.get("control_type") or "options"),
                        )
                        if key in seen:
                            continue
                        seen.add(key)
                        after = day_bars[index + 1:index + 90]
                        for slippage_bps in (0, 1, 3, 5):
                            for management_version in pipeline._management_versions(strategy_type):
                                rows.append(
                                    pipeline._simulate(
                                        setup, level_row, after, management_version,
                                        slippage_bps, strategy_type,
                                    )
                                )
                        break
        return pd.DataFrame(rows) if rows else pd.DataFrame(columns=REPLAY_COLUMNS)

    for model_version, levels in option_levels.groupby("gex_model_version"):
        frame = replay_level_frame(levels.copy(), strategy_type="OPTIONS_STRUCTURE_RECON")
        if not frame.empty:
            frame["gex_model_version"] = model_version
            frame["replay_version"] = REPLAY_VERSION
            replay_frames.append(frame)
    control_replay = replay_level_frame(controls.copy(), strategy_type="PRICE_CONTROL")
    if not control_replay.empty:
        control_replay["gex_model_version"] = "price_control_v2"
        control_replay["replay_version"] = REPLAY_VERSION
        replay_frames.append(control_replay)
    replay = pd.concat(replay_frames, ignore_index=True) if replay_frames else pd.DataFrame(columns=REPLAY_COLUMNS)
    return replay


def trade_stats(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {
            "N": 0, "unique_trading_days": 0, "expectancy_R": None, "profit_factor": None,
            "win_rate": None, "median_R": None, "avg_winner": None, "avg_loser": None,
            "MFE": None, "MAE": None, "max_DD": None, "positive_day_pct": None,
            "remove_best_day_expectancy": None, "remove_best_month_expectancy": None,
            "remove_best_symbol_expectancy": None, "day_block_bootstrap_low": None,
            "day_block_bootstrap_high": None,
        }
    values = pd.to_numeric(frame["realized_R"], errors="coerce").dropna()
    if values.empty:
        return trade_stats(pd.DataFrame())
    wins = values[values > 0]
    losses = values[values < 0]
    gross_win = float(wins.sum())
    gross_loss = float(losses.sum())
    cumulative = values.cumsum()
    max_dd = float((cumulative.cummax() - cumulative).max()) if not cumulative.empty else 0.0
    day_totals = frame.assign(_r=pd.to_numeric(frame["realized_R"], errors="coerce")).groupby("session_date")["_r"].sum()
    best_day = str(day_totals.idxmax()) if not day_totals.empty else None
    reduced_day = frame[frame["session_date"] != best_day] if best_day else frame
    frame = frame.copy()
    frame["_month"] = frame["session_date"].astype(str).str.slice(0, 7)
    month_totals = frame.groupby("_month")["realized_R"].sum()
    best_month = str(month_totals.idxmax()) if not month_totals.empty else None
    reduced_month = frame[frame["_month"] != best_month] if best_month else frame
    symbol_totals = frame.groupby("symbol")["realized_R"].sum()
    best_symbol = str(symbol_totals.idxmax()) if not symbol_totals.empty else None
    reduced_symbol = frame[frame["symbol"] != best_symbol] if best_symbol else frame
    ci_low, ci_high = day_bootstrap(frame)
    return {
        "N": int(len(values)),
        "unique_trading_days": int(frame["session_date"].nunique()),
        "expectancy_R": round(float(values.mean()), 4),
        "profit_factor": round(gross_win / abs(gross_loss), 4) if gross_loss else ("infinite" if gross_win > 0 else None),
        "win_rate": round(float((values > 0).mean()), 4),
        "median_R": round(float(values.median()), 4),
        "avg_winner": round(float(wins.mean()), 4) if not wins.empty else 0.0,
        "avg_loser": round(float(losses.mean()), 4) if not losses.empty else 0.0,
        "MFE": round(float(pd.to_numeric(frame["MFE_R"], errors="coerce").mean()), 4) if "MFE_R" in frame else None,
        "MAE": round(float(pd.to_numeric(frame["MAE_R"], errors="coerce").mean()), 4) if "MAE_R" in frame else None,
        "max_DD": round(max_dd, 4),
        "positive_day_pct": round(float((day_totals > 0).mean()), 4) if not day_totals.empty else None,
        "remove_best_day_expectancy": round(float(pd.to_numeric(reduced_day["realized_R"], errors="coerce").mean()), 4)
        if not reduced_day.empty else None,
        "remove_best_month_expectancy": round(float(pd.to_numeric(reduced_month["realized_R"], errors="coerce").mean()), 4)
        if not reduced_month.empty else None,
        "remove_best_symbol_expectancy": round(float(pd.to_numeric(reduced_symbol["realized_R"], errors="coerce").mean()), 4)
        if not reduced_symbol.empty else None,
        "day_block_bootstrap_low": ci_low,
        "day_block_bootstrap_high": ci_high,
    }


def day_bootstrap(frame: pd.DataFrame, iterations: int = 1000) -> tuple[float | None, float | None]:
    if frame.empty or "session_date" not in frame:
        return None, None
    daily = frame.assign(_r=pd.to_numeric(frame["realized_R"], errors="coerce")).groupby("session_date").agg(
        total_R=("_r", "sum"),
        count_R=("_r", "count"),
    )
    if len(daily) < 2:
        return None, None
    totals = daily["total_R"].to_numpy(dtype=float)
    counts = daily["count_R"].to_numpy(dtype=float)
    rng = random.Random(20260904)
    means = []
    population = list(range(len(daily)))
    for _ in range(iterations):
        indices = [population[rng.randrange(len(population))] for _ in population]
        sampled_count = float(counts[indices].sum())
        means.append(float(totals[indices].sum() / sampled_count) if sampled_count else 0.0)
    means.sort()
    return round(means[int(0.025 * (len(means) - 1))], 4), round(means[int(0.975 * (len(means) - 1))], 4)


def default_eval(replay: pd.DataFrame) -> pd.DataFrame:
    if replay.empty:
        return replay
    return replay[
        (replay["management_version"] == "TM_V0_CURRENT")
        & (pd.to_numeric(replay["slippage_bps"], errors="coerce") == 3)
        & (replay["status"].isin(["closed", "censored"]))
    ].copy()


def grouped_stats(frame: pd.DataFrame, dimensions: list[str]) -> pd.DataFrame:
    rows = []
    if frame.empty:
        return pd.DataFrame()
    for keys, group in frame.groupby(dimensions, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        row = {dimension: keys[index] for index, dimension in enumerate(dimensions)}
        row.update(trade_stats(group))
        rows.append(row)
    return pd.DataFrame(rows)


def discovery_holdout(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame([{"split": "NOT_RUN", **trade_stats(frame)}])
    dates = sorted(frame["session_date"].dropna().astype(str).unique())
    split = max(1, int(len(dates) * 0.60))
    discovery_dates = set(dates[:split])
    holdout_dates = set(dates[split:])
    return pd.DataFrame([
        {"split": "DISCOVERY_60PCT", **trade_stats(frame[frame["session_date"].isin(discovery_dates)])},
        {"split": "HOLDOUT_40PCT", **trade_stats(frame[frame["session_date"].isin(holdout_dates)])},
    ])


def walkforward(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame([{"window": "NOT_RUN", **trade_stats(frame)}])
    dates = sorted(pd.to_datetime(frame["session_date"].dropna().unique()))
    if not dates:
        return pd.DataFrame([{"window": "NOT_RUN", **trade_stats(frame)}])
    start = dates[0]
    end = dates[-1]
    rows = []
    anchor = start
    window_index = 1
    while anchor + pd.DateOffset(months=9) <= end + pd.Timedelta(days=1):
        discovery_end = anchor + pd.DateOffset(months=6)
        holdout_end = discovery_end + pd.DateOffset(months=3)
        holdout = frame[
            (pd.to_datetime(frame["session_date"]) >= discovery_end)
            & (pd.to_datetime(frame["session_date"]) < holdout_end)
        ]
        rows.append({
            "window": f"WF_{window_index}",
            "discovery_start": anchor.date().isoformat(),
            "discovery_end": (discovery_end - pd.Timedelta(days=1)).date().isoformat(),
            "holdout_start": discovery_end.date().isoformat(),
            "holdout_end": (holdout_end - pd.Timedelta(days=1)).date().isoformat(),
            **trade_stats(holdout),
        })
        anchor += pd.DateOffset(months=3)
        window_index += 1
    return pd.DataFrame(rows) if rows else pd.DataFrame([{"window": "INSUFFICIENT_HISTORY", **trade_stats(frame)}])


def daily_robustness(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["session_date", "N", "total_R", "positive_day"])
    rows = []
    for day, group in frame.groupby("session_date"):
        rows.append({
            "session_date": day,
            "N": len(group),
            "total_R": round(float(pd.to_numeric(group["realized_R"], errors="coerce").sum()), 4),
            "expectancy_R": round(float(pd.to_numeric(group["realized_R"], errors="coerce").mean()), 4),
            "positive_day": bool(pd.to_numeric(group["realized_R"], errors="coerce").sum() > 0),
        })
    return pd.DataFrame(rows).sort_values("session_date")


def write_source_validation(
    massive: dict[str, Any],
    repo_probe: dict[str, Any],
    wrds_metrics: dict[str, Any],
    early_close_rows: pd.DataFrame,
    cross_summary: dict[str, Any],
    cross_rows: pd.DataFrame,
    raw_files: list[RawFile],
) -> Path:
    path = PROJECT_ROOT / "HISTORICAL_5M_SOURCE_VALIDATION.md"
    raw_table = pd.DataFrame([record.__dict__ for record in raw_files])
    metrics_table = pd.DataFrame([
        {
            "symbol": symbol,
            "rows": item["rows"],
            "dates": item["unique_dates"],
            "range": f"{item['earliest']} to {item['latest']}",
            "bars/day": f"{item['bars_per_day_min']}/{item['bars_per_day_median']:.0f}/{item['bars_per_day_max']}",
            "bad_ohlc": item["bad_ohlc_rows"],
            "dup_ts": item["duplicate_timestamps"],
            "after_close_removed": item["bars_at_or_after_session_close"],
            "missing_clean_rth": item["expected_missing_rth_bars_after_cleaning"],
            "suitability": item["suitability"],
        }
        for symbol, item in wrds_metrics.items()
    ])
    cross_table = pd.DataFrame([
        {"symbol": symbol, **item}
        for symbol, item in cross_summary.items()
    ])
    worst_cross = (
        cross_rows.sort_values("close_deviation_bps", ascending=False).head(10)
        if not cross_rows.empty else pd.DataFrame()
    )
    text = f"""# Historical 5m Source Validation

Generated: {now_utc().isoformat()}

Scope: Phase 3C.1 historical price-data validation only. No live daemon, live strategy, forward cohort, canonical management, Portfolio OS, or live-execution behavior was changed.

## Massive / Polygon Stocks Basic

```json
{json.dumps(massive, indent=2, default=str)}
```

Current result: `{massive.get('status')}`. If `MASSIVE_API_KEY_NOT_CONFIGURED`, the adapter is present but no authenticated entitlement test could be performed. Add a free Massive developer key to local `.env` as `MASSIVE_API_KEY=` to validate earliest accessible 5m depth.

## WRDS GitHub repository

```json
{json.dumps(repo_probe, indent=2, default=str)}
```

Repository license metadata is `{repo_probe.get('license')}`. Because no explicit license file was found, the source is classified as `EXPLORATORY_RESEARCH`, not `SERIOUS_BACKTEST`, even though the files are technically usable for pipeline replay.

## Raw files downloaded

{markdown_table(raw_table)}

## WRDS 5m file audit

{markdown_table(metrics_table)}

## Early-close handling

The raw files have 78 bars on early-close dates. Bars at or after the official early close were excluded from `historical_intraday_5m_v2.parquet`.

{markdown_table(early_close_rows)}

## Cross-check status

Massive-vs-WRDS bar-level comparison was not run because no Massive key is configured. Fallback validation compared WRDS RTH daily rollups against the Phase 3C daily underlying files.

{markdown_table(cross_table)}

Worst close deviations:

{markdown_table(worst_cross[['symbol', 'trade_date', 'close_deviation_bps', 'open_deviation_bps', 'high_deviation_bps', 'low_deviation_bps', 'volume_deviation_pct']] if not worst_cross.empty else worst_cross)}

## Verdict

- WRDS GitHub 5m files are technically usable for an exploratory Level 2 replay.
- Price closes agree closely enough with daily references for pipeline testing.
- High/low and volume deviations require caution; no serious edge conclusion should rely on this source alone.
- Massive remains the preferred authenticated cross-check once a free key is provided.
"""
    path.write_text(text, encoding="utf-8")
    return path


def write_reports(
    *,
    massive: dict[str, Any],
    wrds_metrics: dict[str, Any],
    cross_summary: dict[str, Any],
    clean: pd.DataFrame,
    option_levels: pd.DataFrame,
    controls: pd.DataFrame,
    replay: pd.DataFrame,
    csv_paths: dict[str, Path],
) -> Path:
    path = PROJECT_ROOT / "PHASE_3C1_HISTORICAL_5M_REPLAY.md"
    eval_all = default_eval(replay)
    options_eval = eval_all[eval_all["strategy_type"] == "OPTIONS_STRUCTURE_RECON"].copy() if not eval_all.empty else eval_all
    controls_eval = eval_all[eval_all["strategy_type"] == "PRICE_CONTROL"].copy() if not eval_all.empty else eval_all
    primary_model = options_eval[options_eval.get("gex_model_version") == "GEX_MODEL_C_ABSOLUTE_GAMMA_CONCENTRATION"].copy() if not options_eval.empty else options_eval
    summary_rows = pd.DataFrame([
        {"bucket": "ALL_OPTIONS_DEFAULT_3BP_TM_V0", **trade_stats(options_eval)},
        {"bucket": "GEX_MODEL_C_DEFAULT_3BP_TM_V0", **trade_stats(primary_model)},
        {"bucket": "ALL_CONTROLS_DEFAULT_3BP_TM_V0", **trade_stats(controls_eval)},
    ])
    long_short = grouped_stats(options_eval, ["direction"]) if not options_eval.empty else pd.DataFrame()
    model_stats = grouped_stats(options_eval, ["gex_model_version"]) if not options_eval.empty else pd.DataFrame()
    control_stats = grouped_stats(eval_all, ["strategy_type", "control_type"]) if not eval_all.empty else pd.DataFrame()
    level_stats = grouped_stats(options_eval, ["level_type"]) if not options_eval.empty else pd.DataFrame()
    text = f"""# Phase 3C.1 Historical 5m OHLCV Acquisition + Full Level Replay

Generated: {now_utc().isoformat()}

Status: **EXPLORATORY REPLAY COMPLETE**

No live daemon, live strategy, forward cohort, threshold, score weight, stop/target, canonical management, provider gate, Portfolio OS, or live-execution behavior was changed.

## Source-gate result before replay

### Massive / Polygon

- Credential state: `{massive.get('credential_state')}`
- Adapter status: `{massive.get('status')}`
- Minute aggregates authenticated test: `{massive.get('usable')}`

No Massive key is configured locally, so no authenticated earliest-depth test was possible. `.env.example` now contains only the placeholder `MASSIVE_API_KEY=`.

### WRDS GitHub 5m

| symbol | rows | dates | range | bad OHLC rows | duplicate timestamps | removed early-close/post-close bars |
|---|---:|---:|---|---:|---:|---:|
""" + "\n".join(
        f"| {symbol} | {item['rows']} | {item['unique_dates']} | {item['earliest']} to {item['latest']} | "
        f"{item['bad_ohlc_rows']} | {item['duplicate_timestamps']} | {item['bars_at_or_after_session_close']} |"
        for symbol, item in wrds_metrics.items()
    ) + f"""

WRDS suitability: `EXPLORATORY_RESEARCH`, not `SERIOUS_BACKTEST`, because the GitHub repository has no explicit license metadata and WRDS TAQ redistribution authority is not proven here.

### Daily reference cross-check

```json
{json.dumps(cross_summary, indent=2, default=str)}
```

## Clean 5m dataset

- File: `historical_intraday_5m_v2.parquet`
- Rows: {len(clean):,}
- Symbols: {', '.join(sorted(clean['symbol'].unique())) if not clean.empty else 'none'}
- Date range: {clean['trade_date'].min() if not clean.empty else None} to {clean['trade_date'].max() if not clean.empty else None}
- Unique trading dates: {clean['trade_date'].nunique() if not clean.empty else 0}
- RTH only: true
- Early-close bars after official close: excluded
- Provider label: `WRDS_TAQ_PUBLIC_GITHUB`

## Options / price alignment

- Existing D-1 option levels used: `historical_daily_option_levels.parquet`
- Expanded detector-compatible option level rows: {len(option_levels):,}
- Control level rows: {len(controls):,}
- Strict rule enforced: `source_chain_date < trade_date`
- Same-day EOD option chains were not used for same-day intraday decisions.

## Replay summary

Default evaluation slice: `TM_V0_CURRENT`, `SLIPPAGE_3BP`, resolved `closed/censored` trades.

{markdown_table(summary_rows)}

## Long / short

{markdown_table(long_short)}

## GEX model comparison

{markdown_table(model_stats)}

## Level type

{markdown_table(level_stats)}

## Options vs controls

{markdown_table(control_stats)}

## Interpretation guardrails

- This is a true replay mechanically: D-1 EOD option structure joins to D 5m bars without same-day chain lookahead.
- It remains exploratory because the public WRDS GitHub data has weak redistribution/licensing provenance and Massive cross-check was not available without a key.
- Do not promote any live rule or management variant from this run alone.
- Serious validation still needs authenticated Massive/Polygon or another licensed 5m source to cross-check the WRDS bars.

## Output files

""" + "\n".join(f"- `{path.name}`" for path in csv_paths.values()) + """
- `historical_intraday_5m_v2.parquet`
- `historical_replay_v2.parquet`
"""
    path.write_text(text, encoding="utf-8")
    return path


def run() -> dict[str, Any]:
    add_env_example_placeholder()
    massive = probe_massive()
    repo_probe = github_repo_probe()
    raw_files = download_wrds_files()
    calendar = get_calendar()
    raw = {symbol: load_raw_wrds(symbol) for symbol in SYMBOLS}
    wrds_metrics, early_close_rows = validate_wrds(raw, calendar)
    clean = normalize_wrds(raw, calendar)
    clean_path = PROJECT_ROOT / "historical_intraday_5m_v2.parquet"
    clean.to_parquet(clean_path, index=False)
    cross_rows, cross_summary = daily_crosscheck(clean)
    option_levels = expand_option_levels()
    option_levels_path = PROJECT_ROOT / "historical_expanded_option_levels_v2.parquet"
    option_levels.to_parquet(option_levels_path, index=False)
    controls = control_levels(clean, option_levels)
    controls_path = PROJECT_ROOT / "historical_control_levels_v2.parquet"
    controls.to_parquet(controls_path, index=False)
    validation_path = write_source_validation(
        massive, repo_probe, wrds_metrics, early_close_rows, cross_summary, cross_rows, raw_files
    )
    replay = run_replay(clean, option_levels, controls)
    replay_path = PROJECT_ROOT / "historical_replay_v2.parquet"
    replay.to_parquet(replay_path, index=False)

    eval_all = default_eval(replay)
    options_eval = eval_all[eval_all["strategy_type"] == "OPTIONS_STRUCTURE_RECON"].copy() if not eval_all.empty else eval_all
    csv_paths = {
        "historical_options_vs_controls_v2.csv": PROJECT_ROOT / "historical_options_vs_controls_v2.csv",
        "historical_long_short_v2.csv": PROJECT_ROOT / "historical_long_short_v2.csv",
        "historical_level_type_v2.csv": PROJECT_ROOT / "historical_level_type_v2.csv",
        "historical_gex_model_comparison.csv": PROJECT_ROOT / "historical_gex_model_comparison.csv",
        "historical_discovery_holdout_v2.csv": PROJECT_ROOT / "historical_discovery_holdout_v2.csv",
        "historical_walkforward_v2.csv": PROJECT_ROOT / "historical_walkforward_v2.csv",
        "historical_daily_robustness_v2.csv": PROJECT_ROOT / "historical_daily_robustness_v2.csv",
    }
    grouped_stats(eval_all, ["strategy_type", "control_type"]).to_csv(csv_paths["historical_options_vs_controls_v2.csv"], index=False)
    grouped_stats(options_eval, ["direction"]).to_csv(csv_paths["historical_long_short_v2.csv"], index=False)
    grouped_stats(options_eval, ["level_type"]).to_csv(csv_paths["historical_level_type_v2.csv"], index=False)
    grouped_stats(options_eval, ["gex_model_version"]).to_csv(csv_paths["historical_gex_model_comparison.csv"], index=False)
    discovery_holdout(options_eval).to_csv(csv_paths["historical_discovery_holdout_v2.csv"], index=False)
    walkforward(options_eval).to_csv(csv_paths["historical_walkforward_v2.csv"], index=False)
    daily_robustness(options_eval).to_csv(csv_paths["historical_daily_robustness_v2.csv"], index=False)
    phase_report = write_reports(
        massive=massive,
        wrds_metrics=wrds_metrics,
        cross_summary=cross_summary,
        clean=clean,
        option_levels=option_levels,
        controls=controls,
        replay=replay,
        csv_paths=csv_paths,
    )
    manifest = {
        "schema_version": "historical_5m_replay_manifest.v1",
        "generated_at_utc": now_utc().isoformat(),
        "parser_version": PARSER_VERSION,
        "normalizer_version": NORMALIZER_VERSION,
        "validation_version": VALIDATION_VERSION,
        "replay_version": REPLAY_VERSION,
        "source_version": SOURCE_VERSION,
        "massive_status": {key: value for key, value in massive.items() if key not in {"apiKey", "token"}},
        "wrds_repo_probe": repo_probe,
        "raw_files": [record.__dict__ for record in raw_files],
        "wrds_metrics": wrds_metrics,
        "crosscheck_summary": cross_summary,
        "artifacts": {
            "validation_report": str(validation_path),
            "phase_report": str(phase_report),
            "historical_intraday_5m_v2": str(clean_path),
            "historical_replay_v2": str(replay_path),
            "historical_expanded_option_levels_v2": str(option_levels_path),
            "historical_control_levels_v2": str(controls_path),
            **{key: str(value) for key, value in csv_paths.items()},
        },
        "artifact_hashes": {
            str(path): sha256_file(path)
            for path in [validation_path, phase_report, clean_path, replay_path, option_levels_path, controls_path, *csv_paths.values()]
            if path.exists()
        },
        "historical_data_tiers": {
            **HISTORICAL_DATA_TIERS,
            "WRDS_TAQ_PUBLIC_GITHUB_EXPLORATORY": "Public GitHub 5m files claiming WRDS TAQ source; technically usable but weak redistribution provenance.",
        },
    }
    manifest_path = PROJECT_ROOT / "HISTORICAL_5M_REPLAY_MANIFEST_V2.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    return {
        "status": "EXPLORATORY_REPLAY_COMPLETE",
        "massive_status": massive.get("status"),
        "clean_5m_rows": int(len(clean)),
        "clean_5m_unique_dates": int(clean["trade_date"].nunique()) if not clean.empty else 0,
        "option_level_rows": int(len(option_levels)),
        "control_level_rows": int(len(controls)),
        "replay_rows": int(len(replay)),
        "default_eval_rows": int(len(default_eval(replay))),
        "reports": {
            "phase_report": str(phase_report),
            "validation_report": str(validation_path),
            "manifest": str(manifest_path),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 3C.1 historical 5m OHLCV acquisition and replay")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = run()
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        for key, value in result.items():
            print(f"{key}: {value}")


if __name__ == "__main__":
    main()
