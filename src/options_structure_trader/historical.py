from __future__ import annotations

import hashlib
import json
import math
import os
import random
import time as pytime
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
from zoneinfo import ZoneInfo

from .config import PROJECT_ROOT, Settings
from .db import Repository
from .engines import ConfluenceEngine, LevelEngine, ReclaimSetupDetector, TradeConstructor
from .models import (Bar, EligibilityContext, FeatureSet, GexMap, GuardStatus, Level, ScanInput,
                     SetupEvent, TickerState)
from .scheduler import sanitize_message


EASTERN = ZoneInfo("America/New_York")
PARSER_VERSION = "historical_parser_v1"
NORMALIZATION_VERSION = "historical_normalization_v1"
GREEKS_MODEL_VERSION = "black_scholes_recompute_v1"
GEX_MODEL_VERSION = "historical_gex_v1"
REPLAY_ENGINE_VERSION = "historical_replay_v1"


HISTORICAL_DATA_TIERS = {
    "TIER_H1_FULL_INTRADAY": (
        "Timestamped historical option-chain snapshots with intraday OI/Greeks/IV where available, "
        "plus underlying intraday OHLCV."
    ),
    "TIER_H2_DAILY_CHAIN": (
        "One option chain/OI snapshot per day. Levels are static for the next session and must be known "
        "before the tested intraday decision."
    ),
    "TIER_H3_PARTIAL_CHAIN": (
        "Incomplete chain or structure snapshot. Missing OI/Greeks/expiries are explicit; usable only "
        "for exploratory reconstruction."
    ),
    "TIER_H4_PRICE_ONLY_CONTROL": "Underlying-only control with no option-derived structure.",
}


PRIORITY_SYMBOLS = [
    "SPY", "QQQ", "IWM",
    "NVDA", "AMD", "TSLA", "AAPL", "MSFT", "META", "AMZN", "PLTR", "HOOD",
    "OKLO", "CRWD", "COIN", "AVGO", "SMCI",
]


OPTION_CHAIN_COLUMNS = [
    "symbol", "option_symbol", "snapshot_date", "snapshot_timestamp", "expiration", "strike",
    "call_put", "bid", "ask", "last", "volume", "open_interest", "implied_volatility",
    "delta", "gamma", "vega", "theta", "vanna", "charm", "underlying_price", "provider",
    "publication_time", "source_quality", "historical_data_tier", "lookahead_risk",
    "greeks_source", "greeks_model_version", "raw_payload_reference", "downloaded_at_utc",
]


GEX_LEVEL_COLUMNS = [
    "symbol", "snapshot_date", "known_at_utc", "level_type", "price", "zone_low", "zone_high",
    "strength_score", "provider", "historical_data_tier", "source_quality", "lookahead_risk",
    "gex_model_version", "dealer_assumption", "raw_payload_reference", "metadata_json",
]


UNDERLYING_COLUMNS = [
    "symbol", "timeframe", "bar_start_utc", "bar_end_utc", "bar_start_et", "open", "high",
    "low", "close", "volume", "atr", "relative_volume", "provider", "dataset_source",
    "exchange_timezone", "adjusted", "split_adjusted", "source_timestamp_utc",
    "downloaded_at_utc", "raw_payload_reference",
]


REPLAY_COLUMNS = [
    "historical_setup_id", "symbol", "session_date", "entry_timestamp", "closed_at_utc",
    "setup_type", "direction", "strategy_type", "control_type", "level_type",
    "historical_data_tier", "source_quality", "provider", "lookahead_risk",
    "management_version", "slippage_variant", "slippage_bps", "entry", "stop", "tp1", "tp2",
    "tp3", "status", "exit_reason", "realized_R", "MFE_R", "MAE_R", "duration_minutes",
    "score", "rr", "gamma_regime", "dealer_assumption", "replay_engine_version",
]


RESULT_COLUMNS = [
    "bucket", "N", "unique_days", "expectancy", "profit_factor", "win_rate", "median_R",
    "average_winner", "average_loser", "MFE", "MAE", "max_drawdown", "positive_day_pct",
    "best_day", "best_day_R", "best_day_contribution", "worst_day", "worst_day_R",
    "remove_best_day_expectancy", "bootstrap_ci_low", "bootstrap_ci_high",
]


SOURCE_MATRIX = [
    {
        "source_name": "Cboe Historical Options Data Download",
        "url": "https://www.cboe.com/us/options/market_statistics/historical_data/",
        "cost": "free public web form",
        "account_required": False,
        "api_key_required": False,
        "historical_depth": "monthly/yearly historical volume by Cboe exchange/product/symbol",
        "option_chain_available": False,
        "oi_available": False,
        "iv_available": False,
        "greeks_available": False,
        "bid_ask_available": False,
        "trade_volume_available": True,
        "intraday_timestamps": False,
        "eod_only": True,
        "rate_limits": "manual/download form; not a chain API",
        "licensing_restrictions": "Cboe disclaimer; not guaranteed and not an OPRA chain dataset",
        "automated_download_allowed": "unclear",
        "suitability_score": 20,
        "notes": "Useful for aggregate volume context, not GEX reconstruction.",
    },
    {
        "source_name": "Cboe DataShop Option Quote Intervals",
        "url": "https://datashop.cboe.com/option-quote-intervals",
        "cost": "paid",
        "account_required": True,
        "api_key_required": "account/download access",
        "historical_depth": "January 2012 to present",
        "option_chain_available": True,
        "oi_available": "not primary field; depends on package",
        "iv_available": "optional add-on",
        "greeks_available": "optional add-on",
        "bid_ask_available": True,
        "trade_volume_available": True,
        "intraday_timestamps": True,
        "eod_only": False,
        "rate_limits": "commercial download/feed terms",
        "licensing_restrictions": "OPRA/exchange commercial terms",
        "automated_download_allowed": "yes after purchase/access grant",
        "suitability_score": 90,
        "notes": "Best technical fit, but not free.",
    },
    {
        "source_name": "OCC Volume and Open Interest Reports",
        "url": "https://www.theocc.com/market-data/market-data-reports/volume-and-open-interest/daily-volume",
        "cost": "free public reports",
        "account_required": False,
        "api_key_required": False,
        "historical_depth": "public report history varies; daily volume page indicates recent history",
        "option_chain_available": False,
        "oi_available": "aggregate/report-level, not full quoted chain",
        "iv_available": False,
        "greeks_available": False,
        "bid_ask_available": False,
        "trade_volume_available": True,
        "intraday_timestamps": False,
        "eod_only": True,
        "rate_limits": "public web/download behavior",
        "licensing_restrictions": "OCC terms/disclaimers",
        "automated_download_allowed": "unclear",
        "suitability_score": 30,
        "notes": "Can validate market-wide OI/volume context, not strike-level GEX.",
    },
    {
        "source_name": "NYSE Options Open-Close Volume Summary",
        "url": "https://www.nyse.com/data-products/catalog/open-close-volume-summary",
        "cost": "paid product with sample",
        "account_required": True,
        "api_key_required": "purchase/download access",
        "historical_depth": "previous trading day EOD; intraday 10-minute snapshots in product",
        "option_chain_available": False,
        "oi_available": False,
        "iv_available": False,
        "greeks_available": False,
        "bid_ask_available": False,
        "trade_volume_available": True,
        "intraday_timestamps": True,
        "eod_only": False,
        "rate_limits": "commercial access terms",
        "licensing_restrictions": "NYSE/ICE product terms",
        "automated_download_allowed": "yes after purchase/access grant",
        "suitability_score": 25,
        "notes": "Open/close volume is useful context but insufficient for chain/GEX.",
    },
    {
        "source_name": "Yahoo Finance / yfinance",
        "url": "https://pypi.org/project/yfinance/",
        "cost": "free unofficial",
        "account_required": False,
        "api_key_required": False,
        "historical_depth": "5m underlying candles available for recent windows; option chains are current/future snapshots",
        "option_chain_available": "current only",
        "oi_available": "current chain has openInterest",
        "iv_available": "current chain has impliedVolatility",
        "greeks_available": False,
        "bid_ask_available": True,
        "trade_volume_available": True,
        "intraday_timestamps": "underlying only",
        "eod_only": False,
        "rate_limits": "unofficial/no SLA",
        "licensing_restrictions": "Yahoo terms; unofficial wrapper",
        "automated_download_allowed": "unofficial; use cautiously",
        "suitability_score": 40,
        "notes": "Good H4 underlying source; not enough for historical option-chain reconstruction unless archived prospectively.",
    },
    {
        "source_name": "Alpha Vantage Historical Options",
        "url": "https://www.alphavantage.co/documentation/",
        "cost": "premium endpoint; free key available for other endpoints",
        "account_required": True,
        "api_key_required": True,
        "historical_depth": "docs state 15+ years for HISTORICAL_OPTIONS",
        "option_chain_available": True,
        "oi_available": True,
        "iv_available": True,
        "greeks_available": True,
        "bid_ask_available": "depends on endpoint fields",
        "trade_volume_available": True,
        "intraday_timestamps": False,
        "eod_only": True,
        "rate_limits": "plan-dependent",
        "licensing_restrictions": "Alpha Vantage plan/exchange terms",
        "automated_download_allowed": "API access if entitled",
        "suitability_score": 75,
        "notes": "Technically suitable for H2 if entitled; configured free key was probed and did not return data.",
    },
    {
        "source_name": "Finnhub",
        "url": "https://finnhub.io/docs/api",
        "cost": "free key plus paid tiers",
        "account_required": True,
        "api_key_required": True,
        "historical_depth": "equity quote/candles vary; options chain access plan-dependent",
        "option_chain_available": "plan-dependent",
        "oi_available": "plan-dependent",
        "iv_available": "plan-dependent",
        "greeks_available": "plan-dependent",
        "bid_ask_available": "plan-dependent",
        "trade_volume_available": "plan-dependent",
        "intraday_timestamps": "not usable in current probe",
        "eod_only": "unknown",
        "rate_limits": "free-tier limited",
        "licensing_restrictions": "Finnhub terms",
        "automated_download_allowed": "API access if entitled",
        "suitability_score": 20,
        "notes": "Useful quote heartbeat in live free-validation; current key probe returned 401 for option-chain endpoint.",
    },
    {
        "source_name": "MarketData.app",
        "url": "https://www.marketdata.app/data/options/",
        "cost": "free trial; paid subscription after",
        "account_required": True,
        "api_key_required": True,
        "historical_depth": "docs state historical EOD options quotes back to 2010",
        "option_chain_available": True,
        "oi_available": True,
        "iv_available": "real-time yes; docs say not currently for historical EOD",
        "greeks_available": "real-time yes; docs say not currently for historical EOD",
        "bid_ask_available": True,
        "trade_volume_available": True,
        "intraday_timestamps": False,
        "eod_only": True,
        "rate_limits": "plan-dependent",
        "licensing_restrictions": "OPRA/vendor terms",
        "automated_download_allowed": "API if account/trial entitled",
        "suitability_score": 65,
        "notes": "Potential H2 daily-chain candidate, but not keyless.",
    },
    {
        "source_name": "ThetaData",
        "url": "https://www.thetadata.net/",
        "cost": "trial/paid",
        "account_required": True,
        "api_key_required": True,
        "historical_depth": "historical options and stocks; flat files available",
        "option_chain_available": True,
        "oi_available": True,
        "iv_available": True,
        "greeks_available": True,
        "bid_ask_available": True,
        "trade_volume_available": True,
        "intraday_timestamps": True,
        "eod_only": False,
        "rate_limits": "plan/local terminal dependent",
        "licensing_restrictions": "vendor/exchange terms",
        "automated_download_allowed": "API/flat files if entitled",
        "suitability_score": 90,
        "notes": "Strong H1 candidate if trial/access is granted; not free keyless.",
    },
    {
        "source_name": "Intrinio",
        "url": "https://docs.intrinio.com/documentation/web_api/get_options_chain_v2",
        "cost": "sales/trial/paid",
        "account_required": True,
        "api_key_required": True,
        "historical_depth": "historical EOD options chain available via third party/contact sales",
        "option_chain_available": True,
        "oi_available": True,
        "iv_available": True,
        "greeks_available": True,
        "bid_ask_available": True,
        "trade_volume_available": True,
        "intraday_timestamps": "separate intraday product",
        "eod_only": "EOD endpoint; intraday product separate",
        "rate_limits": "plan-dependent",
        "licensing_restrictions": "Intrinio/vendor terms",
        "automated_download_allowed": "API if entitled",
        "suitability_score": 85,
        "notes": "Technically suitable but not free/no-signup.",
    },
    {
        "source_name": "Databento OPRA",
        "url": "https://databento.com/options",
        "cost": "usage-based with advertised starter credits",
        "account_required": True,
        "api_key_required": True,
        "historical_depth": "OPRA historical coverage; plan/dataset dependent",
        "option_chain_available": True,
        "oi_available": True,
        "iv_available": "not precomputed",
        "greeks_available": "not precomputed",
        "bid_ask_available": True,
        "trade_volume_available": True,
        "intraday_timestamps": True,
        "eod_only": False,
        "rate_limits": "API/credit/dataset dependent",
        "licensing_restrictions": "OPRA/vendor terms",
        "automated_download_allowed": "API if account/credits available",
        "suitability_score": 88,
        "notes": "High-quality H1 route if the user chooses account/credits; Greeks must be recomputed.",
    },
    {
        "source_name": "Massive / Polygon Options",
        "url": "https://massive.com/docs/rest/options/overview",
        "cost": "free reference tier; useful snapshots/market data require paid options plan",
        "account_required": True,
        "api_key_required": True,
        "historical_depth": "contract reference and option OHLC; snapshot history not applicable",
        "option_chain_available": "current snapshot only on paid options plans",
        "oi_available": True,
        "iv_available": True,
        "greeks_available": True,
        "bid_ask_available": True,
        "trade_volume_available": True,
        "intraday_timestamps": "option trades/quotes/bars on paid plans",
        "eod_only": False,
        "rate_limits": "plan-dependent",
        "licensing_restrictions": "vendor/exchange terms",
        "automated_download_allowed": "API if entitled",
        "suitability_score": 70,
        "notes": "Options Basic Free does not include chain snapshots; not usable for free H2 chains.",
    },
    {
        "source_name": "Tradier",
        "url": "https://docs.tradier.com/reference/brokerage-api-markets-get-options-chains",
        "cost": "developer/brokerage account; market data entitlement dependent",
        "account_required": True,
        "api_key_required": True,
        "historical_depth": "current chains; daily/weekly/monthly historical pricing by OCC option symbol",
        "option_chain_available": "current chain by expiration",
        "oi_available": True,
        "iv_available": True,
        "greeks_available": True,
        "bid_ask_available": True,
        "trade_volume_available": True,
        "intraday_timestamps": False,
        "eod_only": "historical endpoint is daily/weekly/monthly",
        "rate_limits": "account/plan dependent",
        "licensing_restrictions": "Tradier/ORATS terms",
        "automated_download_allowed": "API if account/token entitled",
        "suitability_score": 45,
        "notes": "Can help contract-level history after contracts are known; not a keyless historical chain archive.",
    },
    {
        "source_name": "Public Kaggle/GitHub/academic archives",
        "url": "https://github.com/topics/options-data",
        "cost": "varies/free",
        "account_required": "varies",
        "api_key_required": "varies",
        "historical_depth": "dataset-specific",
        "option_chain_available": "dataset-specific",
        "oi_available": "dataset-specific",
        "iv_available": "dataset-specific",
        "greeks_available": "dataset-specific",
        "bid_ask_available": "dataset-specific",
        "trade_volume_available": "dataset-specific",
        "intraday_timestamps": "dataset-specific",
        "eod_only": "dataset-specific",
        "rate_limits": "dataset-specific",
        "licensing_restrictions": "must inspect per dataset",
        "automated_download_allowed": "not assumed",
        "suitability_score": 35,
        "notes": "Potential one-off research data, but provenance/licensing/coverage are usually the blocker.",
    },
]


@dataclass
class Artifact:
    name: str
    path: Path
    rows: int
    source: str
    downloaded_at_utc: str
    checksum_sha256: str | None = None
    parser_version: str = PARSER_VERSION
    normalization_version: str = NORMALIZATION_VERSION


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _json_default(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_id(*parts: Any) -> str:
    return hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:24]


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def _read_env_key(name: str) -> str | None:
    value = os.environ.get(name)
    if value:
        return value.strip()
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip() or None
    return None


def _empty_frame(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def _write_frame(frame: pd.DataFrame, path: Path, columns: list[str] | None = None) -> Artifact:
    path.parent.mkdir(parents=True, exist_ok=True)
    if columns is not None:
        frame = frame.copy() if not frame.empty else _empty_frame(columns)
        for column in columns:
            if column not in frame.columns:
                frame[column] = None
        frame = frame[columns + [column for column in frame.columns if column not in columns]]
    if path.suffix == ".parquet":
        frame.to_parquet(path, index=False)
    else:
        frame.to_csv(path, index=False)
    return Artifact(
        name=path.name,
        path=path,
        rows=int(len(frame)),
        source="generated",
        downloaded_at_utc=_now_utc().isoformat(),
        checksum_sha256=_sha256_file(path),
    )


def _parse_dt(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        result = value
    else:
        try:
            result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _session_date(value: datetime) -> str:
    return value.astimezone(EASTERN).date().isoformat()


def _rth_close(value: datetime) -> datetime:
    local = value.astimezone(EASTERN)
    return datetime.combine(local.date(), time(16, 0), EASTERN).astimezone(timezone.utc)


class HistoricalGreeksEngine:
    """Deterministic Black-Scholes recomputation for missing historical Greeks.

    IV is never fabricated. Rows without strike, expiry, IV, or underlying price
    are returned with unavailable Greek fields.
    """

    @staticmethod
    def _norm_pdf(value: float) -> float:
        return math.exp(-0.5 * value * value) / math.sqrt(2 * math.pi)

    @staticmethod
    def _norm_cdf(value: float) -> float:
        return 0.5 * (1 + math.erf(value / math.sqrt(2)))

    def recompute(self, row: dict[str, Any], *, risk_free_rate: float = 0.045,
                  dividend_yield: float = 0.0) -> dict[str, Any]:
        spot = _safe_float(row.get("underlying_price"))
        strike = _safe_float(row.get("strike"))
        iv = _safe_float(row.get("implied_volatility"))
        expiry_raw = row.get("expiration")
        snapshot_raw = row.get("snapshot_timestamp") or row.get("snapshot_date")
        expiry = _parse_dt(f"{expiry_raw}T16:00:00-04:00") if expiry_raw else None
        snapshot = _parse_dt(snapshot_raw)
        if not snapshot and row.get("snapshot_date"):
            snapshot = _parse_dt(f"{row['snapshot_date']}T16:00:00-04:00")
        call_put = str(row.get("call_put") or "").upper()
        if call_put in {"C", "CALL"}:
            cp = "CALL"
        elif call_put in {"P", "PUT"}:
            cp = "PUT"
        else:
            cp = ""
        if not spot or not strike or not iv or not expiry or not snapshot or expiry <= snapshot or cp not in {"CALL", "PUT"}:
            return {
                "delta": None, "gamma": None, "vega": None, "theta": None,
                "vanna": None, "charm": None, "greeks_source": "UNAVAILABLE",
                "greeks_model_version": GREEKS_MODEL_VERSION,
            }
        years = max((expiry - snapshot).total_seconds() / (365.0 * 24 * 3600), 1 / (365 * 24))
        vol_sqrt_t = iv * math.sqrt(years)
        d1 = (math.log(spot / strike) + (risk_free_rate - dividend_yield + 0.5 * iv * iv) * years) / vol_sqrt_t
        d2 = d1 - vol_sqrt_t
        pdf = self._norm_pdf(d1)
        discount_q = math.exp(-dividend_yield * years)
        discount_r = math.exp(-risk_free_rate * years)
        if cp == "CALL":
            delta = discount_q * self._norm_cdf(d1)
            theta = (-(spot * discount_q * pdf * iv) / (2 * math.sqrt(years))
                     - risk_free_rate * strike * discount_r * self._norm_cdf(d2)
                     + dividend_yield * spot * discount_q * self._norm_cdf(d1))
        else:
            delta = -discount_q * self._norm_cdf(-d1)
            theta = (-(spot * discount_q * pdf * iv) / (2 * math.sqrt(years))
                     + risk_free_rate * strike * discount_r * self._norm_cdf(-d2)
                     - dividend_yield * spot * discount_q * self._norm_cdf(-d1))
        gamma = discount_q * pdf / (spot * vol_sqrt_t)
        vega = spot * discount_q * pdf * math.sqrt(years) / 100
        vanna = -discount_q * pdf * d2 / iv
        charm = dividend_yield * discount_q * (self._norm_cdf(d1) if cp == "CALL" else self._norm_cdf(d1) - 1)
        charm -= discount_q * pdf * (2 * (risk_free_rate - dividend_yield) * years - d2 * vol_sqrt_t) / (2 * years * vol_sqrt_t)
        return {
            "delta": round(delta, 8), "gamma": round(gamma, 10), "vega": round(vega, 8),
            "theta": round(theta / 365, 8), "vanna": round(vanna, 8), "charm": round(charm / 365, 8),
            "greeks_source": "RECOMPUTED", "greeks_model_version": GREEKS_MODEL_VERSION,
        }


class HistoricalGEXEngine:
    """Reconstructs strike-level gamma exposure from normalized historical chains."""

    DEALER_ASSUMPTIONS = {
        "dealer_short_calls_long_puts": {"CALL": -1, "PUT": 1},
        "dealer_long_calls_short_puts": {"CALL": 1, "PUT": -1},
        "same_sign_customer_long": {"CALL": -1, "PUT": -1},
    }

    def __init__(self, settings: Settings):
        self.settings = settings

    def reconstruct(self, chain: pd.DataFrame,
                    dealer_assumption: str = "dealer_short_calls_long_puts") -> pd.DataFrame:
        if chain.empty:
            return _empty_frame([
                "symbol", "snapshot_date", "known_at_utc", "dealer_assumption", "strike", "call_gex",
                "put_gex", "net_gex", "absolute_gex", "local_gamma_concentration",
                "gex_model_version", "historical_data_tier", "source_quality", "lookahead_risk",
            ])
        signs = self.DEALER_ASSUMPTIONS.get(dealer_assumption, self.DEALER_ASSUMPTIONS["dealer_short_calls_long_puts"])
        rows: list[dict[str, Any]] = []
        for item in chain.to_dict("records"):
            gamma = _safe_float(item.get("gamma"))
            oi = _safe_float(item.get("open_interest"))
            spot = _safe_float(item.get("underlying_price"))
            strike = _safe_float(item.get("strike"))
            cp = str(item.get("call_put") or "").upper()
            if cp in {"C", "CALL"}:
                cp = "CALL"
            elif cp in {"P", "PUT"}:
                cp = "PUT"
            else:
                continue
            if gamma is None or oi is None or spot is None or strike is None:
                continue
            gex = gamma * oi * 100 * spot * spot * 0.01 * signs[cp]
            rows.append({
                "symbol": item.get("symbol"), "snapshot_date": item.get("snapshot_date"),
                "known_at_utc": item.get("publication_time") or item.get("snapshot_timestamp"),
                "dealer_assumption": dealer_assumption, "strike": strike,
                "call_gex": gex if cp == "CALL" else 0.0,
                "put_gex": gex if cp == "PUT" else 0.0,
                "historical_data_tier": item.get("historical_data_tier"),
                "source_quality": item.get("source_quality"),
                "lookahead_risk": bool(item.get("lookahead_risk")),
            })
        if not rows:
            return _empty_frame([
                "symbol", "snapshot_date", "known_at_utc", "dealer_assumption", "strike", "call_gex",
                "put_gex", "net_gex", "absolute_gex", "local_gamma_concentration",
                "gex_model_version", "historical_data_tier", "source_quality", "lookahead_risk",
            ])
        frame = pd.DataFrame(rows)
        grouped = frame.groupby(
            ["symbol", "snapshot_date", "known_at_utc", "dealer_assumption", "strike"],
            dropna=False,
        ).agg({
            "call_gex": "sum", "put_gex": "sum", "historical_data_tier": "first",
            "source_quality": "first", "lookahead_risk": "max",
        }).reset_index()
        grouped["net_gex"] = grouped["call_gex"] + grouped["put_gex"]
        grouped["absolute_gex"] = grouped["net_gex"].abs()
        grouped["local_gamma_concentration"] = grouped.groupby(
            ["symbol", "snapshot_date", "dealer_assumption"]
        )["absolute_gex"].transform(lambda value: value / max(float(value.sum()), 1.0))
        grouped["gex_model_version"] = GEX_MODEL_VERSION
        return grouped

    def derive_levels(self, strike_gex: pd.DataFrame) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        if strike_gex.empty:
            return _empty_frame(GEX_LEVEL_COLUMNS)
        for (_, _, assumption), group in strike_gex.groupby(["symbol", "snapshot_date", "dealer_assumption"], dropna=False):
            symbol = str(group["symbol"].iloc[0]).upper()
            known_at = group["known_at_utc"].iloc[0]
            source_quality = group["source_quality"].iloc[0]
            tier = group["historical_data_tier"].iloc[0]
            lookahead = bool(group["lookahead_risk"].max())
            ordered = group.sort_values("strike").copy()
            ordered["cumulative_gex"] = ordered["net_gex"].cumsum()
            flip_price = None
            prior = None
            for item in ordered.to_dict("records"):
                value = _safe_float(item.get("cumulative_gex"), 0) or 0
                if prior and ((prior[1] <= 0 < value) or (prior[1] >= 0 > value)):
                    flip_price = float(item["strike"])
                    break
                prior = (float(item["strike"]), value)
            call_wall = None
            put_wall = None
            if "call_gex" in ordered:
                calls = ordered[ordered["call_gex"].abs() > 0]
                if not calls.empty:
                    call_wall = float(calls.loc[calls["call_gex"].abs().idxmax()]["strike"])
            if "put_gex" in ordered:
                puts = ordered[ordered["put_gex"].abs() > 0]
                if not puts.empty:
                    put_wall = float(puts.loc[puts["put_gex"].abs().idxmax()]["strike"])
            top_nodes = ordered.sort_values("absolute_gex", ascending=False).head(5)
            for level_type, price, strength in [
                ("GAMMA_FLIP", flip_price, 1.0), ("CALL_WALL", call_wall, 0.9), ("PUT_WALL", put_wall, 0.9),
            ]:
                if price is None:
                    continue
                width = max(0.001 * abs(price), 0.05)
                rows.append({
                    "symbol": symbol, "snapshot_date": group["snapshot_date"].iloc[0],
                    "known_at_utc": known_at, "level_type": level_type, "price": float(price),
                    "zone_low": float(price) - width, "zone_high": float(price) + width,
                    "strength_score": strength, "provider": "historical_chain_reconstruction",
                    "historical_data_tier": tier, "source_quality": source_quality,
                    "lookahead_risk": lookahead, "gex_model_version": GEX_MODEL_VERSION,
                    "dealer_assumption": assumption, "raw_payload_reference": None,
                    "metadata_json": json.dumps({"source": "chain_reconstruction"}, sort_keys=True),
                })
            for item in top_nodes.to_dict("records"):
                price = float(item["strike"])
                width = max(0.001 * abs(price), 0.05)
                rows.append({
                    "symbol": symbol, "snapshot_date": group["snapshot_date"].iloc[0],
                    "known_at_utc": known_at, "level_type": "GEX_NODE", "price": price,
                    "zone_low": price - width, "zone_high": price + width,
                    "strength_score": min(1.0, float(item.get("local_gamma_concentration") or 0) * 5),
                    "provider": "historical_chain_reconstruction",
                    "historical_data_tier": tier, "source_quality": source_quality,
                    "lookahead_risk": lookahead, "gex_model_version": GEX_MODEL_VERSION,
                    "dealer_assumption": assumption, "raw_payload_reference": None,
                    "metadata_json": json.dumps({
                        "net_gex": item.get("net_gex"),
                        "absolute_gex": item.get("absolute_gex"),
                    }, sort_keys=True),
                })
        return pd.DataFrame(rows)


class HistoricalReconstructionPipeline:
    """Separate research pipeline for historical reconstruction.

    It reads live archive data and downloads free underlying data, but it does
    not mutate live strategy parameters, paper trades, cohorts, or production
    gates.
    """

    def __init__(self, repository: Repository, settings: Settings, output_root: Path | None = None):
        self.repository = repository
        self.settings = settings
        self.output_root = output_root or PROJECT_ROOT
        self.raw_root = self.output_root / "data" / "historical" / "raw"
        self.greeks = HistoricalGreeksEngine()
        self.gex_engine = HistoricalGEXEngine(settings)
        self.level_engine = LevelEngine(settings)
        self.detector = ReclaimSetupDetector(settings, ConfluenceEngine(settings), TradeConstructor(settings))

    def run(self, *, symbols: Iterable[str] | None = None, period: str = "20d",
            interval: str = "5m") -> dict[str, Any]:
        symbols = [symbol.upper().strip() for symbol in (symbols or PRIORITY_SYMBOLS) if symbol.strip()]
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.raw_root.mkdir(parents=True, exist_ok=True)
        started = _now_utc()
        artifacts: list[Artifact] = []
        probes = self._probe_sources()
        source_matrix_path = self.output_root / "HISTORICAL_OPTIONS_SOURCE_MATRIX.md"
        source_matrix_path.write_text(self._source_matrix_markdown(probes), encoding="utf-8")

        option_chains = self._collect_historical_option_chains(symbols, probes)
        underlying = self._collect_underlying(symbols, period=period, interval=interval)
        local_gex_levels = self._local_archive_gex_levels(symbols)
        chain_gex = self.gex_engine.reconstruct(option_chains)
        chain_levels = self.gex_engine.derive_levels(chain_gex)
        gex_levels = pd.concat([chain_levels, local_gex_levels], ignore_index=True) if not local_gex_levels.empty else chain_levels
        controls = self._control_levels(underlying)

        replay = self._replay(underlying, gex_levels, strategy_type="OPTIONS_STRUCTURE_RECON")
        control_replay = self._replay(underlying, controls, strategy_type="PRICE_CONTROL")
        all_replay = pd.concat([replay, control_replay], ignore_index=True)

        artifacts.append(_write_frame(option_chains, self.output_root / "historical_option_chains.parquet", OPTION_CHAIN_COLUMNS))
        artifacts.append(_write_frame(gex_levels, self.output_root / "historical_gex_levels.parquet", GEX_LEVEL_COLUMNS))
        artifacts.append(_write_frame(underlying, self.output_root / "historical_underlying_5m.parquet", UNDERLYING_COLUMNS))
        artifacts.append(_write_frame(all_replay, self.output_root / "historical_replay_trades.parquet", REPLAY_COLUMNS))

        by_day = self._group_results(all_replay, "session_date")
        by_symbol = self._group_results(all_replay, "symbol")
        by_direction = self._group_results(all_replay, "direction")
        by_level = self._group_results(all_replay, "level_type")
        by_management = self._management_results(all_replay)
        holdout = self._holdout_results(all_replay)
        control_compare = self._control_comparison(all_replay)

        for frame, filename in [
            (by_day, "historical_results_by_day.csv"),
            (by_symbol, "historical_results_by_symbol.csv"),
            (by_direction, "historical_results_by_direction.csv"),
            (by_level, "historical_results_by_level_type.csv"),
            (by_management, "historical_management_comparison.csv"),
            (holdout, "historical_holdout_results.csv"),
            (control_compare, "historical_control_comparison.csv"),
        ]:
            artifacts.append(_write_frame(frame, self.output_root / filename, RESULT_COLUMNS if filename != "historical_control_comparison.csv" else None))

        validation = self._live_validation(all_replay)
        summary = self._summary(
            started=started, symbols=symbols, probes=probes, option_chains=option_chains,
            underlying=underlying, gex_levels=gex_levels, replay=all_replay,
            validation=validation, artifacts=artifacts,
        )
        manifest_path = self.output_root / "HISTORICAL_DATA_MANIFEST.json"
        manifest_path.write_text(json.dumps(summary["manifest"], indent=2, default=_json_default), encoding="utf-8")
        report_path = self.output_root / "PHASE_3B_HISTORICAL_RECONSTRUCTION.md"
        report_path.write_text(self._report_markdown(summary, validation), encoding="utf-8")
        return {
            "report": summary["report"],
            "markdown_path": str(report_path),
            "source_matrix_path": str(source_matrix_path),
            "manifest_path": str(manifest_path),
            "parquet_paths": [
                str(self.output_root / "historical_option_chains.parquet"),
                str(self.output_root / "historical_gex_levels.parquet"),
                str(self.output_root / "historical_underlying_5m.parquet"),
                str(self.output_root / "historical_replay_trades.parquet"),
            ],
            "csv_paths": [str(self.output_root / name) for name in [
                "historical_results_by_day.csv", "historical_results_by_symbol.csv",
                "historical_results_by_direction.csv", "historical_results_by_level_type.csv",
                "historical_management_comparison.csv", "historical_holdout_results.csv",
                "historical_control_comparison.csv",
            ]],
        }

    def _probe_sources(self) -> dict[str, Any]:
        probes: dict[str, Any] = {"generated_at_utc": _now_utc().isoformat()}
        probes["yfinance"] = self._probe_yfinance()
        probes["alpha_vantage"] = self._probe_alpha_vantage()
        probes["finnhub"] = self._probe_finnhub()
        raw_path = self.raw_root / "source_probes.json"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(json.dumps(probes, indent=2, default=_json_default), encoding="utf-8")
        return probes

    def _probe_yfinance(self) -> dict[str, Any]:
        started = pytime.perf_counter()
        try:
            import yfinance as yf
            ticker = yf.Ticker("SPY")
            hist = ticker.history(period="5d", interval="5m", prepost=False, auto_adjust=False)
            expirations = list(ticker.options or [])
            chain_meta: dict[str, Any] = {"expiration_count": len(expirations), "current_chain_available": bool(expirations)}
            if expirations:
                chain = ticker.option_chain(expirations[0])
                calls = chain.calls
                chain_meta.update({
                    "sample_expiration": expirations[0],
                    "sample_call_rows": int(len(calls)),
                    "has_open_interest": "openInterest" in calls.columns,
                    "has_implied_volatility": "impliedVolatility" in calls.columns,
                    "has_greeks": any(column in calls.columns for column in ["delta", "gamma", "theta", "vega"]),
                    "historical_chain_snapshots_available": False,
                })
            return {
                "status": "AVAILABLE",
                "underlying_5m_available": not hist.empty,
                "underlying_rows": int(len(hist)),
                "first_underlying_bar": str(hist.index[0]) if not hist.empty else None,
                "last_underlying_bar": str(hist.index[-1]) if not hist.empty else None,
                **chain_meta,
                "latency_ms": int((pytime.perf_counter() - started) * 1000),
            }
        except Exception as exc:
            return {"status": "ERROR", "error": sanitize_message(exc),
                    "latency_ms": int((pytime.perf_counter() - started) * 1000)}

    def _probe_alpha_vantage(self) -> dict[str, Any]:
        key = _read_env_key("ALPHA_VANTAGE_API_KEY")
        if not key:
            return {"status": "NOT_CONFIGURED", "configured": False}
        started = pytime.perf_counter()
        try:
            import httpx
            response = httpx.get(
                "https://www.alphavantage.co/query",
                params={"function": "HISTORICAL_OPTIONS", "symbol": "SPY",
                        "date": "2026-08-28", "apikey": key},
                timeout=20,
            )
            data = response.json()
            rows = data.get("data") if isinstance(data, dict) else None
            message_type = next((name for name in ["Information", "Note", "Error Message"]
                                 if isinstance(data, dict) and name in data), None)
            return {
                "status": "DATA_AVAILABLE" if isinstance(rows, list) and rows else
                ("ENTITLEMENT_OR_PREMIUM_LIMIT" if message_type else "EMPTY"),
                "configured": True,
                "authenticated": message_type != "Error Message",
                "http_status": response.status_code,
                "historical_options_rows": len(rows) if isinstance(rows, list) else 0,
                "message_type": message_type,
                "latency_ms": int((pytime.perf_counter() - started) * 1000),
            }
        except Exception as exc:
            return {"status": "ERROR", "configured": True, "error": sanitize_message(exc),
                    "latency_ms": int((pytime.perf_counter() - started) * 1000)}

    def _probe_finnhub(self) -> dict[str, Any]:
        key = _read_env_key("FINNHUB_API_KEY")
        if not key:
            return {"status": "NOT_CONFIGURED", "configured": False}
        started = pytime.perf_counter()
        try:
            import httpx
            response = httpx.get(
                "https://finnhub.io/api/v1/stock/option-chain",
                params={"symbol": "SPY", "token": key},
                timeout=20,
            )
            data = response.json()
            rows = data.get("data") if isinstance(data, dict) else None
            expirations = data.get("expirationDates") if isinstance(data, dict) else None
            return {
                "status": "DATA_AVAILABLE" if response.status_code == 200 and isinstance(rows, list) and rows else
                ("AUTH_OR_ENTITLEMENT_FAILED" if response.status_code in {401, 403} else "EMPTY"),
                "configured": True,
                "authenticated": response.status_code not in {401, 403},
                "http_status": response.status_code,
                "expiration_count": len(expirations) if isinstance(expirations, list) else 0,
                "option_chain_rows": len(rows) if isinstance(rows, list) else 0,
                "latency_ms": int((pytime.perf_counter() - started) * 1000),
            }
        except Exception as exc:
            return {"status": "ERROR", "configured": True, "error": sanitize_message(exc),
                    "latency_ms": int((pytime.perf_counter() - started) * 1000)}

    def _collect_historical_option_chains(self, symbols: list[str], probes: dict[str, Any]) -> pd.DataFrame:
        del symbols, probes
        # No probed free/no-signup source returned historical chain rows. Keep an
        # explicit empty schema instead of fabricating chain/OI/Greeks.
        return _empty_frame(OPTION_CHAIN_COLUMNS)

    def _collect_underlying(self, symbols: list[str], *, period: str, interval: str) -> pd.DataFrame:
        live = self._local_archive_underlying(symbols)
        yf_frame = self._yfinance_underlying(symbols, period=period, interval=interval)
        frames = [frame for frame in [live, yf_frame] if not frame.empty]
        if not frames:
            return _empty_frame(UNDERLYING_COLUMNS)
        combined = pd.concat(frames, ignore_index=True)
        combined["_source_rank"] = combined["dataset_source"].map({"LOCAL_LIVE_ARCHIVE": 0}).fillna(1)
        combined = combined.sort_values(["symbol", "bar_end_utc", "_source_rank"]).drop_duplicates(
            ["symbol", "bar_end_utc"], keep="first")
        return combined.drop(columns=["_source_rank"])

    def _local_archive_underlying(self, symbols: list[str]) -> pd.DataFrame:
        rows = self.repository.list_json("market_bars", "WHERE timeframe=?", ("5m",), limit=250000)
        allowed = set(symbols)
        output = []
        for row in rows:
            symbol = str(row.get("ticker", "")).upper()
            if symbol not in allowed:
                continue
            start = _parse_dt(row.get("bar_start_utc"))
            end = _parse_dt(row.get("bar_end_utc") or row.get("source_timestamp_utc"))
            if not start and end:
                start = end - timedelta(minutes=5)
            if not start or not end:
                continue
            output.append({
                "symbol": symbol, "timeframe": "5m", "bar_start_utc": start.isoformat(),
                "bar_end_utc": end.isoformat(), "bar_start_et": start.astimezone(EASTERN).isoformat(),
                "open": _safe_float(row.get("open")), "high": _safe_float(row.get("high")),
                "low": _safe_float(row.get("low")), "close": _safe_float(row.get("close")),
                "volume": _safe_float(row.get("volume"), 0), "atr": _safe_float(row.get("atr"), 0.5),
                "relative_volume": _safe_float(row.get("relative_volume"), 1.0),
                "provider": row.get("source") or "local_archive", "dataset_source": "LOCAL_LIVE_ARCHIVE",
                "exchange_timezone": "America/New_York", "adjusted": False, "split_adjusted": "unknown",
                "source_timestamp_utc": row.get("source_timestamp_utc") or end.isoformat(),
                "downloaded_at_utc": row.get("ingestion_timestamp_utc") or _now_utc().isoformat(),
                "raw_payload_reference": row.get("raw_payload_reference"),
            })
        return pd.DataFrame(output) if output else _empty_frame(UNDERLYING_COLUMNS)

    def _yfinance_underlying(self, symbols: list[str], *, period: str, interval: str) -> pd.DataFrame:
        try:
            import yfinance as yf
        except Exception:
            return _empty_frame(UNDERLYING_COLUMNS)
        rows: list[dict[str, Any]] = []
        downloaded_at = _now_utc().isoformat()
        for symbol in symbols:
            started = pytime.perf_counter()
            try:
                frame = yf.Ticker(symbol).history(period=period, interval=interval, prepost=False, auto_adjust=False)
            except Exception as exc:
                self._write_raw_json(f"yfinance_error_{symbol}.json", {
                    "symbol": symbol, "error": sanitize_message(exc), "downloaded_at_utc": downloaded_at,
                })
                continue
            raw_path = self.raw_root / f"yfinance_underlying_{symbol}_{period}_{interval}.csv"
            frame.to_csv(raw_path)
            for timestamp, bar in frame.iterrows():
                if pd.isna(bar.get("Open")) or pd.isna(bar.get("Close")):
                    continue
                ts = pd.Timestamp(timestamp)
                if ts.tzinfo is None:
                    ts = ts.tz_localize(EASTERN)
                start = ts.tz_convert(timezone.utc).to_pydatetime()
                minutes = 5 if interval == "5m" else int(interval.rstrip("m")) if interval.endswith("m") else 5
                end = start + timedelta(minutes=minutes)
                rows.append({
                    "symbol": symbol, "timeframe": interval, "bar_start_utc": start.isoformat(),
                    "bar_end_utc": end.isoformat(), "bar_start_et": start.astimezone(EASTERN).isoformat(),
                    "open": float(bar["Open"]), "high": float(bar["High"]), "low": float(bar["Low"]),
                    "close": float(bar["Close"]), "volume": float(bar.get("Volume", 0) or 0),
                    "atr": None, "relative_volume": 1.0, "provider": "yfinance",
                    "dataset_source": "YFINANCE_RECENT_UNDERLYING", "exchange_timezone": "America/New_York",
                    "adjusted": False, "split_adjusted": "raw_yahoo_ohlcv", "source_timestamp_utc": end.isoformat(),
                    "downloaded_at_utc": downloaded_at, "raw_payload_reference": str(raw_path),
                    "provider_latency_ms": int((pytime.perf_counter() - started) * 1000),
                })
        frame = pd.DataFrame(rows) if rows else _empty_frame(UNDERLYING_COLUMNS)
        if not frame.empty:
            frame = self._add_atr(frame)
        return frame

    def _add_atr(self, frame: pd.DataFrame) -> pd.DataFrame:
        frame = frame.sort_values(["symbol", "bar_end_utc"]).copy()
        values = []
        for _, group in frame.groupby("symbol", sort=False):
            high = pd.to_numeric(group["high"], errors="coerce")
            low = pd.to_numeric(group["low"], errors="coerce")
            close = pd.to_numeric(group["close"], errors="coerce")
            prior_close = close.shift(1)
            tr = pd.concat([(high - low).abs(), (high - prior_close).abs(), (low - prior_close).abs()], axis=1).max(axis=1)
            atr = tr.rolling(14, min_periods=1).mean()
            values.append(atr)
        frame["atr"] = pd.concat(values).sort_index().clip(lower=0.01)
        return frame

    def _local_archive_gex_levels(self, symbols: list[str]) -> pd.DataFrame:
        rows = self.repository.list_json("options_gex_snapshots", limit=250000)
        allowed = set(symbols)
        output: list[dict[str, Any]] = []
        for row in rows:
            symbol = str(row.get("ticker", "")).upper()
            if symbol not in allowed:
                continue
            try:
                gex = GexMap.model_validate(row)
            except Exception:
                continue
            if gex.source_timestamp_utc > _now_utc():
                continue
            spread = max(abs(gex.spot) * 0.0002, 0.01)
            for level in self.level_engine.from_gex(gex, max(abs(gex.spot) * 0.01, 0.25), spread):
                metadata = {
                    "source": "local_live_archive_gex_snapshot",
                    "gamma_regime": gex.gamma_regime,
                    "missing_required_fields": gex.missing_required_fields,
                    "raw_payload_reference": gex.raw_payload_reference,
                }
                output.append({
                    "symbol": symbol, "snapshot_date": _session_date(gex.source_timestamp_utc),
                    "known_at_utc": gex.source_timestamp_utc.isoformat(),
                    "level_type": level.level_type, "price": level.price,
                    "zone_low": level.zone_low, "zone_high": level.zone_high,
                    "strength_score": level.strength_score, "provider": f"local_archive_{gex.source}",
                    "historical_data_tier": "TIER_H3_PARTIAL_CHAIN",
                    "source_quality": "LOCAL_LIVE_ARCHIVE_STRUCTURE_ONLY",
                    "lookahead_risk": False, "gex_model_version": "live_archive_level_engine_v1",
                    "dealer_assumption": "provider_precomputed_or_partial",
                    "raw_payload_reference": gex.raw_payload_reference,
                    "metadata_json": json.dumps(metadata, sort_keys=True, default=_json_default),
                })
        return pd.DataFrame(output) if output else _empty_frame(GEX_LEVEL_COLUMNS)

    def _control_levels(self, underlying: pd.DataFrame) -> pd.DataFrame:
        if underlying.empty:
            return _empty_frame(GEX_LEVEL_COLUMNS)
        rows: list[dict[str, Any]] = []
        rng = random.Random(20260904)
        frame = underlying.copy()
        frame["session_date"] = pd.to_datetime(frame["bar_end_utc"], utc=True).dt.tz_convert(EASTERN).dt.date.astype(str)
        for symbol, group in frame.groupby("symbol"):
            by_day = {day: day_frame.sort_values("bar_end_utc") for day, day_frame in group.groupby("session_date")}
            days = sorted(by_day)
            for index, day in enumerate(days):
                if index == 0:
                    continue
                prev = by_day[days[index - 1]]
                current = by_day[day]
                if prev.empty or current.empty:
                    continue
                known_at = str(prev["bar_end_utc"].iloc[-1])
                prev_high = float(pd.to_numeric(prev["high"], errors="coerce").max())
                prev_low = float(pd.to_numeric(prev["low"], errors="coerce").min())
                first_close = float(pd.to_numeric(current["close"], errors="coerce").iloc[0])
                atr = float(pd.to_numeric(prev["atr"], errors="coerce").median() or max(first_close * 0.005, 0.25))
                control_prices = [
                    ("PREVIOUS_DAY_HIGH", prev_high),
                    ("PREVIOUS_DAY_LOW", prev_low),
                    ("PRICE_ONLY_PRIOR_RANGE_MID", (prev_high + prev_low) / 2),
                    ("RANDOM_NEARBY_PRICE_LEVEL", first_close + rng.uniform(-1.0, 1.0) * atr),
                ]
                for control_type, price_value in control_prices:
                    width = max(0.20 * atr, 0.001 * abs(price_value), 0.05)
                    rows.append({
                        "symbol": symbol, "snapshot_date": day, "known_at_utc": known_at,
                        "level_type": "GEX_NODE", "price": price_value,
                        "zone_low": price_value - width, "zone_high": price_value + width,
                        "strength_score": 0.7, "provider": "historical_price_control",
                        "historical_data_tier": "TIER_H4_PRICE_ONLY_CONTROL",
                        "source_quality": "PRICE_ONLY_CONTROL",
                        "lookahead_risk": False, "gex_model_version": "price_control_v1",
                        "dealer_assumption": "none", "raw_payload_reference": None,
                        "control_type": control_type,
                        "metadata_json": json.dumps({"control_type": control_type}, sort_keys=True),
                    })
        return pd.DataFrame(rows) if rows else _empty_frame(GEX_LEVEL_COLUMNS + ["control_type"])

    def _replay(self, underlying: pd.DataFrame, levels: pd.DataFrame, *, strategy_type: str) -> pd.DataFrame:
        if underlying.empty or levels.empty:
            return _empty_frame(REPLAY_COLUMNS)
        rows: list[dict[str, Any]] = []
        bars_by_symbol = self._bars_by_symbol(underlying)
        level_frame = levels.copy()
        level_frame["known_at_dt"] = pd.to_datetime(level_frame["known_at_utc"], utc=True, errors="coerce")
        seen: set[tuple[str, str, str, str, float, str]] = set()
        for symbol, bars in bars_by_symbol.items():
            symbol_levels = level_frame[level_frame["symbol"] == symbol].copy().sort_values("known_at_dt")
            if symbol_levels.empty or len(bars) < 3:
                continue
            snapshots = [
                (timestamp, group.drop(columns=["known_at_dt"]).copy())
                for timestamp, group in symbol_levels.groupby("known_at_dt", sort=True, dropna=True)
            ]
            if not snapshots:
                continue
            first_known = snapshots[0][0]
            snapshot_index = -1
            for index in range(1, len(bars)):
                previous_bar, confirmation_bar = bars[index - 1], bars[index]
                cutoff = confirmation_bar.bar_start_utc
                cutoff_ts = pd.Timestamp(cutoff)
                if pd.notna(first_known) and cutoff_ts <= first_known:
                    continue
                while snapshot_index + 1 < len(snapshots) and snapshots[snapshot_index + 1][0] < cutoff_ts:
                    snapshot_index += 1
                if snapshot_index < 0:
                    continue
                snapshot_levels = snapshots[snapshot_index][1].copy()
                if snapshot_levels.empty:
                    continue
                snapshot_levels["_distance"] = (
                    pd.to_numeric(snapshot_levels["price"], errors="coerce") - confirmation_bar.close
                ).abs()
                local_levels = snapshot_levels.nsmallest(25, "_distance")
                target_nodes = sorted({float(value) for value in pd.to_numeric(snapshot_levels["price"], errors="coerce").dropna()})
                for level_row in local_levels.to_dict("records"):
                    level = self._level_from_row(level_row)
                    scan = self._scan_from_history(previous_bar, confirmation_bar, level, target_nodes, level_row)
                    setup = self.detector.detect(scan, at=confirmation_bar.bar_end_utc)
                    if not setup or not setup.trade_plan:
                        continue
                    key = (symbol, confirmation_bar.bar_end_utc.isoformat(), setup.side.value,
                           level.level_type, round(level.price, 4), str(level_row.get("control_type") or "options"))
                    if key in seen:
                        continue
                    seen.add(key)
                    after = bars[index + 1:index + 90]
                    for slippage_bps in (0, 1, 3, 5):
                        for management_version in self._management_versions(strategy_type):
                            rows.append(self._simulate(setup, level_row, after, management_version, slippage_bps, strategy_type))
                    break
        return pd.DataFrame(rows) if rows else _empty_frame(REPLAY_COLUMNS)

    def _management_versions(self, strategy_type: str) -> list[str]:
        versions = ["TM_V0_CURRENT", "TM_V3_TP1_PLUS_RUNNER"]
        if strategy_type == "OPTIONS_STRUCTURE_RECON":
            versions.extend([
                "FIXED_EXIT_0_5R", "FIXED_EXIT_1R",
                "HALF_0_5R_REST_RUNNER", "HALF_0_5R_HALF_1R",
            ])
        return versions

    def _bars_by_symbol(self, underlying: pd.DataFrame) -> dict[str, list[Bar]]:
        result: dict[str, list[Bar]] = {}
        for symbol, group in underlying.groupby("symbol"):
            bars: list[Bar] = []
            for row in group.sort_values("bar_end_utc").to_dict("records"):
                start = _parse_dt(row.get("bar_start_utc"))
                end = _parse_dt(row.get("bar_end_utc"))
                if not start or not end:
                    continue
                bars.append(Bar(
                    ticker=symbol, timeframe="5m", bar_start_utc=start, bar_end_utc=end,
                    open=float(row["open"]), high=float(row["high"]), low=float(row["low"]),
                    close=float(row["close"]), volume=float(row.get("volume") or 0),
                    atr=max(float(row.get("atr") or max(abs(row["close"]) * 0.005, 0.25)), 0.01),
                    relative_volume=float(row.get("relative_volume") or 1.0),
                    source=str(row.get("provider") or "historical"),
                    source_timestamp_utc=end, source_freshness_seconds=0,
                    confidence_score=0.6 if row.get("dataset_source") == "YFINANCE_RECENT_UNDERLYING" else 0.75,
                    raw_payload_reference=row.get("raw_payload_reference"),
                ))
            result[str(symbol).upper()] = bars
        return result

    def _level_from_row(self, row: dict[str, Any]) -> Level:
        known = _parse_dt(row.get("known_at_utc")) or _now_utc()
        return Level(
            ticker=str(row.get("symbol")).upper(),
            level_type=str(row.get("level_type") or "GEX_NODE"),
            price=float(row.get("price")),
            zone_low=float(row.get("zone_low")),
            zone_high=float(row.get("zone_high")),
            known_at_utc=known,
            source=str(row.get("provider") or "historical"),
            strength_score=float(row.get("strength_score") or 0.7),
            metadata={"historical_data_tier": row.get("historical_data_tier"),
                      "source_quality": row.get("source_quality"),
                      "control_type": row.get("control_type")},
        )

    def _scan_from_history(self, previous_bar: Bar, confirmation_bar: Bar, level: Level,
                           target_nodes: list[float], level_row: dict[str, Any]) -> ScanInput:
        long_pattern = min(previous_bar.low, confirmation_bar.low) < level.zone_low and confirmation_bar.close > level.zone_high
        short_pattern = max(previous_bar.high, confirmation_bar.high) > level.zone_high and confirmation_bar.close < level.zone_low
        direction = "bullish" if long_pattern else "bearish" if short_pattern else "unknown"
        historical_tier = str(level_row.get("historical_data_tier") or "TIER_H3_PARTIAL_CHAIN")
        is_price_control = historical_tier == "TIER_H4_PRICE_ONLY_CONTROL"
        confidence = 0.35 if is_price_control else 0.55
        state = TickerState(
            ticker=confirmation_bar.ticker, timestamp_utc=confirmation_bar.bar_end_utc,
            source=str(level_row.get("provider") or "historical"),
            spot_price=confirmation_bar.close,
            bid=confirmation_bar.close - max(confirmation_bar.close * 0.0001, 0.01),
            ask=confirmation_bar.close + max(confirmation_bar.close * 0.0001, 0.01),
            last=confirmation_bar.close, spread_bps=2.0,
            volume_today=confirmation_bar.volume, relative_volume=confirmation_bar.relative_volume,
            source_freshness_seconds=0, confidence_score=confidence,
        )
        guard = GuardStatus(
            ticker=confirmation_bar.ticker, evaluated_at_utc=confirmation_bar.bar_end_utc,
            blocked=False, macro_unknown=True, calendar_approved=False,
        )
        features = FeatureSet(
            dealer_positioning=None if is_price_control else max(0.65, min(0.95, level.strength_score)),
            options_flow=None,
            oi_confirmation=None,
            big_trades_dark_pool=None,
            price_structure=1.0 if direction != "unknown" else 0.4,
            volatility_liquidity=min(1.0, 0.45 + min(2.0, confirmation_bar.relative_volume) * 0.2),
            data_quality_event_guard=0.25,
            flow_direction=direction,
            volume_expansion=confirmation_bar.relative_volume >= 1.25,
            raw={
                "historical_reconstruction": True,
                "historical_data_tier": historical_tier,
                "source_quality": level_row.get("source_quality"),
                "gamma_regime": "UNKNOWN",
                "lookahead_risk": bool(level_row.get("lookahead_risk")),
                "control_type": level_row.get("control_type"),
            },
        )
        eligibility = EligibilityContext(
            real_data=True, synthetic_present=False, supported_ticker=True, session_valid=True,
            free_validation_session_valid=True, session_name="historical_regular",
            macro_guard_evaluated=True, required_fields_complete=False, core_fields_complete=True,
            price_provider=confirmation_bar.source, structure_provider=level.source,
            price_provider_production_eligible=False, structure_provider_production_eligible=False,
            price_provider_free_validation_eligible=True, structure_provider_free_validation_eligible=not is_price_control,
            price_freshness_seconds=0, structure_freshness_seconds=0,
            macro_calendar_production_eligible=False, limited_data=True,
            unofficial_source=confirmation_bar.source == "yfinance", production_grade=False,
            gamma_grid_missing=True, oi_unavailable=True, greeks_unavailable=True,
            confidence_penalty_applied=True, macro_unknown=True,
            missing_components=["historical_macro_calendar_unapproved", "historical_options_flow_unavailable"]
            + (["historical_option_chain_unavailable"] if is_price_control else ["full_historical_chain_unavailable"]),
            confidence_score=confidence,
        )
        return ScanInput(
            ticker_state=state, level=level, previous_bar=previous_bar,
            confirmation_bar=confirmation_bar, features=features, target_nodes=target_nodes,
            guard=guard, source_mode="HISTORICAL_RECONSTRUCTION", eligibility=eligibility,
        )

    def _simulate(self, setup: SetupEvent, level_row: dict[str, Any], bars: list[Bar],
                  management_version: str, slippage_bps: int, strategy_type: str) -> dict[str, Any]:
        side_mult = 1 if setup.side.value == "LONG" else -1
        plan = setup.trade_plan
        assert plan is not None
        entry = plan.planned_entry + (plan.planned_entry * slippage_bps / 10000 * side_mult)
        stop = plan.stop_initial
        risk = abs(entry - stop)
        setup_id = "hsetup_" + _stable_id(
            setup.ticker, setup.created_at_utc.isoformat(), setup.side.value,
            level_row.get("level_type"), level_row.get("price"), management_version, slippage_bps,
            level_row.get("control_type") or "options",
        )
        if risk <= 0 or not bars:
            return self._trade_row(setup_id, setup, level_row, management_version, slippage_bps, entry, stop,
                                   "expired", "invalid_or_no_future_bars", 0.0, 0.0, 0.0, None, strategy_type)
        status = "pending"
        opened_at = None
        closed_at = None
        bars_pending = 0
        stop_current = stop
        remaining = 1.0
        realized = 0.0
        mfe = 0.0
        mae = 0.0
        last_close = entry
        exit_reason = None
        targets_hit: set[str] = set()
        for bar in bars:
            last_close = bar.close
            if status == "pending":
                bars_pending += 1
                if bar.low <= plan.entry_zone_high and bar.high >= plan.entry_zone_low:
                    status = "open"
                    opened_at = bar.bar_end_utc
                elif bars_pending >= int(self.settings.get("execution.pending_order_expiry_bars", 3)):
                    return self._trade_row(setup_id, setup, level_row, management_version, slippage_bps, entry, stop,
                                           "expired", "pending_order_expiry", 0.0, 0.0, 0.0,
                                           bar.bar_end_utc, strategy_type)
                else:
                    continue
            if status not in {"open", "partial"}:
                continue
            favorable = (bar.high - entry) / risk if side_mult == 1 else (entry - bar.low) / risk
            adverse = (entry - bar.low) / risk if side_mult == 1 else (bar.high - entry) / risk
            mfe = max(mfe, favorable)
            mae = max(mae, adverse)
            stop_hit = bar.low <= stop_current if side_mult == 1 else bar.high >= stop_current
            if stop_hit:
                realized += ((stop_current - entry) * side_mult / risk) * remaining
                closed_at = bar.bar_end_utc
                exit_reason = "breakeven_stop" if abs(stop_current - entry) <= 0.01 else "stop_loss"
                return self._trade_row(setup_id, setup, level_row, management_version, slippage_bps, entry, stop,
                                       "closed", exit_reason, realized, mfe, mae, closed_at, strategy_type,
                                       opened_at=opened_at)
            for target_price, fraction, label in self._target_spec(management_version, setup.side.value, entry, risk, plan.targets):
                if label in targets_hit or remaining <= 0:
                    continue
                hit = bar.high >= target_price if side_mult == 1 else bar.low <= target_price
                if not hit:
                    continue
                close_fraction = min(remaining, fraction)
                realized += ((target_price - entry) * side_mult / risk) * close_fraction
                remaining = round(remaining - close_fraction, 8)
                targets_hit.add(label)
                if label in {"TP1_PARTIAL", "FIXED_0_5R", "HALF_0_5R"}:
                    stop_current = entry
                if remaining <= 0:
                    closed_at = bar.bar_end_utc
                    return self._trade_row(setup_id, setup, level_row, management_version, slippage_bps, entry, stop,
                                           "closed", label.lower(), realized, mfe, mae, closed_at, strategy_type,
                                           opened_at=opened_at)
                status = "partial"
        if status == "pending":
            return self._trade_row(setup_id, setup, level_row, management_version, slippage_bps, entry, stop,
                                   "expired", "no_fill_before_data_end", 0.0, mfe, mae, None, strategy_type)
        close_r = ((last_close - entry) * side_mult / risk) * remaining
        realized += close_r
        closed_at = bars[-1].bar_end_utc
        return self._trade_row(setup_id, setup, level_row, management_version, slippage_bps, entry, stop,
                               "censored", "rth_close_or_data_end", realized, mfe, mae, closed_at,
                               strategy_type, opened_at=opened_at)

    def _target_spec(self, management_version: str, side: str, entry: float,
                     risk: float, plan_targets: list[float]) -> list[tuple[float, float, str]]:
        side_mult = 1 if side == "LONG" else -1
        tp1 = plan_targets[0] if plan_targets else entry + side_mult * risk
        tp3 = plan_targets[2] if len(plan_targets) > 2 else entry + side_mult * 3 * risk
        if management_version == "TM_V3_TP1_PLUS_RUNNER":
            return [(tp1, 0.50, "TP1_PARTIAL"), (tp3, 0.50, "RUNNER_EXIT")]
        if management_version == "FIXED_EXIT_0_5R":
            return [(entry + side_mult * 0.5 * risk, 1.0, "FIXED_0_5R")]
        if management_version == "FIXED_EXIT_1R":
            return [(entry + side_mult * 1.0 * risk, 1.0, "FIXED_1R")]
        if management_version == "HALF_0_5R_REST_RUNNER":
            return [(entry + side_mult * 0.5 * risk, 0.50, "HALF_0_5R"), (tp3, 0.50, "RUNNER_EXIT")]
        if management_version == "HALF_0_5R_HALF_1R":
            return [(entry + side_mult * 0.5 * risk, 0.50, "HALF_0_5R"),
                    (entry + side_mult * 1.0 * risk, 0.50, "HALF_1R")]
        fraction = float((self.settings.get("targets.partials", [.33]) or [.33])[0])
        return [(tp1, fraction, "TP1_PARTIAL")]

    def _trade_row(self, setup_id: str, setup: SetupEvent, level_row: dict[str, Any],
                   management_version: str, slippage_bps: int, entry: float, stop: float,
                   status: str, exit_reason: str, realized: float, mfe: float, mae: float,
                   closed_at: datetime | None, strategy_type: str,
                   opened_at: datetime | None = None) -> dict[str, Any]:
        plan = setup.trade_plan
        assert plan is not None
        opened_at = opened_at or setup.created_at_utc
        duration = round((closed_at - opened_at).total_seconds() / 60, 2) if closed_at else None
        return {
            "historical_setup_id": setup_id,
            "symbol": setup.ticker,
            "session_date": _session_date(setup.created_at_utc),
            "entry_timestamp": opened_at.isoformat() if opened_at else None,
            "closed_at_utc": closed_at.isoformat() if closed_at else None,
            "setup_type": setup.setup_type.value,
            "direction": setup.side.value,
            "strategy_type": strategy_type,
            "control_type": level_row.get("control_type") or "OPTIONS_STRUCTURE_RECON",
            "level_type": level_row.get("level_type"),
            "historical_data_tier": level_row.get("historical_data_tier"),
            "source_quality": level_row.get("source_quality"),
            "provider": level_row.get("provider"),
            "lookahead_risk": bool(level_row.get("lookahead_risk")),
            "management_version": management_version,
            "slippage_variant": f"SLIPPAGE_{slippage_bps}BP",
            "slippage_bps": slippage_bps,
            "entry": round(entry, 6),
            "stop": round(stop, 6),
            "tp1": plan.targets[0] if len(plan.targets) > 0 else None,
            "tp2": plan.targets[1] if len(plan.targets) > 1 else None,
            "tp3": plan.targets[2] if len(plan.targets) > 2 else None,
            "status": status,
            "exit_reason": exit_reason,
            "realized_R": round(realized, 6),
            "MFE_R": round(mfe, 6),
            "MAE_R": round(mae, 6),
            "duration_minutes": duration,
            "score": setup.score.total,
            "rr": plan.primary_rr,
            "gamma_regime": (setup.signal_snapshot.get("features") or {}).get("raw", {}).get("gamma_regime", "UNKNOWN"),
            "dealer_assumption": level_row.get("dealer_assumption"),
            "replay_engine_version": REPLAY_ENGINE_VERSION,
        }

    def _group_results(self, trades: pd.DataFrame, dimension: str) -> pd.DataFrame:
        subset = self._default_eval_subset(trades)
        if subset.empty or dimension not in subset.columns:
            return _empty_frame(["bucket", *RESULT_COLUMNS[1:]])
        rows = []
        for bucket, group in subset.groupby(dimension, dropna=False):
            rows.append({"bucket": "UNKNOWN" if pd.isna(bucket) else str(bucket), **self._stats(group)})
        return pd.DataFrame(rows).sort_values("bucket")

    def _management_results(self, trades: pd.DataFrame) -> pd.DataFrame:
        if trades.empty:
            return _empty_frame(["bucket", *RESULT_COLUMNS[1:]])
        subset = trades[
            (trades["strategy_type"] == "OPTIONS_STRUCTURE_RECON") &
            (trades["slippage_bps"] == 3)
        ].copy()
        subset = subset[pd.to_numeric(subset["realized_R"], errors="coerce").notna()]
        if subset.empty:
            return _empty_frame(["bucket", *RESULT_COLUMNS[1:]])
        rows = []
        for management_version, group in subset.groupby("management_version", dropna=False):
            rows.append({"bucket": str(management_version), **self._stats(group)})
        return pd.DataFrame(rows).sort_values("bucket")

    def _default_eval_subset(self, trades: pd.DataFrame) -> pd.DataFrame:
        if trades.empty:
            return _empty_frame(REPLAY_COLUMNS)
        frame = trades[
            (trades["management_version"] == "TM_V0_CURRENT") &
            (trades["slippage_bps"] == 3)
        ].copy()
        frame = frame[pd.to_numeric(frame["realized_R"], errors="coerce").notna()]
        return frame

    def _stats(self, frame: pd.DataFrame) -> dict[str, Any]:
        if frame.empty:
            return {key: 0 if key in {"N", "unique_days"} else None for key in RESULT_COLUMNS[1:]}
        values = pd.to_numeric(frame["realized_R"], errors="coerce").dropna()
        if values.empty:
            return {key: 0 if key in {"N", "unique_days"} else None for key in RESULT_COLUMNS[1:]}
        wins = values[values > 0]
        losses = values[values < 0]
        gross_win = float(wins.sum())
        gross_loss = float(losses.sum())
        day_totals = frame.assign(_r=pd.to_numeric(frame["realized_R"], errors="coerce")).groupby("session_date")["_r"].sum()
        cumulative = values.cumsum()
        running_max = cumulative.cummax()
        max_dd = float((running_max - cumulative).max()) if not cumulative.empty else 0.0
        best_day = str(day_totals.idxmax()) if not day_totals.empty else None
        worst_day = str(day_totals.idxmin()) if not day_totals.empty else None
        best_day_r = float(day_totals.max()) if not day_totals.empty else 0.0
        reduced = frame[frame["session_date"] != best_day] if best_day else frame
        reduced_values = pd.to_numeric(reduced["realized_R"], errors="coerce").dropna()
        ci = self._day_bootstrap(frame)
        return {
            "N": int(len(values)),
            "unique_days": int(frame["session_date"].nunique()) if "session_date" in frame else 0,
            "expectancy": round(float(values.mean()), 4),
            "profit_factor": round(gross_win / abs(gross_loss), 4) if gross_loss else ("infinite" if gross_win > 0 else None),
            "win_rate": round(float((values > 0).mean()), 4),
            "median_R": round(float(values.median()), 4),
            "average_winner": round(float(wins.mean()), 4) if not wins.empty else 0.0,
            "average_loser": round(float(losses.mean()), 4) if not losses.empty else 0.0,
            "MFE": round(float(pd.to_numeric(frame.get("MFE_R"), errors="coerce").mean()), 4)
            if "MFE_R" in frame else None,
            "MAE": round(float(pd.to_numeric(frame.get("MAE_R"), errors="coerce").mean()), 4)
            if "MAE_R" in frame else None,
            "max_drawdown": round(max_dd, 4),
            "positive_day_pct": round(float((day_totals > 0).mean()), 4) if not day_totals.empty else None,
            "best_day": best_day,
            "best_day_R": round(best_day_r, 4),
            "best_day_contribution": round(best_day_r / max(abs(float(values.sum())), 1e-9), 4),
            "worst_day": worst_day,
            "worst_day_R": round(float(day_totals.min()), 4) if not day_totals.empty else 0.0,
            "remove_best_day_expectancy": round(float(reduced_values.mean()), 4) if not reduced_values.empty else None,
            "bootstrap_ci_low": ci.get("low"),
            "bootstrap_ci_high": ci.get("high"),
        }

    def _day_bootstrap(self, frame: pd.DataFrame, iterations: int = 500) -> dict[str, Any]:
        if frame.empty or "session_date" not in frame:
            return {"low": None, "high": None}
        daily = [group for _, group in frame.groupby("session_date")]
        if not daily:
            return {"low": None, "high": None}
        rng = random.Random(20260904)
        means = []
        for _ in range(iterations):
            sample = [daily[rng.randrange(len(daily))] for _ in daily]
            values = pd.concat(sample)["realized_R"].astype(float)
            means.append(float(values.mean()) if not values.empty else 0.0)
        means.sort()
        return {"low": round(means[int(0.025 * (len(means) - 1))], 4),
                "high": round(means[int(0.975 * (len(means) - 1))], 4)}

    def _holdout_results(self, trades: pd.DataFrame) -> pd.DataFrame:
        subset = self._default_eval_subset(trades)
        if subset.empty:
            return _empty_frame(["bucket", *RESULT_COLUMNS[1:]])
        dates = sorted(subset["session_date"].dropna().unique())
        if len(dates) < 2:
            return pd.DataFrame([{"bucket": "INSUFFICIENT_DAYS_FOR_WALK_FORWARD", **self._stats(subset)}])
        split_index = max(1, int(len(dates) * 0.65))
        discovery_dates = set(dates[:split_index])
        holdout_dates = set(dates[split_index:])
        rows = [
            {"bucket": "DISCOVERY", **self._stats(subset[subset["session_date"].isin(discovery_dates)])},
            {"bucket": "HOLDOUT", **self._stats(subset[subset["session_date"].isin(holdout_dates)])},
        ]
        return pd.DataFrame(rows)

    def _control_comparison(self, trades: pd.DataFrame) -> pd.DataFrame:
        subset = self._default_eval_subset(trades)
        if subset.empty:
            return pd.DataFrame(columns=["strategy_type", "control_type", *RESULT_COLUMNS[1:]])
        rows = []
        for (strategy_type, control_type), group in subset.groupby(["strategy_type", "control_type"], dropna=False):
            rows.append({"strategy_type": strategy_type, "control_type": control_type, **self._stats(group)})
        return pd.DataFrame(rows).sort_values(["strategy_type", "control_type"])

    def _live_validation(self, replay: pd.DataFrame) -> dict[str, Any]:
        live = [row for row in self.repository.list_json("setup_events", limit=250000)
                if str(row.get("source_mode", "")).startswith("REAL_")]
        options = replay[
            (replay.get("strategy_type") == "OPTIONS_STRUCTURE_RECON") &
            (replay.get("management_version") == "TM_V0_CURRENT") &
            (replay.get("slippage_bps") == 3)
        ].copy() if not replay.empty else pd.DataFrame()
        if not live:
            return {"live_setup_count": 0, "matched_setups": 0, "setup_match_rate": None,
                    "level_deviation_median": None, "entry_timing_deviation_median_minutes": None,
                    "trust_assessment": "NO_LIVE_RECORDS_TO_COMPARE"}
        matched = 0
        level_deviations = []
        timing_deviations = []
        for setup in live:
            created = _parse_dt(setup.get("created_at_utc"))
            if not created or options.empty:
                continue
            day = _session_date(created)
            candidates = options[
                (options["symbol"] == setup.get("ticker")) &
                (options["direction"] == setup.get("side")) &
                (options["session_date"] == day)
            ].copy()
            if candidates.empty:
                continue
            candidates["_entry_dt"] = pd.to_datetime(candidates["entry_timestamp"], utc=True, errors="coerce")
            candidates["_delta"] = (candidates["_entry_dt"] - pd.Timestamp(created)).abs().dt.total_seconds() / 60
            best = candidates.sort_values("_delta").head(1)
            if best.empty or float(best["_delta"].iloc[0]) > 15:
                continue
            matched += 1
            live_level = ((setup.get("signal_snapshot") or {}).get("level") or {}).get("price")
            replay_level = _safe_float(best["entry"].iloc[0])
            if live_level is not None and replay_level is not None:
                level_deviations.append(abs(float(live_level) - float(replay_level)))
            timing_deviations.append(float(best["_delta"].iloc[0]))
        return {
            "live_setup_count": len(live),
            "matched_setups": matched,
            "setup_match_rate": round(matched / len(live), 4) if live else None,
            "level_deviation_median": round(float(pd.Series(level_deviations).median()), 4) if level_deviations else None,
            "entry_timing_deviation_median_minutes": round(float(pd.Series(timing_deviations).median()), 2) if timing_deviations else None,
            "trust_assessment": "LOCAL_ARCHIVE_VALIDATION_ONLY" if matched else "NO_RELIABLE_HISTORICAL_REPRODUCTION_YET",
        }

    def _summary(self, *, started: datetime, symbols: list[str], probes: dict[str, Any],
                 option_chains: pd.DataFrame, underlying: pd.DataFrame, gex_levels: pd.DataFrame,
                 replay: pd.DataFrame, validation: dict[str, Any], artifacts: list[Artifact]) -> dict[str, Any]:
        options_replay = replay[replay["strategy_type"] == "OPTIONS_STRUCTURE_RECON"] if not replay.empty else pd.DataFrame()
        control_replay = replay[replay["strategy_type"] == "PRICE_CONTROL"] if not replay.empty else pd.DataFrame()
        default_options = self._default_eval_subset(options_replay)
        default_controls = self._default_eval_subset(control_replay)
        unique_days = int(underlying["bar_end_utc"].str.slice(0, 10).nunique()) if not underlying.empty else 0
        if len(option_chains) > 0 and unique_days >= 20 and len(options_replay) > 0:
            status = "BEST_CASE"
        elif len(options_replay) > 0 or len(default_controls) > 0 or len(underlying) > 0:
            status = "PARTIAL_SUCCESS"
        else:
            status = "FAILURE"
        report = {
            "status": status,
            "generated_at_utc": _now_utc().isoformat(),
            "symbols_requested": symbols,
            "historical_option_chain_rows": int(len(option_chains)),
            "historical_underlying_5m_rows": int(len(underlying)),
            "historical_gex_level_rows": int(len(gex_levels)),
            "historical_replay_rows": int(len(replay)),
            "options_structure_replay_rows": int(len(options_replay)),
            "price_control_replay_rows": int(len(control_replay)),
            "underlying_unique_symbols": int(underlying["symbol"].nunique()) if not underlying.empty else 0,
            "underlying_unique_days": unique_days,
            "default_options_stats": self._stats(default_options),
            "default_control_stats": self._stats(default_controls),
            "live_validation": validation,
            "no_live_strategy_changes": True,
            "live_trading_enabled": False,
        }
        manifest = {
            "schema_version": "historical_data_manifest.v1",
            "created_at_utc": report["generated_at_utc"],
            "started_at_utc": started.isoformat(),
            "parser_version": PARSER_VERSION,
            "normalization_version": NORMALIZATION_VERSION,
            "greeks_model_version": GREEKS_MODEL_VERSION,
            "gex_model_version": GEX_MODEL_VERSION,
            "replay_engine_version": REPLAY_ENGINE_VERSION,
            "historical_data_tiers": HISTORICAL_DATA_TIERS,
            "source_probes": probes,
            "artifacts": [
                {
                    "name": artifact.name,
                    "path": str(artifact.path),
                    "rows": artifact.rows,
                    "source": artifact.source,
                    "downloaded_at_utc": artifact.downloaded_at_utc,
                    "checksum_sha256": artifact.checksum_sha256,
                    "parser_version": artifact.parser_version,
                    "normalization_version": artifact.normalization_version,
                }
                for artifact in artifacts
            ],
            "limitations": [
                "No free/no-signup source returned timestamp-correct historical US option-chain snapshots.",
                "Alpha Vantage HISTORICAL_OPTIONS was probed with the configured key and did not return chain rows.",
                "Finnhub option-chain endpoint returned auth/entitlement failure for the configured key.",
                "Yahoo/yfinance is usable for recent underlying 5m candles and current chains, not historical chain snapshots.",
                "Local live archive covers only dates already collected by the daemon and is not a full historical OPRA replay.",
            ],
        }
        return {"report": report, "manifest": manifest}

    def _source_matrix_markdown(self, probes: dict[str, Any]) -> str:
        rows = "\n".join(
            "| {source_name} | {cost} | {account_required} | {api_key_required} | {historical_depth} | "
            "{option_chain_available} | {oi_available} | {iv_available} | {greeks_available} | "
            "{bid_ask_available} | {trade_volume_available} | {intraday_timestamps} | {eod_only} | "
            "{suitability_score} | {url} |".format(**item)
            for item in SOURCE_MATRIX
        )
        probe_json = json.dumps({
            "yfinance": probes.get("yfinance"),
            "alpha_vantage": probes.get("alpha_vantage"),
            "finnhub": probes.get("finnhub"),
        }, indent=2, sort_keys=True)
        return f"""# Historical Options Source Matrix

Generated: {_now_utc().isoformat()}

This matrix is for Phase 3B historical reconstruction only. It does not authorize paid signups, purchases, live trading, or changes to the running daemon.

## Source matrix

| source | free/trial/paid | account required | API key required | historical depth | option chain | OI | IV | Greeks | bid/ask | volume | intraday timestamps | EOD only | suitability | URL |
|---|---|---:|---:|---|---|---|---|---|---|---|---|---|---:|---|
{rows}

## Local entitlement probes

The probes below intentionally omit API keys and raw payload bodies.

```json
{probe_json}
```

## Current conclusion

No currently configured free/no-signup source produced historical option-chain/OI/IV/Greeks rows suitable for a strict H1/H2 GEX reconstruction. The pipeline therefore keeps historical option chains empty unless a valid entitled source is added, uses yfinance only for recent underlying 5m candles, uses the local live archive only as H3 partial structure validation, and produces H4 price-only controls.
"""

    def _report_markdown(self, summary: dict[str, Any], validation: dict[str, Any]) -> str:
        report = summary["report"]
        manifest = summary["manifest"]
        artifacts = "\n".join(
            f"- `{Path(item['path']).name}`: {item['rows']} rows, sha256 `{item['checksum_sha256']}`"
            for item in manifest["artifacts"]
        ) or "- none"
        tiers = "\n".join(f"- `{name}`: {description}" for name, description in HISTORICAL_DATA_TIERS.items())
        limitations = "\n".join(f"- {item}" for item in manifest["limitations"])
        return f"""# Phase 3B Historical Options Reconstruction

Generated: {report['generated_at_utc']}

Status: **{report['status']}**

No live/paper strategy behavior was changed. The live daemon, forward cohorts, Production gates, no-live-trading rule, and Portfolio OS isolation remain separate from this historical research pipeline.

## Data quality tiers

{tiers}

## Data collected

- Symbols requested: {', '.join(report['symbols_requested'])}
- Historical option-chain rows: {report['historical_option_chain_rows']}
- Historical GEX/level rows: {report['historical_gex_level_rows']}
- Historical underlying 5m rows: {report['historical_underlying_5m_rows']}
- Underlying symbols represented: {report['underlying_unique_symbols']}
- Underlying calendar days represented: {report['underlying_unique_days']}
- Options-structure replay rows: {report['options_structure_replay_rows']}
- Price-control replay rows: {report['price_control_replay_rows']}

## Default evaluation slice

Default slice: `TM_V0_CURRENT`, `SLIPPAGE_3BP`.

Options-structure reconstruction stats:

```json
{json.dumps(report['default_options_stats'], indent=2)}
```

Price-control stats:

```json
{json.dumps(report['default_control_stats'], indent=2)}
```

## Live-record validation

```json
{json.dumps(validation, indent=2)}
```

Interpretation: if local reconstruction does not match the daemon's live records well, older reconstructed backtest results should not be trusted. At this stage the reliable historical structure source is only the local live archive, so the result is partial by design.

## Source probe conclusion

- yfinance/Yahoo: recent 5m underlying candles and current option chains only; no historical chain snapshots.
- Alpha Vantage: `HISTORICAL_OPTIONS` endpoint exists in docs, but configured free key did not return chain rows.
- Finnhub: configured key did not authorize option-chain endpoint in probe.
- Cboe/OCC/NYSE public pages provide useful volume/OI context but not free full historical chain snapshots with bid/ask, IV, OI, and Greeks.

## Controls

Controls are written to `historical_control_comparison.csv` and use no option-derived levels:

- price-only prior range midpoint
- random nearby price level
- previous-day high
- previous-day low

These controls are H4 and are not mixed with option-derived H3 results.

## Limitations

{limitations}

## Artifacts

{artifacts}

## Acceptance classification

Phase 3B is currently **{report['status']}**:

- Best case is not met because no configured free source returned 20+ trading days of historical option-chain/OI data.
- Partial success is met if generated H4 controls, local H3 archive levels, manifest, source matrix, and replay outputs exist.
- Failure would be declared only if no usable underlying/control/local archive data could be produced.
"""

    def _write_raw_json(self, name: str, payload: dict[str, Any]) -> Path:
        path = self.raw_root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, default=_json_default), encoding="utf-8")
        return path
