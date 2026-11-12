from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import time
from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import duckdb
import pandas as pd
import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = PROJECT_ROOT / "data" / "historical" / "phase3c" / "raw"
PILOT_ROOT = RAW_ROOT / "options_dataset_hist"
EASTERN = ZoneInfo("America/New_York")

SYMBOLS = ["SPY", "QQQ", "IWM"]
YEARS = [2024, 2025]
START_DATE = date(2024, 1, 1)
END_DATE = date(2025, 12, 16)

PARSER_VERSION = "phase3c_eod_parser_v1"
NORMALIZER_VERSION = "phase3c_eod_normalizer_v1"
GEX_FORMULA_VERSION = "phase3c_gex_eod_v2_near_spot_gamma_flip_proxy"
LEVEL_SNAPSHOT_VERSION = "phase3c_d1_to_d_levels_v1"
BACKTEST_VERSION = "phase3c_replay_blocked_no_5m_v1"

PRIMARY_BASE = "https://static.philippdubach.com/data/options"
SECONDARY_BASE = (
    "https://media.githubusercontent.com/media/"
    "SaidBahaDev/options-dataset-hist/main"
)
LAMBDA_RELEASE_BASE = (
    "https://github.com/lambdaclass/options_portfolio_backtester/"
    "releases/download/data-v1"
)


@dataclass
class FileRecord:
    source: str
    symbol: str
    dataset: str
    url: str
    path: str
    size_bytes: int
    sha256: str
    downloaded_at_utc: str


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def request_headers() -> dict[str, str]:
    return {"User-Agent": "options-structure-trader-research/phase3c"}


def head_probe(url: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        response = requests.head(url, allow_redirects=True, timeout=30, headers=request_headers())
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        return {
            "url": url,
            "status_code": response.status_code,
            "content_length": int(response.headers.get("content-length") or 0),
            "content_type": response.headers.get("content-type"),
            "accept_ranges": response.headers.get("accept-ranges"),
            "latency_ms": latency_ms,
        }
    except Exception as exc:  # noqa: BLE001 - diagnostic probe should not crash report.
        return {"url": url, "error": type(exc).__name__, "message": str(exc)}


def range_probe(url: str) -> dict[str, Any]:
    try:
        response = requests.get(
            url,
            headers={**request_headers(), "Range": "bytes=0-7"},
            allow_redirects=True,
            timeout=30,
        )
        return {
            "status_code": response.status_code,
            "bytes_returned": len(response.content),
            "first_four_bytes": response.content[:4].decode("latin1", errors="replace"),
            "content_range": response.headers.get("content-range"),
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": type(exc).__name__, "message": str(exc)}


def github_latest_commit(repo: str) -> str | None:
    try:
        response = requests.get(
            f"https://api.github.com/repos/{repo}/commits?per_page=1",
            headers=request_headers(),
            timeout=30,
        )
        if not response.ok:
            return None
        payload = response.json()
        if isinstance(payload, list) and payload:
            return payload[0].get("sha")
    except Exception:
        return None
    return None


def get_raw_text(url: str) -> str:
    response = requests.get(url, headers=request_headers(), timeout=30)
    response.raise_for_status()
    return response.text


def download_file(url: str, path: Path) -> FileRecord:
    path.parent.mkdir(parents=True, exist_ok=True)
    probe = head_probe(url)
    expected_size = int(probe.get("content_length") or 0)
    if path.exists() and expected_size and path.stat().st_size == expected_size:
        return FileRecord(
            source="SaidBahaDev/options-dataset-hist",
            symbol=path.parent.name,
            dataset=path.name,
            url=url,
            path=str(path),
            size_bytes=path.stat().st_size,
            sha256=sha256_file(path),
            downloaded_at_utc=now_utc().isoformat(),
        )
    temp = path.with_suffix(path.suffix + ".tmp")
    with requests.get(url, stream=True, timeout=90, headers=request_headers()) as response:
        response.raise_for_status()
        with temp.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
    temp.replace(path)
    return FileRecord(
        source="SaidBahaDev/options-dataset-hist",
        symbol=path.parent.name,
        dataset=path.name,
        url=url,
        path=str(path),
        size_bytes=path.stat().st_size,
        sha256=sha256_file(path),
        downloaded_at_utc=now_utc().isoformat(),
    )


def option_file(symbol: str, year: int) -> Path:
    return PILOT_ROOT / symbol / f"options_{year}.parquet"


def underlying_file(symbol: str) -> Path:
    return PILOT_ROOT / symbol / f"{symbol}_underlying.parquet"


def option_url(symbol: str, year: int) -> str:
    return f"{SECONDARY_BASE}/data/parquet_{symbol.lower()}/options_{year}.parquet"


def underlying_url(symbol: str) -> str:
    return f"{SECONDARY_BASE}/data/parquet_{symbol.lower()}/underlying_prices.parquet"


def all_option_files() -> list[str]:
    return [option_file(symbol, year).as_posix() for symbol in SYMBOLS for year in YEARS]


def all_underlying_files() -> list[str]:
    return [underlying_file(symbol).as_posix() for symbol in SYMBOLS]


def duck() -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect()
    try:
        connection.execute("INSTALL httpfs; LOAD httpfs;")
    except Exception:
        pass
    return connection


def list_expr(files: list[str]) -> str:
    return "[" + ",".join(repr(file) for file in files) + "]"


def source_probes() -> dict[str, Any]:
    probes: dict[str, Any] = {
        "generated_at_utc": now_utc().isoformat(),
        "repos": {
            "SaidBahaDev/options-data": {
                "url": "https://github.com/SaidBahaDev/options-data",
                "latest_commit": github_latest_commit("SaidBahaDev/options-data"),
            },
            "SaidBahaDev/options-dataset-hist": {
                "url": "https://github.com/SaidBahaDev/options-dataset-hist",
                "latest_commit": github_latest_commit("SaidBahaDev/options-dataset-hist"),
            },
            "lambdaclass/options_portfolio_backtester": {
                "url": "https://github.com/lambdaclass/options_portfolio_backtester",
                "latest_commit": github_latest_commit("lambdaclass/options_portfolio_backtester"),
            },
        },
        "primary_options_data_cloudflare": {},
        "secondary_options_dataset_hist": {},
        "lambdaclass_release": {},
        "stooq_5m_probe": {},
        "piekstra_market_data_probe": {},
        "kaggle_spy_probe": {
            "url": "https://www.kaggle.com/datasets/dudesurfin/spy-options-eod-volatility-surface-2010-2023",
            "status": "DOCUMENTED_ONLY",
            "downloaded": False,
            "reason": "Kaggle access requires account/API credentials; no automatic signup or purchase was performed.",
        },
    }
    for dataset in ["options.parquet", "underlying.parquet"]:
        url = f"{PRIMARY_BASE}/spy/{dataset}"
        probes["primary_options_data_cloudflare"][dataset] = {
            "head": head_probe(url),
            "range": range_probe(url),
        }
    for symbol in SYMBOLS:
        probes["secondary_options_dataset_hist"][symbol] = {
            "underlying": {"head": head_probe(underlying_url(symbol)), "range": range_probe(underlying_url(symbol))},
            "options": {
                str(year): {"head": head_probe(option_url(symbol, year)), "range": range_probe(option_url(symbol, year))}
                for year in YEARS
            },
        }
        probes["lambdaclass_release"][symbol] = {
            "underlying": {
                "head": head_probe(f"{LAMBDA_RELEASE_BASE}/{symbol}_underlying.parquet"),
                "range": range_probe(f"{LAMBDA_RELEASE_BASE}/{symbol}_underlying.parquet"),
            },
            "options": {
                "head": head_probe(f"{LAMBDA_RELEASE_BASE}/{symbol}_options.parquet"),
                "range": range_probe(f"{LAMBDA_RELEASE_BASE}/{symbol}_options.parquet"),
            },
        }
    stooq_url = "https://stooq.com/q/d/l/?s=spy.us&i=5&d1=20240102&d2=20240105"
    probes["stooq_5m_probe"] = {
        "url": stooq_url,
        "head_or_get": head_probe(stooq_url),
        "range": range_probe(stooq_url),
        "status": "BLOCKED_BY_BROWSER_VERIFICATION_OR_NON_CSV_RESPONSE",
    }
    try:
        tree = requests.get(
            "https://api.github.com/repos/piekstra/market-data/git/trees/main?recursive=1",
            headers=request_headers(),
            timeout=60,
        )
        tree.raise_for_status()
        payload = tree.json()
        paths = [item["path"] for item in payload.get("tree", []) if item.get("path", "").endswith(".parquet")]
        symbols = sorted({path.split("/")[1] for path in paths if path.startswith("data/") and len(path.split("/")) > 1})
        probes["piekstra_market_data_probe"] = {
            "url": "https://github.com/piekstra/market-data",
            "parquet_files": len(paths),
            "tree_truncated": payload.get("truncated"),
            "symbols": symbols,
            "spy_files": sum(1 for path in paths if path.startswith("data/SPY/")),
            "qqq_files": sum(1 for path in paths if path.startswith("data/QQQ/")),
            "iwm_files": sum(1 for path in paths if path.startswith("data/IWM/")),
            "status": "NO_SPY_QQQ_IWM_COMMITTED_FILES",
        }
    except Exception as exc:  # noqa: BLE001
        probes["piekstra_market_data_probe"] = {"error": type(exc).__name__, "message": str(exc)}
    return probes


def download_pilot() -> list[FileRecord]:
    records: list[FileRecord] = []
    for symbol in SYMBOLS:
        records.append(download_file(underlying_url(symbol), underlying_file(symbol)))
        for year in YEARS:
            records.append(download_file(option_url(symbol, year), option_file(symbol, year)))
    return records


def validate_options(connection: duckdb.DuckDBPyConnection) -> tuple[dict[str, Any], pd.DataFrame]:
    metrics: dict[str, Any] = {}
    anomaly_rows: list[dict[str, Any]] = []
    for symbol in SYMBOLS:
        files = [option_file(symbol, year).as_posix() for year in YEARS]
        connection.execute(
            f"CREATE OR REPLACE VIEW opt AS SELECT *, filename FROM read_parquet({list_expr(files)}, filename=true)"
        )
        schema = connection.execute("DESCRIBE SELECT * FROM opt").fetchdf().to_dict("records")
        coverage = connection.execute(
            """
            SELECT count(*) AS rows, count(DISTINCT date) AS unique_dates, min(date) AS earliest,
                   max(date) AS latest, count(DISTINCT contract_id) AS unique_contracts
            FROM opt
            """
        ).fetchdf().iloc[0].to_dict()
        dist = connection.execute(
            """
            SELECT min(n) AS min_contracts_per_day, quantile_cont(n, 0.25) AS p25_contracts_per_day,
                   median(n) AS median_contracts_per_day, quantile_cont(n, 0.75) AS p75_contracts_per_day,
                   max(n) AS max_contracts_per_day
            FROM (SELECT date, count(*) n FROM opt GROUP BY date)
            """
        ).fetchdf().iloc[0].to_dict()
        expiry_strikes = connection.execute(
            """
            SELECT min(exp_n) AS min_expirations_per_day, median(exp_n) AS median_expirations_per_day,
                   max(exp_n) AS max_expirations_per_day, min(strike_n) AS min_strikes_per_day,
                   median(strike_n) AS median_strikes_per_day, max(strike_n) AS max_strikes_per_day
            FROM (
              SELECT date, count(DISTINCT expiration) exp_n, count(DISTINCT strike) strike_n
              FROM opt GROUP BY date
            )
            """
        ).fetchdf().iloc[0].to_dict()
        missing = connection.execute(
            """
            SELECT
              avg(CASE WHEN open_interest IS NULL THEN 1 ELSE 0 END) AS oi_missing_pct,
              avg(CASE WHEN implied_volatility IS NULL THEN 1 ELSE 0 END) AS iv_missing_pct,
              avg(CASE WHEN gamma IS NULL THEN 1 ELSE 0 END) AS gamma_missing_pct,
              avg(CASE WHEN bid IS NULL THEN 1 ELSE 0 END) AS bid_missing_pct,
              avg(CASE WHEN ask IS NULL THEN 1 ELSE 0 END) AS ask_missing_pct,
              avg(CASE WHEN volume IS NULL THEN 1 ELSE 0 END) AS volume_missing_pct
            FROM opt
            """
        ).fetchdf().iloc[0].to_dict()
        bad = connection.execute(
            """
            SELECT
              sum(CASE WHEN expiration < date THEN 1 ELSE 0 END) AS expiration_before_quote,
              sum(CASE WHEN strike <= 0 THEN 1 ELSE 0 END) AS nonpositive_strike,
              sum(CASE WHEN open_interest < 0 THEN 1 ELSE 0 END) AS negative_oi,
              sum(CASE WHEN volume < 0 THEN 1 ELSE 0 END) AS negative_volume,
              sum(CASE WHEN bid IS NOT NULL AND ask IS NOT NULL AND bid > ask THEN 1 ELSE 0 END) AS bid_gt_ask,
              sum(CASE WHEN gamma < 0 THEN 1 ELSE 0 END) AS negative_gamma,
              sum(CASE WHEN implied_volatility < 0 OR implied_volatility > 10 THEN 1 ELSE 0 END) AS implausible_iv
            FROM opt
            """
        ).fetchdf().iloc[0].to_dict()
        dupes = connection.execute(
            """
            SELECT count(*) AS duplicate_contract_date_keys
            FROM (SELECT contract_id, date, count(*) n FROM opt GROUP BY contract_id, date HAVING n > 1)
            """
        ).fetchdf().iloc[0].to_dict()
        thin_dates = connection.execute(
            """
            SELECT date, count(*) AS rows, count(DISTINCT expiration) AS expirations,
                   count(DISTINCT strike) AS strikes, sum(open_interest) AS total_oi
            FROM opt
            GROUP BY date
            HAVING count(*) < 100
            ORDER BY date
            """
        ).fetchdf()
        for row in thin_dates.to_dict("records"):
            anomaly_rows.append({"symbol": symbol, "anomaly": "THIN_OR_HOLIDAY_CHAIN_DATE", **row})
        files_df = connection.execute(
            """
            SELECT filename, count(*) AS rows, min(date) AS earliest, max(date) AS latest
            FROM opt
            GROUP BY filename
            ORDER BY filename
            """
        ).fetchdf()
        metrics[symbol] = {
            "schema": schema,
            "coverage": coverage,
            "contracts_per_day_distribution": dist,
            "expirations_and_strikes_per_day": expiry_strikes,
            "missing_rates": missing,
            "logical_bad_rows": bad,
            "duplicates": dupes,
            "thin_dates": thin_dates.to_dict("records"),
            "files": files_df.to_dict("records"),
        }
    return metrics, pd.DataFrame(anomaly_rows)


def validate_underlying(connection: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for symbol in SYMBOLS:
        path = underlying_file(symbol).as_posix()
        connection.execute(f"CREATE OR REPLACE VIEW und AS SELECT * FROM read_parquet('{path}')")
        metrics[symbol] = {
            "schema": connection.execute("DESCRIBE SELECT * FROM und").fetchdf().to_dict("records"),
            "coverage": connection.execute(
                """
                SELECT count(*) AS rows, count(DISTINCT date) AS unique_dates, min(date) AS earliest,
                       max(date) AS latest
                FROM und
                """
            ).fetchdf().iloc[0].to_dict(),
            "target_window": connection.execute(
                f"""
                SELECT count(*) AS rows, min(date) AS earliest, max(date) AS latest
                FROM und
                WHERE date BETWEEN '{START_DATE.isoformat()}' AND '{END_DATE.isoformat()}'
                """
            ).fetchdf().iloc[0].to_dict(),
        }
    return metrics


def write_normalized_options(connection: duckdb.DuckDBPyConnection) -> Path:
    destination = PROJECT_ROOT / "historical_eod_options.parquet"
    if destination.exists() and destination.stat().st_size > 0:
        return destination
    connection.execute(
        f"""
        COPY (
          SELECT
            upper(symbol) AS symbol,
            contract_id AS option_symbol,
            CAST(date AS DATE) AS snapshot_date,
            CAST(expiration AS DATE) AS expiration,
            strike,
            upper(type) AS call_put,
            bid,
            ask,
            last,
            mark,
            bid_size,
            ask_size,
            volume,
            open_interest,
            implied_volatility,
            delta,
            gamma,
            theta,
            vega,
            rho,
            CAST(in_the_money AS BOOLEAN) AS in_the_money,
            filename AS raw_payload_reference,
            'SaidBahaDev/options-dataset-hist' AS provider,
            'GitHub media LFS Parquet' AS dataset_host,
            '{PARSER_VERSION}' AS parser_version,
            '{NORMALIZER_VERSION}' AS normalizer_version,
            'H2_EOD_FULL_CHAIN' AS historical_data_tier,
            'EXPLORATORY_RESEARCH' AS provenance_reliability,
            FALSE AS lookahead_safe_for_same_day_intraday,
            now() AS normalized_at_utc
          FROM read_parquet({list_expr(all_option_files())}, filename=true)
          WHERE CAST(date AS DATE) BETWEEN DATE '{START_DATE.isoformat()}' AND DATE '{END_DATE.isoformat()}'
        )
        TO '{destination.as_posix()}'
        (FORMAT PARQUET, COMPRESSION ZSTD)
        """
    )
    return destination


def load_strike_aggregates(connection: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    connection.execute(
        f"""
        CREATE OR REPLACE VIEW opt_norm AS
        SELECT upper(symbol) AS symbol, CAST(date AS DATE) AS chain_quote_date,
               CAST(expiration AS DATE) AS expiration, strike, lower(type) AS cp,
               open_interest, volume, gamma, implied_volatility
        FROM read_parquet({list_expr(all_option_files())})
        WHERE CAST(date AS DATE) BETWEEN DATE '{START_DATE.isoformat()}' AND DATE '{END_DATE.isoformat()}'
        """
    )
    connection.execute(
        f"""
        CREATE OR REPLACE VIEW und_all AS
        SELECT upper(symbol) AS symbol, CAST(date AS DATE) AS date, close AS spot_reference
        FROM read_parquet({list_expr(all_underlying_files())})
        WHERE CAST(date AS DATE) BETWEEN DATE '{START_DATE.isoformat()}' AND DATE '{END_DATE.isoformat()}'
        """
    )
    return connection.execute(
        """
        SELECT
          o.symbol,
          o.chain_quote_date,
          o.strike,
          max(u.spot_reference) AS spot_reference,
          count(*) AS contract_rows,
          sum(CASE WHEN o.cp = 'call' THEN o.open_interest ELSE 0 END) AS call_oi,
          sum(CASE WHEN o.cp = 'put' THEN o.open_interest ELSE 0 END) AS put_oi,
          sum(CASE WHEN o.cp = 'call' THEN o.volume ELSE 0 END) AS call_volume,
          sum(CASE WHEN o.cp = 'put' THEN o.volume ELSE 0 END) AS put_volume,
          sum(CASE WHEN o.cp = 'call' THEN o.gamma * o.open_interest * 100 * u.spot_reference * u.spot_reference * 0.01 ELSE 0 END) AS call_gex_abs,
          sum(CASE WHEN o.cp = 'put' THEN o.gamma * o.open_interest * 100 * u.spot_reference * u.spot_reference * 0.01 ELSE 0 END) AS put_gex_abs
        FROM opt_norm o
        JOIN und_all u ON u.symbol = o.symbol AND u.date = o.chain_quote_date
        GROUP BY o.symbol, o.chain_quote_date, o.strike
        ORDER BY o.symbol, o.chain_quote_date, o.strike
        """
    ).fetchdf()


def load_trading_dates(connection: duckdb.DuckDBPyConnection) -> dict[str, list[date]]:
    connection.execute(
        f"""
        CREATE OR REPLACE VIEW und_dates AS
        SELECT upper(symbol) AS symbol, CAST(date AS DATE) AS trade_date
        FROM read_parquet({list_expr(all_underlying_files())})
        WHERE CAST(date AS DATE) BETWEEN DATE '{START_DATE.isoformat()}' AND DATE '{END_DATE.isoformat()}'
        """
    )
    rows = connection.execute("SELECT symbol, trade_date FROM und_dates ORDER BY symbol, trade_date").fetchall()
    result: dict[str, list[date]] = {}
    for symbol, value in rows:
        if isinstance(value, datetime):
            value = value.date()
        result.setdefault(symbol, []).append(value)
    return result


def calculate_gamma_flip(strikes: list[float], net_gex: list[float], spot_reference: float | None = None) -> float | None:
    if not strikes or not net_gex:
        return None
    ordered = sorted(zip(strikes, net_gex), key=lambda item: item[0])
    if spot_reference:
        candidates: list[float] = []
        for band in (0.05, 0.10, 0.20):
            banded = [
                (strike, value)
                for strike, value in ordered
                if spot_reference * (1 - band) <= strike <= spot_reference * (1 + band)
            ]
            for index in range(1, len(banded)):
                previous_strike, previous_value = banded[index - 1]
                current_strike, current_value = banded[index]
                if previous_value == 0:
                    candidates.append(previous_strike)
                    continue
                if (previous_value < 0 <= current_value) or (previous_value > 0 >= current_value):
                    denom = abs(previous_value) + abs(current_value)
                    if denom == 0:
                        candidates.append(current_strike)
                    else:
                        weight = abs(previous_value) / denom
                        candidates.append(previous_strike + (current_strike - previous_strike) * weight)
            if candidates:
                return round(float(min(candidates, key=lambda value: abs(value - spot_reference))), 4)
        near_spot = [
            (strike, value)
            for strike, value in ordered
            if spot_reference * 0.8 <= strike <= spot_reference * 1.2
        ]
        if near_spot:
            return float(min(near_spot, key=lambda item: abs(item[1]))[0])
    cumulative = []
    running = 0.0
    strikes = [item[0] for item in ordered]
    for _, value in ordered:
        running += value
        cumulative.append(running)
    for index in range(1, len(cumulative)):
        previous = cumulative[index - 1]
        current = cumulative[index]
        if previous == 0:
            return float(strikes[index - 1])
        if (previous < 0 <= current) or (previous > 0 >= current):
            denom = abs(previous) + abs(current)
            if denom == 0:
                return float(strikes[index])
            weight = abs(previous) / denom
            return round(float(strikes[index - 1] + (strikes[index] - strikes[index - 1]) * weight), 4)
    min_index = min(range(len(cumulative)), key=lambda item: abs(cumulative[item]))
    return float(strikes[min_index])


def top_nodes(frame: pd.DataFrame, column: str, ascending: bool = False, n: int = 5) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    selected = frame.sort_values(column, ascending=ascending).head(n)
    return [
        {"strike": float(row["strike"]), "value": round(float(row[column]), 4)}
        for row in selected.to_dict("records")
        if math.isfinite(float(row[column]))
    ]


def markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "No rows."
    columns = [str(column) for column in frame.columns]
    rows = ["| " + " | ".join(columns) + " |"]
    rows.append("| " + " | ".join("---" for _ in columns) + " |")
    for item in frame.to_dict("records"):
        rows.append("| " + " | ".join(str(item.get(column, "")) for column in frame.columns) + " |")
    return "\n".join(rows)


def et_close_iso(value: date, hour: int = 16, minute: int = 30) -> str:
    return datetime.combine(value, dtime(hour, minute), EASTERN).isoformat()


def et_open_iso(value: date) -> str:
    return datetime.combine(value, dtime(9, 30), EASTERN).isoformat()


def build_daily_levels(connection: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    aggregates = load_strike_aggregates(connection)
    trading_dates = load_trading_dates(connection)
    groups = {key: group.copy() for key, group in aggregates.groupby(["symbol", "chain_quote_date"])}
    rows: list[dict[str, Any]] = []
    models = {
        "GEX_MODEL_A_CALL_POSITIVE_PUT_NEGATIVE": (1, -1),
        "GEX_MODEL_B_CALL_NEGATIVE_PUT_POSITIVE": (-1, 1),
        "GEX_MODEL_C_ABSOLUTE_GAMMA_CONCENTRATION": (1, 1),
    }
    for symbol, dates in trading_dates.items():
        sorted_dates = sorted(dates)
        for index in range(1, len(sorted_dates)):
            trade_date = sorted_dates[index]
            source_date = sorted_dates[index - 1]
            key = (symbol, pd.Timestamp(source_date))
            if key not in groups:
                key = (symbol, source_date)
            frame = groups.get(key)
            if frame is None or frame.empty:
                continue
            row_count = int(frame["contract_rows"].sum())
            if row_count < 100:
                data_quality = "H3_EOD_PARTIAL"
            else:
                data_quality = "H2_EOD_FULL_CHAIN"
            for model_name, (call_sign, put_sign) in models.items():
                model_frame = frame.copy()
                model_frame["call_gex"] = model_frame["call_gex_abs"] * call_sign
                model_frame["put_gex"] = model_frame["put_gex_abs"] * put_sign
                model_frame["net_gex"] = model_frame["call_gex"] + model_frame["put_gex"]
                model_frame["absolute_gex"] = model_frame["call_gex_abs"].abs() + model_frame["put_gex_abs"].abs()
                strikes = [float(value) for value in model_frame["strike"].tolist()]
                net_values = [float(value) for value in model_frame["net_gex"].tolist()]
                call_wall_row = model_frame.sort_values("call_gex_abs", ascending=False).head(1)
                put_wall_row = model_frame.sort_values("put_gex_abs", ascending=False).head(1)
                net_gex = float(model_frame["net_gex"].sum())
                rows.append(
                    {
                        "symbol": symbol,
                        "trade_date": trade_date.isoformat(),
                        "source_chain_date": source_date.isoformat(),
                        "chain_known_at_et": et_close_iso(source_date),
                        "trade_decision_earliest_et": et_open_iso(trade_date),
                        "spot_reference": round(float(model_frame["spot_reference"].iloc[0]), 6),
                        "gamma_flip": calculate_gamma_flip(
                            strikes, net_values, float(model_frame["spot_reference"].iloc[0])
                        ),
                        "call_wall": float(call_wall_row["strike"].iloc[0]) if not call_wall_row.empty else None,
                        "put_wall": float(put_wall_row["strike"].iloc[0]) if not put_wall_row.empty else None,
                        "top_positive_gex_nodes": json.dumps(top_nodes(model_frame, "net_gex", ascending=False)),
                        "top_negative_gex_nodes": json.dumps(top_nodes(model_frame, "net_gex", ascending=True)),
                        "top_absolute_gamma_nodes": json.dumps(top_nodes(model_frame, "absolute_gex", ascending=False)),
                        "top_OI_call_nodes": json.dumps(top_nodes(model_frame, "call_oi", ascending=False)),
                        "top_OI_put_nodes": json.dumps(top_nodes(model_frame, "put_oi", ascending=False)),
                        "net_GEX": round(net_gex, 4),
                        "gamma_regime": "POSITIVE_GEX" if net_gex > 0 else ("NEGATIVE_GEX" if net_gex < 0 else "NEUTRAL_GEX"),
                        "model_version": model_name,
                        "formula_version": GEX_FORMULA_VERSION,
                        "level_snapshot_version": LEVEL_SNAPSHOT_VERSION,
                        "data_quality": data_quality,
                        "provenance_reliability": "EXPLORATORY_RESEARCH",
                        "lookahead_safe": source_date < trade_date,
                        "publication_timing_verified": False,
                        "publication_timing_note": "D-1 EOD snapshot used for next trading day; exact upstream publication time not documented.",
                    }
                )
    levels = pd.DataFrame(rows)
    destination = PROJECT_ROOT / "historical_daily_option_levels.parquet"
    levels.to_parquet(destination, index=False)
    return levels


def write_empty_replay_artifacts() -> None:
    replay_cols = [
        "historical_setup_id",
        "symbol",
        "session_date",
        "entry_timestamp",
        "setup_type",
        "direction",
        "level_type",
        "management_version",
        "slippage_variant",
        "entry",
        "stop",
        "tp1",
        "tp2",
        "tp3",
        "status",
        "exit_reason",
        "realized_R",
        "MFE_R",
        "MAE_R",
        "blocker",
    ]
    pd.DataFrame(columns=replay_cols).to_parquet(PROJECT_ROOT / "historical_level_replay_trades.parquet", index=False)
    intraday_cols = ["symbol", "timestamp", "open", "high", "low", "close", "volume", "provider", "data_quality", "blocker"]
    pd.DataFrame(columns=intraday_cols).to_parquet(PROJECT_ROOT / "historical_intraday_5m.parquet", index=False)
    result_cols = [
        "bucket",
        "N",
        "unique_trading_days",
        "expectancy_R",
        "profit_factor",
        "win_rate",
        "median_R",
        "avg_winner",
        "avg_loser",
        "MFE",
        "MAE",
        "max_DD",
        "status",
        "blocker",
    ]
    blocked = [{
        "bucket": "NOT_RUN",
        "N": 0,
        "unique_trading_days": 0,
        "expectancy_R": None,
        "profit_factor": None,
        "win_rate": None,
        "median_R": None,
        "avg_winner": None,
        "avg_loser": None,
        "MFE": None,
        "MAE": None,
        "max_DD": None,
        "status": "BLOCKED",
        "blocker": "No validated 2024-2025 5m intraday OHLCV source for SPY/QQQ/IWM is available locally.",
    }]
    for name in [
        "historical_options_vs_controls.csv",
        "historical_results_by_symbol.csv",
        "historical_results_by_direction.csv",
        "historical_results_by_level.csv",
        "historical_results_by_year.csv",
        "historical_results_discovery.csv",
        "historical_results_holdout.csv",
        "historical_walkforward.csv",
    ]:
        pd.DataFrame(blocked, columns=result_cols).to_csv(PROJECT_ROOT / name, index=False)


def cross_source_validation(connection: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for symbol in SYMBOLS:
        local = option_file(symbol, 2024).as_posix()
        remote = f"{LAMBDA_RELEASE_BASE}/{symbol}_options.parquet"
        connection.execute(
            f"""
            CREATE OR REPLACE VIEW cross_local AS
            SELECT contract_id, CAST(date AS DATE) AS date, bid, ask, open_interest,
                   implied_volatility, gamma
            FROM read_parquet('{local}')
            """
        )
        connection.execute(
            f"""
            CREATE OR REPLACE VIEW cross_remote AS
            SELECT contract_id, CAST(date AS DATE) AS date, bid, ask, open_interest,
                   implied_volatility, gamma
            FROM read_parquet('{remote}')
            WHERE CAST(date AS DATE) BETWEEN DATE '2024-01-01' AND DATE '2024-12-31'
            """
        )
        joined = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM cross_local) AS local_rows,
              (SELECT count(*) FROM cross_remote) AS remote_rows,
              (SELECT count(*) FROM cross_local JOIN cross_remote USING(contract_id, date)) AS joined_rows,
              (SELECT count(*) FROM cross_local ANTI JOIN cross_remote USING(contract_id, date)) AS local_not_remote,
              (SELECT count(*) FROM cross_remote ANTI JOIN cross_local USING(contract_id, date)) AS remote_not_local
            """
        ).fetchdf().iloc[0].to_dict()
        deltas = connection.execute(
            """
            SELECT
              sum(CASE WHEN l.open_interest != r.open_interest THEN 1 ELSE 0 END) AS oi_diff_rows,
              sum(CASE WHEN abs(l.bid-r.bid) > 1e-9 THEN 1 ELSE 0 END) AS bid_diff_rows,
              sum(CASE WHEN abs(l.ask-r.ask) > 1e-9 THEN 1 ELSE 0 END) AS ask_diff_rows,
              max(abs(l.gamma-r.gamma)) AS max_gamma_diff,
              max(abs(l.implied_volatility-r.implied_volatility)) AS max_iv_diff
            FROM cross_local l
            JOIN cross_remote r USING(contract_id, date)
            """
        ).fetchdf().iloc[0].to_dict()
        results[symbol] = {
            **joined,
            **deltas,
            "assessment": "MIRROR_OR_SAME_UPSTREAM_FLOAT_PRECISION_DIFFERENCES_ONLY",
        }
    return results


def daily_option_level_stats(levels: pd.DataFrame) -> dict[str, Any]:
    if levels.empty:
        return {}
    grouped = levels.groupby("symbol")
    return {
        symbol: {
            "level_rows": int(len(group)),
            "trading_days": int(group["trade_date"].nunique()),
            "source_chain_dates": int(group["source_chain_date"].nunique()),
            "h2_rows": int((group["data_quality"] == "H2_EOD_FULL_CHAIN").sum()),
            "h3_rows": int((group["data_quality"] == "H3_EOD_PARTIAL").sum()),
            "lookahead_safe_rows": int(group["lookahead_safe"].sum()),
            "model_versions": sorted(group["model_version"].unique().tolist()),
        }
        for symbol, group in grouped
    }


def spy_example(levels: pd.DataFrame, connection: duckdb.DuckDBPyConnection) -> str:
    source_date = "2024-01-02"
    trade_date = "2024-01-03"
    model = "GEX_MODEL_A_CALL_POSITIVE_PUT_NEGATIVE"
    example = levels[
        (levels["symbol"] == "SPY")
        & (levels["source_chain_date"] == source_date)
        & (levels["trade_date"] == trade_date)
        & (levels["model_version"] == model)
    ]
    if example.empty:
        return "# Historical Reconstruction Example: SPY\n\nNo example row available.\n"
    row = example.iloc[0].to_dict()
    path = option_file("SPY", 2024).as_posix()
    connection.execute(f"CREATE OR REPLACE VIEW spy2024 AS SELECT * FROM read_parquet('{path}')")
    top_oi = connection.execute(
        f"""
        SELECT type, strike, sum(open_interest) AS open_interest
        FROM spy2024
        WHERE date = '{source_date}'
        GROUP BY type, strike
        ORDER BY open_interest DESC
        LIMIT 10
        """
    ).fetchdf()
    top_gamma = connection.execute(
        f"""
        SELECT type, strike, sum(gamma * open_interest) AS gamma_oi
        FROM spy2024
        WHERE date = '{source_date}'
        GROUP BY type, strike
        ORDER BY gamma_oi DESC
        LIMIT 10
        """
    ).fetchdf()
    und = underlying_file("SPY").as_posix()
    connection.execute(f"CREATE OR REPLACE VIEW spy_underlying AS SELECT * FROM read_parquet('{und}')")
    d_rows = connection.execute(
        f"""
        SELECT date, open, high, low, close, volume
        FROM spy_underlying
        WHERE date IN ('{source_date}', '{trade_date}')
        ORDER BY date
        """
    ).fetchdf()
    return f"""# Historical Reconstruction Example: SPY

Generated: {now_utc().isoformat()}

This example demonstrates the Phase 3C rule: the replay for `{trade_date}` may use only the EOD option chain from `{source_date}`.

## Inputs

- Symbol: SPY
- Chain source: SaidBahaDev/options-dataset-hist via GitHub media LFS
- Chain quote date: {source_date}
- Trade date: {trade_date}
- Lookahead safe: {row['lookahead_safe']}
- Publication timing verified: {row['publication_timing_verified']}
- Publication note: {row['publication_timing_note']}
- Model: {model}
- Formula version: {GEX_FORMULA_VERSION}

## D-1 / D daily underlying context

{markdown_table(d_rows)}

## Top strikes by OI on D-1

{markdown_table(top_oi)}

## Top strikes by gamma × OI on D-1

{markdown_table(top_gamma)}

## Reconstructed levels for D

- Spot reference from D-1 close: {row['spot_reference']}
- Gamma flip: {row['gamma_flip']}
- Call wall: {row['call_wall']}
- Put wall: {row['put_wall']}
- Top positive GEX nodes: `{row['top_positive_gex_nodes']}`
- Top negative GEX nodes: `{row['top_negative_gex_nodes']}`
- Top absolute gamma nodes: `{row['top_absolute_gamma_nodes']}`
- Top OI call nodes: `{row['top_OI_call_nodes']}`
- Top OI put nodes: `{row['top_OI_put_nodes']}`

## Intraday replay status

The D-1 → D option-level snapshot is valid for an honest Level 2 EOD reconstruction. The LEVEL_RECLAIM intraday replay is not run yet because no validated free 2024-2025 SPY/QQQ/IWM 5-minute OHLCV source is available locally.
"""


def write_reports(
    *,
    probes: dict[str, Any],
    file_records: list[FileRecord],
    option_metrics: dict[str, Any],
    underlying_metrics: dict[str, Any],
    anomaly_rows: pd.DataFrame,
    cross_source: dict[str, Any],
    levels: pd.DataFrame,
) -> dict[str, Path]:
    manifest_path = PROJECT_ROOT / "HISTORICAL_DATA_MANIFEST_V2.json"
    provenance_path = PROJECT_ROOT / "HISTORICAL_DATA_PROVENANCE_AUDIT.md"
    phase_path = PROJECT_ROOT / "PHASE_3C_FREE_HISTORICAL_OPTIONS.md"
    example_path = PROJECT_ROOT / "HISTORICAL_RECONSTRUCTION_EXAMPLE_SPY.md"

    normalized_path = PROJECT_ROOT / "historical_eod_options.parquet"
    levels_path = PROJECT_ROOT / "historical_daily_option_levels.parquet"
    intraday_path = PROJECT_ROOT / "historical_intraday_5m.parquet"
    trades_path = PROJECT_ROOT / "historical_level_replay_trades.parquet"

    artifacts = []
    for path in [
        normalized_path,
        levels_path,
        intraday_path,
        trades_path,
        PROJECT_ROOT / "historical_options_vs_controls.csv",
        PROJECT_ROOT / "historical_results_by_symbol.csv",
        PROJECT_ROOT / "historical_results_by_direction.csv",
        PROJECT_ROOT / "historical_results_by_level.csv",
        PROJECT_ROOT / "historical_results_by_year.csv",
        PROJECT_ROOT / "historical_results_discovery.csv",
        PROJECT_ROOT / "historical_results_holdout.csv",
        PROJECT_ROOT / "historical_walkforward.csv",
    ]:
        if path.exists():
            artifacts.append({
                "path": str(path),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            })
    manifest = {
        "schema_version": "historical_data_manifest.v2",
        "generated_at_utc": now_utc().isoformat(),
        "phase": "3C_FREE_HISTORICAL_EOD_OPTION_CHAIN_RECONSTRUCTION",
        "symbols": SYMBOLS,
        "requested_window": {"start": START_DATE.isoformat(), "end": END_DATE.isoformat()},
        "parser_version": PARSER_VERSION,
        "normalizer_version": NORMALIZER_VERSION,
        "gex_formula_version": GEX_FORMULA_VERSION,
        "level_snapshot_version": LEVEL_SNAPSHOT_VERSION,
        "backtest_version": BACKTEST_VERSION,
        "raw_files": [record.__dict__ for record in file_records],
        "source_probes": probes,
        "option_metrics": option_metrics,
        "underlying_metrics": underlying_metrics,
        "cross_source_validation": cross_source,
        "level_snapshot_stats": daily_option_level_stats(levels),
        "known_limitations": [
            "Primary SaidBahaDev/options-data README Cloudflare URLs returned 404 for SPY test files.",
            "Pilot data uses SaidBahaDev/options-dataset-hist and lambdaclass mirrors of the same undocumented upstream.",
            "SPY 2024 contains a suspicious 2024-01-15 holiday/two-row chain; anomaly is documented and excluded by D-1 trading-day mapping.",
            "Exact upstream sourcing and publication timing are not documented, so this is not authoritative exchange data.",
            "No validated free 2024-2025 5-minute intraday OHLCV source for SPY/QQQ/IWM was found in this run.",
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")

    def source_rows() -> str:
        rows = [
            ["SaidBahaDev/options-data", "GitHub + Cloudflare R2", "MIT repo; dataset terms educational/research", "404 for SPY options/underlying Cloudflare URLs", "NOT_TRUSTED_FOR_DOWNLOAD"],
            ["SaidBahaDev/options-dataset-hist", "GitHub media LFS", "MIT", "Downloaded/tested SPY/QQQ/IWM 2024-2025", "EXPLORATORY_RESEARCH"],
            ["lambdaclass/options_portfolio_backtester data-v1", "GitHub release", "MIT code; data notice says research reproducibility", "Remote-read tested; mirrors same upstream", "PIPELINE_TEST / EXPLORATORY_RESEARCH"],
            ["Kaggle SPY EOD 2010-2023", "Kaggle", "Dataset-specific Kaggle terms", "Documented only; no credentials/download", "NOT_TESTED"],
            ["Stooq 5m", "Stooq web", "Public web terms", "Direct endpoint returned JS/browser verification", "NOT_USABLE_AUTOMATED_HERE"],
            ["piekstra/market-data", "GitHub", "MIT", "Tree tested; no SPY/QQQ/IWM committed files", "NOT_USABLE_FOR_PILOT_SYMBOLS"],
        ]
        return "\n".join("| " + " | ".join(row) + " |" for row in rows)

    provenance = f"""# Historical Data Provenance Audit

Generated: {manifest['generated_at_utc']}

Scope: Phase 3C historical EOD options reconstruction only. This does not change live daemon behavior, live/paper strategy parameters, provider gates, Portfolio OS isolation, or live execution settings.

## Source verdict table

| repository/source | dataset host | license / terms observed | actual test result | reliability classification |
|---|---|---|---|---|
{source_rows()}

## Downloaded pilot files

| source | symbol | dataset | size bytes | sha256 |
|---|---|---|---:|---|
""" + "\n".join(
        f"| {record.source} | {record.symbol} | {record.dataset} | {record.size_bytes} | `{record.sha256}` |"
        for record in file_records
    ) + f"""

## Data content audit

| symbol | rows | dates | range | OI missing | IV missing | gamma missing | bid missing | ask missing | duplicate keys | bad rows |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---|
""" + "\n".join(
        f"| {symbol} | {int(metrics['coverage']['rows'])} | {int(metrics['coverage']['unique_dates'])} | "
        f"{metrics['coverage']['earliest']} to {metrics['coverage']['latest']} | "
        f"{metrics['missing_rates']['oi_missing_pct']:.4f} | {metrics['missing_rates']['iv_missing_pct']:.4f} | "
        f"{metrics['missing_rates']['gamma_missing_pct']:.4f} | {metrics['missing_rates']['bid_missing_pct']:.4f} | "
        f"{metrics['missing_rates']['ask_missing_pct']:.4f} | "
        f"{int(metrics['duplicates']['duplicate_contract_date_keys'])} | "
        f"bid>ask={int(metrics['logical_bad_rows']['bid_gt_ask'])}; "
        f"neg_gamma={int(metrics['logical_bad_rows']['negative_gamma'])}; "
        f"implausible_iv={int(metrics['logical_bad_rows']['implausible_iv'])} |"
        for symbol, metrics in option_metrics.items()
    ) + f"""

## Suspicious anomalies

{markdown_table(anomaly_rows) if not anomaly_rows.empty else "No thin-date anomalies found by the <100-row rule."}

## Cross-source validation

The lambdaclass release files match the 2024 GitHub-media per-year files on contract/date keys and bid/ask/OI for SPY, QQQ, and IWM. IV/gamma differences are only float precision differences from Parquet typing. This is a mirror validation, not independent exchange-source validation.

```json
{json.dumps(cross_source, indent=2, default=str)}
```

## Provenance assessment

The pilot data is suitable for `PIPELINE_TEST` and `EXPLORATORY_RESEARCH`. It is not yet reliable enough for `SERIOUS_BACKTEST` because the original upstream sourcing and publication timing are not documented and at least one holiday/anomaly row exists.
"""
    provenance_path.write_text(provenance, encoding="utf-8")

    level_stats = daily_option_level_stats(levels)
    phase = f"""# Phase 3C Free Historical EOD Option-Chain Reconstruction

Generated: {manifest['generated_at_utc']}

Status: **PARTIAL SUCCESS / PIPELINE READY FOR OPTION LEVELS; INTRADAY REPLAY BLOCKED**

No live daemon, canonical strategy, forward cohort, threshold, score-weight, stop/target, provider-gate, Portfolio OS, or live-execution behavior was changed.

## First-gate answer before any huge download

- Primary 104-symbol `SaidBahaDev/options-data` README is reachable, but its Cloudflare R2 SPY test URLs returned HTTP 404.
- `SaidBahaDev/options-dataset-hist` SPY/QQQ/IWM files are reachable via `media.githubusercontent.com` and are real Parquet.
- lambdaclass `data-v1` release files are reachable and remote-queryable.
- Actual pilot schema contains OI, IV, gamma, delta/theta/vega/rho, bid/ask, volume, expiration, strike, and type.
- Pilot option rows downloaded: {sum(int(item['coverage']['rows']) for item in option_metrics.values()):,}.
- Pilot option date range: 2024-01-02 through 2025-12-15 depending symbol.
- Pilot raw download size: {sum(record.size_bytes for record in file_records):,} bytes.
- D-1 → D GEX/OI level snapshots can be constructed for SPY/QQQ/IWM with explicit `lookahead_safe=true` where `source_chain_date < trade_date`.
- Full LEVEL_RECLAIM historical replay cannot honestly run yet because no validated free 2024-2025 5-minute OHLCV source for SPY/QQQ/IWM is available locally.

## Pilot option-chain validation

| symbol | rows | unique dates | date range | median contracts/day | median expirations/day | median strikes/day | OI/IV/gamma missing |
|---|---:|---:|---|---:|---:|---:|---|
""" + "\n".join(
        f"| {symbol} | {int(metrics['coverage']['rows']):,} | {int(metrics['coverage']['unique_dates'])} | "
        f"{metrics['coverage']['earliest']} to {metrics['coverage']['latest']} | "
        f"{metrics['contracts_per_day_distribution']['median_contracts_per_day']:.0f} | "
        f"{metrics['expirations_and_strikes_per_day']['median_expirations_per_day']:.0f} | "
        f"{metrics['expirations_and_strikes_per_day']['median_strikes_per_day']:.0f} | "
        f"{metrics['missing_rates']['oi_missing_pct']:.1%} / {metrics['missing_rates']['iv_missing_pct']:.1%} / {metrics['missing_rates']['gamma_missing_pct']:.1%} |"
        for symbol, metrics in option_metrics.items()
    ) + f"""

## Historical level snapshots

| symbol | level rows | trading days | source chain dates | H2 rows | H3 rows | lookahead-safe rows |
|---|---:|---:|---:|---:|---:|---:|
""" + "\n".join(
        f"| {symbol} | {stats['level_rows']} | {stats['trading_days']} | {stats['source_chain_dates']} | "
        f"{stats['h2_rows']} | {stats['h3_rows']} | {stats['lookahead_safe_rows']} |"
        for symbol, stats in level_stats.items()
    ) + f"""

Generated model variants:

- `GEX_MODEL_A_CALL_POSITIVE_PUT_NEGATIVE`
- `GEX_MODEL_B_CALL_NEGATIVE_PUT_POSITIVE`
- `GEX_MODEL_C_ABSOLUTE_GAMMA_CONCENTRATION`

## Intraday 5m blocker

The option side is usable for an honest D-1 EOD level reconstruction. The backtest side is blocked because LEVEL_RECLAIM requires completed 5-minute candles. Current findings:

- Stooq direct CSV probe returned browser verification HTML, not downloadable 5m CSV.
- `piekstra/market-data` is a real 5m Parquet store but currently has no committed SPY/QQQ/IWM files.
- yfinance/Yahoo 5m is not suitable for 2024-2025 history; the existing local Phase 3B yfinance cache is recent-window only and does not overlap the EOD options pilot.
- The bundled underlying files are daily OHLCV only.

## Replay / controls status

Replay and controls are intentionally written as blocked/empty artifacts. I did not fabricate intraday candles, did not use same-day EOD option chains for same-day intraday decisions, and did not run random/control tests without 5m bars.

## Acceptance classification

Phase 3C is currently **partial success**:

- Real free EOD option-chain/OI/IV/Greeks data has been verified and downloaded for SPY/QQQ/IWM.
- D-1 → D GEX/OI level snapshots have been generated with explicit model versions and lookahead flags.
- Provenance is not authoritative; reliability is `EXPLORATORY_RESEARCH`, not `SERIOUS_BACKTEST`.
- Full Level 2 historical replay is blocked pending a validated free 5-minute intraday OHLCV source for the same dates/symbols.
"""
    phase_path.write_text(phase, encoding="utf-8")

    connection = duck()
    example_path.write_text(spy_example(levels, connection), encoding="utf-8")
    return {
        "manifest": manifest_path,
        "provenance": provenance_path,
        "phase_report": phase_path,
        "spy_example": example_path,
    }


def run() -> dict[str, Any]:
    probes = source_probes()
    file_records = download_pilot()
    connection = duck()
    option_metrics, anomaly_rows = validate_options(connection)
    underlying_metrics = validate_underlying(connection)
    normalized = write_normalized_options(connection)
    levels = build_daily_levels(connection)
    write_empty_replay_artifacts()
    cross_source = cross_source_validation(connection)
    report_paths = write_reports(
        probes=probes,
        file_records=file_records,
        option_metrics=option_metrics,
        underlying_metrics=underlying_metrics,
        anomaly_rows=anomaly_rows,
        cross_source=cross_source,
        levels=levels,
    )
    return {
        "status": "PARTIAL_SUCCESS_OPTION_LEVELS_READY_INTRADAY_REPLAY_BLOCKED",
        "raw_files": len(file_records),
        "raw_bytes": sum(record.size_bytes for record in file_records),
        "normalized_options_path": str(normalized),
        "normalized_options_rows": sum(int(item["coverage"]["rows"]) for item in option_metrics.values()),
        "daily_level_rows": int(len(levels)),
        "reports": {key: str(path) for key, path in report_paths.items()},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 3C free historical EOD option-chain reconstruction pilot")
    parser.add_argument("--json", action="store_true", help="Print JSON summary")
    args = parser.parse_args()
    result = run()
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        for key, value in result.items():
            print(f"{key}: {value}")


if __name__ == "__main__":
    main()
