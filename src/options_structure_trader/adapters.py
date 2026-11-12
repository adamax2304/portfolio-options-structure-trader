from __future__ import annotations

import csv
import json
import math
import os
import sqlite3
import threading
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import yfinance as yf
import yaml

from .models import Bar, GexMap, MacroEvent, TickerState, utc_now


class AdapterError(RuntimeError):
    pass


class DataSourceAdapter(ABC):
    name = "base"
    capabilities: list[str] = []
    latency_type = "unknown"
    requires_api_key = False
    cost_tier = "free"
    license_notes = ""

    def __init__(self) -> None:
        self.last_success_utc: datetime | None = None
        self.last_error: str | None = None

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name, "capabilities": self.capabilities, "latency_type": self.latency_type,
            "requires_api_key": self.requires_api_key, "cost_tier": self.cost_tier,
            "configured": self.configured, "last_success_utc": self.last_success_utc,
            "last_error": self.last_error, "license_notes": self.license_notes,
        }

    @property
    def configured(self) -> bool:
        return True

    @abstractmethod
    def fetch(self, request: dict[str, Any]) -> Any: ...

    @abstractmethod
    def normalize(self, raw_payload: Any) -> Any: ...


class AlgoXAdapter(DataSourceAdapter):
    name = "algox"
    capabilities = ["gex_by_strike", "gamma_flip", "call_wall", "put_wall", "max_pain", "expected_move", "atm_iv"]
    latency_type = "delayed"
    license_notes = "CC BY 4.0; attribution required. Cache locally and treat levels as zones."

    def __init__(self, base_url: str = "https://algoxflow.com", timeout: float = 12.0):
        super().__init__()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.cache_seconds = 900
        self._cache: dict[str, tuple[datetime, dict[str, Any]]] = {}

    def fetch(self, request: dict[str, Any]) -> dict[str, Any]:
        ticker = request["ticker"].upper()
        cached = self._cache.get(ticker)
        if cached and (utc_now() - cached[0]).total_seconds() < self.cache_seconds:
            return cached[1]
        try:
            response = httpx.get(f"{self.base_url}/api/gexmap", params={"ticker": ticker}, timeout=self.timeout)
            response.raise_for_status()
            self.last_success_utc = utc_now()
            self.last_error = None
            payload = response.json()
            self._cache[ticker] = (self.last_success_utc, payload)
            return payload
        except Exception as exc:
            self.last_error = str(exc)
            raise AdapterError(f"AlgoX fetch failed for {ticker}: {exc}") from exc

    def normalize(self, raw: dict[str, Any]) -> GexMap:
        updated = raw.get("updated") or raw.get("as_of") or utc_now().isoformat()
        timestamp = datetime.fromisoformat(str(updated).replace("Z", "+00:00"))
        now = utc_now()
        strikes = [{"strike": float(row.get("k", row.get("strike"))),
                    "net_gex": float(row.get("g", row.get("net_gex_millions", 0)))}
                   for row in raw.get("strikes", []) if row.get("k", row.get("strike")) is not None]
        gamma = raw.get("gamma", {})
        expected = raw.get("expected_move", {})
        return GexMap(
            ticker=str(raw.get("ticker", "")).upper(), source=self.name,
            source_timestamp_utc=timestamp, ingestion_timestamp_utc=now,
            spot=float(raw.get("spot", 0)), gamma_flip=raw.get("flip", gamma.get("zero_gamma_flip")),
            call_wall=raw.get("callWall", gamma.get("call_wall")),
            put_wall=raw.get("putWall", gamma.get("put_wall")), max_pain=raw.get("maxPain", gamma.get("max_pain")),
            expected_move=raw.get("expMove", expected.get("points")), atm_iv=raw.get("atmIv", expected.get("atm_iv")),
            gamma_regime=raw.get("regime", gamma.get("regime", "unknown")), strikes=strikes,
            freshness_seconds=max(0, (now - timestamp).total_seconds()),
            confidence_score=.75,
            field_coverage={"gex": 1.0 if strikes else 0.0, "oi": 0.0, "iv": 1.0 if raw.get("atmIv") else 0.0,
                            "greeks": 0.0},
            missing_required_fields=["open_interest", "greeks"],
            free_validation_complete=bool(raw.get("spot") and strikes and
                                          (raw.get("callWall", gamma.get("call_wall")) is not None or
                                           raw.get("putWall", gamma.get("put_wall")) is not None)),
            required_fields_complete=False,
        )


class AlpacaMarketBarsAdapter(DataSourceAdapter):
    name = "alpaca"
    capabilities = ["ohlcv", "quotes", "snapshots"]
    latency_type = "realtime"
    requires_api_key = True
    cost_tier = "trial"
    license_notes = "Entitlements determine feed coverage and delay. This adapter never uses order endpoints."

    def __init__(self, feed: str = "iex"):
        super().__init__()
        self.key = os.getenv("ALPACA_API_KEY", "")
        self.secret = os.getenv("ALPACA_API_SECRET", "")
        self.feed = feed

    @property
    def configured(self) -> bool:
        return bool(self.key and self.secret)

    def fetch(self, request: dict[str, Any]) -> dict[str, Any]:
        if not self.configured:
            raise AdapterError("Alpaca credentials are not configured")
        ticker = request["ticker"].upper()
        params = {"symbols": ticker, "timeframe": request.get("timeframe", "5Min"),
                  "limit": request.get("limit", 100), "feed": self.feed, "sort": "asc"}
        headers = {"APCA-API-KEY-ID": self.key, "APCA-API-SECRET-KEY": self.secret}
        try:
            response = httpx.get("https://data.alpaca.markets/v2/stocks/bars", params=params, headers=headers, timeout=15)
            response.raise_for_status()
            quote = httpx.get("https://data.alpaca.markets/v2/stocks/quotes/latest",
                              params={"symbols": ticker, "feed": self.feed}, headers=headers, timeout=15)
            quote.raise_for_status()
            self.last_success_utc, self.last_error = utc_now(), None
            return {"ticker": ticker, "bars_payload": response.json(), "quotes_payload": quote.json()}
        except Exception as exc:
            self.last_error = str(exc)
            raise AdapterError(f"Alpaca fetch failed: {exc}") from exc

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        bars: list[Bar] = []
        now = utc_now()
        for ticker, rows in raw.get("bars_payload", {}).get("bars", {}).items():
            true_ranges: list[float] = []
            volumes = [float(item["v"]) for item in rows]
            for row in rows:
                close = float(row["c"])
                prior_close = bars[-1].close if bars and bars[-1].ticker == ticker else close
                tr = max(float(row["h"]) - float(row["l"]), abs(float(row["h"]) - prior_close),
                         abs(float(row["l"]) - prior_close))
                true_ranges.append(tr)
                timestamp = datetime.fromisoformat(row["t"].replace("Z", "+00:00"))
                end = timestamp + timedelta(minutes=5)
                if now < end:
                    continue
                baseline = sum(volumes[max(0, len(bars)-20):max(1, len(bars))]) / max(1, min(20, len(bars))) if bars else row["v"]
                bars.append(Bar(ticker=ticker, bar_start_utc=timestamp, bar_end_utc=end,
                                open=row["o"], high=row["h"], low=row["l"], close=close, volume=row["v"],
                                vwap=row.get("vw"), atr=max(sum(true_ranges[-14:]) / len(true_ranges[-14:]), 0.01),
                                relative_volume=float(row["v"]) / max(float(baseline), 1), closed=now >= end,
                                source=self.name, source_timestamp_utc=end,
                                source_freshness_seconds=max(0, (now - end).total_seconds()), confidence_score=.95))
        ticker = raw["ticker"]
        quote = raw.get("quotes_payload", {}).get("quotes", {}).get(ticker, {})
        quote_time = datetime.fromisoformat(quote["t"].replace("Z", "+00:00")) if quote.get("t") else (bars[-1].bar_end_utc if bars else now)
        last = bars[-1].close if bars else 0
        bid, ask = float(quote.get("bp") or 0), float(quote.get("ap") or 0)
        state = TickerState(ticker=ticker, timestamp_utc=quote_time, source=self.name, spot_price=last,
                            bid=bid, ask=ask, last=last, spread_bps=((ask-bid)/last*10_000) if last and ask >= bid else 0,
                            volume_today=sum(bar.volume for bar in bars[-78:]),
                            relative_volume=bars[-1].relative_volume if bars else 0,
                            average_daily_volume=0, trading_session="regular",
                            source_freshness_seconds=max(0, (now - quote_time).total_seconds()), confidence_score=.95)
        return {"bars": bars, "ticker_state": state,
                "core_fields_complete": bool(len(bars) >= 2 and last > 0),
                "required_fields_complete": bool(bars and bid > 0 and ask >= bid),
                "unofficial_source": False, "missing_fields": [] if bid > 0 and ask >= bid else ["bid", "ask"]}


class YFinanceMarketBarsAdapter(DataSourceAdapter):
    name = "yfinance"
    capabilities = ["ohlcv", "last_price", "volume"]
    latency_type = "unknown"
    cost_tier = "free"
    license_notes = "Unofficial Yahoo Finance wrapper with no SLA; collection/Shadow fallback by default."

    def __init__(self, cache_seconds: int = 60):
        super().__init__()
        self.cache_seconds = cache_seconds
        self._cache: dict[str, tuple[datetime, dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def fetch(self, request: dict[str, Any]) -> dict[str, Any]:
        ticker = request["ticker"].upper()
        requested_at = utc_now()
        with self._lock:
            cached = self._cache.get(ticker)
            if not request.get("force_refresh") and cached and (
                requested_at - cached[0]).total_seconds() < self.cache_seconds:
                return cached[1]
        try:
            instrument = yf.Ticker(ticker)
            interval = request.get("interval") or request.get("timeframe") or "5m"
            interval = "5m" if str(interval).lower() in {"5min", "5min", "5minute", "5minutes"} else str(interval)
            frame = instrument.history(period=request.get("period", "5d"), interval=interval,
                                       auto_adjust=False, prepost=False, actions=False)
            if frame.empty:
                raise AdapterError(f"No {interval} bars returned for {ticker}")
            rows = []
            for timestamp, row in frame.iterrows():
                rows.append({"t": pd.Timestamp(timestamp).isoformat(), "o": float(row["Open"]),
                             "h": float(row["High"]), "l": float(row["Low"]), "c": float(row["Close"]),
                             "v": float(row["Volume"])})
            fast = instrument.fast_info
            received_at = utc_now()
            payload = {"ticker": ticker, "bars": rows,
                       "last_price": float(fast["lastPrice"]), "last_volume": float(fast["lastVolume"]),
                       "average_volume": float(fast["threeMonthAverageVolume"]),
                       "requested_at_utc": requested_at.isoformat(), "received_at_utc": received_at.isoformat(),
                       "provider_latency_ms": int((received_at-requested_at).total_seconds()*1000),
                       "interval": interval, "provider": self.name, "official_source": False,
                       "provider_timestamp_utc": received_at.isoformat()}
            self.last_success_utc, self.last_error = received_at, None
            with self._lock:
                self._cache[ticker] = (self.last_success_utc, payload)
            return payload
        except Exception as exc:
            self.last_error = str(exc)
            raise AdapterError(f"yfinance fetch failed for {ticker}: {exc}") from exc

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        now, ticker = utc_now(), raw["ticker"]
        bars: list[Bar] = []
        true_ranges: list[float] = []
        prior_close: float | None = None
        session_volumes: list[float] = []
        current_date = None
        cumulative_volume = cumulative_value = 0.0
        for index, row in enumerate(raw["bars"]):
            start = datetime.fromisoformat(row["t"])
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            start = start.astimezone(timezone.utc)
            end = start + timedelta(minutes=5)
            if now < end:
                continue
            if start.date() != current_date:
                current_date, session_volumes, cumulative_volume, cumulative_value = start.date(), [], 0.0, 0.0
            tr = max(row["h"] - row["l"], abs(row["h"] - (prior_close or row["c"])),
                     abs(row["l"] - (prior_close or row["c"])))
            true_ranges.append(tr)
            baseline = sum(session_volumes[-20:]) / len(session_volumes[-20:]) if session_volumes else row["v"]
            session_volumes.append(row["v"])
            typical = (row["h"] + row["l"] + row["c"]) / 3
            cumulative_volume += row["v"]
            cumulative_value += typical * row["v"]
            bars.append(Bar(ticker=ticker, bar_start_utc=start, bar_end_utc=end, open=row["o"], high=row["h"],
                            low=row["l"], close=row["c"], volume=row["v"],
                            vwap=cumulative_value / max(cumulative_volume, 1),
                            atr=max(sum(true_ranges[-14:]) / len(true_ranges[-14:]), .01),
                            relative_volume=row["v"] / max(baseline, 1), closed=True, source=self.name,
                            source_timestamp_utc=end, source_freshness_seconds=max(0, (now-end).total_seconds()),
                            confidence_score=.45))
            prior_close = row["c"]
        if not bars:
            raise AdapterError(f"No completed 5m bars for {ticker}")
        latest = bars[-1]
        last = float(raw.get("last_price") or latest.close)
        state = TickerState(ticker=ticker, timestamp_utc=latest.bar_end_utc, source=self.name,
                            spot_price=last, bid=last, ask=last, last=last,
                            spread_bps=0, volume_today=float(raw.get("last_volume") or 0),
                            relative_volume=latest.relative_volume,
                            average_daily_volume=float(raw.get("average_volume") or 0),
                            trading_session="regular", source_freshness_seconds=latest.source_freshness_seconds,
                            confidence_score=.45)
        return {"bars": bars, "ticker_state": state, "core_fields_complete": len(bars) >= 2,
                "required_fields_complete": False, "unofficial_source": True,
                "missing_fields": ["bid", "ask", "authoritative_feed_latency"],
                "provider_timing": {
                    "requested_at": raw.get("requested_at_utc"), "received_at": raw.get("received_at_utc"),
                    "latest_bar_open_time": latest.bar_start_utc.isoformat(),
                    "latest_bar_close_time": latest.bar_end_utc.isoformat(),
                    "interval": raw.get("interval", "5m"),
                    "provider_latency_ms": raw.get("provider_latency_ms"),
                    "provider": self.name, "official_source": False,
                }}


class AlphaVantageMarketBarsAdapter(YFinanceMarketBarsAdapter):
    name = "alpha_vantage"
    capabilities = ["intraday_ohlcv"]
    latency_type = "feed-dependent"
    requires_api_key = True
    cost_tier = "free-key"
    license_notes = "Optional free-key backup. Rate limits and data recency depend on the account entitlement."

    def __init__(self, minimum_request_interval_seconds: int = 12):
        DataSourceAdapter.__init__(self)
        self.key = os.getenv("ALPHA_VANTAGE_API_KEY") or os.getenv("ALPHAVANTAGE_API_KEY", "")
        self.minimum_request_interval_seconds = minimum_request_interval_seconds
        self._last_request_utc: datetime | None = None
        self._lock = threading.Lock()
        self.rate_limit_responses = 0
        self.auth_errors = 0

    @property
    def configured(self) -> bool:
        return bool(self.key)

    def fetch(self, request: dict[str, Any]) -> dict[str, Any]:
        if not self.configured:
            raise AdapterError("Alpha Vantage key is not configured")
        ticker = request["ticker"].upper()
        requested_at = utc_now()
        with self._lock:
            if self._last_request_utc:
                remaining = self.minimum_request_interval_seconds - (requested_at-self._last_request_utc).total_seconds()
                if remaining > 0:
                    raise AdapterError(f"Alpha Vantage local rate-limit guard: retry after {remaining:.1f}s")
            self._last_request_utc = requested_at
        try:
            response = httpx.get("https://www.alphavantage.co/query", params={
                "function": "TIME_SERIES_INTRADAY", "symbol": ticker, "interval": "5min",
                "outputsize": "compact", "apikey": self.key,
            }, timeout=20)
            response.raise_for_status()
            payload = response.json()
            series = payload.get("Time Series (5min)", {})
            if not series:
                message = payload.get("Note") or payload.get("Information") or payload.get("Error Message") or "no bars"
                if "rate" in str(message).lower() or "frequency" in str(message).lower():
                    self.rate_limit_responses += 1
                if "invalid api call" in str(message).lower() or "apikey" in str(message).lower():
                    self.auth_errors += 1
                raise AdapterError(f"Alpha Vantage returned {message}")
            from zoneinfo import ZoneInfo
            rows = []
            for stamp, row in sorted(series.items()):
                at = datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=ZoneInfo(payload.get("Meta Data", {}).get("6. Time Zone", "US/Eastern")))
                rows.append({"t": at.isoformat(), "o": float(row["1. open"]), "h": float(row["2. high"]),
                             "l": float(row["3. low"]), "c": float(row["4. close"]), "v": float(row["5. volume"])})
            received_at = utc_now()
            self.last_success_utc, self.last_error = received_at, None
            return {"ticker": ticker, "bars": rows, "last_price": rows[-1]["c"],
                    "last_volume": rows[-1]["v"], "average_volume": 0,
                    "requested_at_utc": requested_at.isoformat(), "received_at_utc": received_at.isoformat(),
                    "provider_latency_ms": int((received_at-requested_at).total_seconds()*1000),
                    "interval": "5m", "provider": self.name, "official_source": False,
                    "provider_timestamp_utc": received_at.isoformat(), "raw_provider_payload": payload}
        except Exception as exc:
            self.last_error = str(exc)
            if isinstance(exc, AdapterError):
                raise
            raise AdapterError(f"Alpha Vantage fetch failed for {ticker}: {exc}") from exc

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        value = super().normalize(raw)
        for bar in value["bars"]:
            bar.source, bar.confidence_score = self.name, .65
        state = value["ticker_state"]
        state.source, state.confidence_score = self.name, .65
        value.update({"core_fields_complete": len(value["bars"]) >= 2,
                      "required_fields_complete": False, "unofficial_source": False,
                      "missing_fields": ["bid", "ask", "authoritative_quote_latency"]})
        value["provider_timing"]["provider"] = self.name
        return value

    def status(self) -> dict[str, Any]:
        value = super().status()
        value.update({"auth_status": "CONFIGURED" if self.configured else "NOT_CONFIGURED",
                      "rate_limit_responses": self.rate_limit_responses,
                      "auth_errors": self.auth_errors})
        return value


class FinnhubContextAdapter(DataSourceAdapter):
    name = "finnhub"
    capabilities = ["quote", "company_profile", "market_news", "calendar_context"]
    latency_type = "feed-dependent"
    requires_api_key = True
    cost_tier = "free-key"
    license_notes = "Optional context adapter; never required for reclaim candles."

    def __init__(self):
        super().__init__()
        self.key = os.getenv("FINNHUB_API_KEY", "")
        self.auth_errors = 0
        self.rate_limit_responses = 0

    @property
    def configured(self) -> bool:
        return bool(self.key)

    def fetch(self, request: dict[str, Any]) -> dict[str, Any]:
        if not self.configured:
            raise AdapterError("Finnhub key is not configured")
        endpoint = request.get("endpoint", "quote")
        requested_at = utc_now()
        try:
            response = httpx.get(f"https://finnhub.io/api/v1/{endpoint}",
                                 params={**request.get("params", {}), "symbol": request.get("ticker"), "token": self.key},
                                 timeout=15)
            if response.status_code in {401, 403}:
                self.auth_errors += 1
            if response.status_code == 429:
                self.rate_limit_responses += 1
            response.raise_for_status()
            received_at = utc_now()
            self.last_success_utc, self.last_error = received_at, None
            return {"endpoint": endpoint, "ticker": request.get("ticker"), "payload": response.json(),
                    "requested_at_utc": requested_at.isoformat(), "fetched_at_utc": received_at.isoformat(),
                    "provider_latency_ms": int((received_at-requested_at).total_seconds()*1000)}
        except Exception as exc:
            self.last_error = str(exc)
            raise

    def normalize(self, raw_payload: Any) -> Any:
        if raw_payload.get("endpoint") != "quote":
            return raw_payload
        payload = raw_payload.get("payload", {})
        now = utc_now()
        timestamp = None
        if payload.get("t"):
            timestamp = datetime.fromtimestamp(float(payload["t"]), tz=timezone.utc)
        last = float(payload.get("c") or 0)
        previous_close = float(payload.get("pc") or 0)
        quote_age = max(0, (now-timestamp).total_seconds()) if timestamp else None
        return {"provider": self.name, "ticker": str(raw_payload.get("ticker", "")).upper(),
                "authenticated": True, "quote_available": bool(last > 0 and timestamp),
                "current_price": last, "previous_close": previous_close,
                "quote_timestamp_utc": timestamp.isoformat() if timestamp else None,
                "quote_age_seconds": quote_age,
                "provider_latency_ms": raw_payload.get("provider_latency_ms"),
                "production_grade": False, "free_validation_eligible": bool(last > 0 and timestamp)}

    def status(self) -> dict[str, Any]:
        value = super().status()
        value.update({"auth_status": "CONFIGURED" if self.configured else "NOT_CONFIGURED",
                      "rate_limit_responses": self.rate_limit_responses,
                      "auth_errors": self.auth_errors})
        return value


class MacroCsvAdapter(DataSourceAdapter):
    name = "manual_macro_csv"
    capabilities = ["macro_events", "earnings_events", "session_events"]
    latency_type = "unknown"
    license_notes = "Operator-maintained; verify against official calendars before Production Paper."

    def __init__(self, path: Path):
        super().__init__()
        self.path = path

    @property
    def configured(self) -> bool:
        return self.path.exists()

    def fetch(self, request: dict[str, Any] | None = None) -> list[dict[str, str]]:
        with self.path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.last_success_utc, self.last_error = utc_now(), None
        return rows

    def normalize(self, raw: list[dict[str, str]]) -> list[MacroEvent]:
        return [MacroEvent(
            event_id=row["event_id"], event_name=row["event_name"], event_type=row["event_type"],
            event_time_utc=datetime.fromisoformat(row["event_time_utc"].replace("Z", "+00:00")),
            importance=row["importance"].lower(), scope=row.get("scope") or "market",
            tickers=[item.strip().upper() for item in (row.get("tickers") or "").split(";") if item.strip()],
            block_before_minutes=int(row["block_before_minutes"]) if row.get("block_before_minutes") else None,
            block_after_minutes=int(row["block_after_minutes"]) if row.get("block_after_minutes") else None,
            notes=row.get("notes", ""),
        ) for row in raw]


class MacroYamlAdapter(DataSourceAdapter):
    name = "manual_macro_yaml"
    capabilities = ["macro_events", "session_events", "manual_approval", "coverage_status"]
    latency_type = "operator-maintained"
    license_notes = "Manual calendar. Approval requires explicit file metadata and verified critical-event coverage."
    REQUIRED_TYPES = {"CPI", "FOMC", "NFP", "PPI", "PCE", "GDP", "FED_SPEAKER",
                      "TREASURY_AUCTION", "OPEX", "QUAD_WITCHING", "MARKET_HOLIDAY", "EARLY_CLOSE"}

    def __init__(self, path: Path):
        super().__init__()
        self.path = path
        self.metadata: dict[str, Any] = {}
        self.coverage: dict[str, Any] = {}

    @property
    def configured(self) -> bool:
        return self.path.exists()

    @property
    def approved(self) -> bool:
        critical = {"CPI", "FOMC", "NFP"}
        verified = set(self.coverage.get("verified_event_types", []))
        return bool(self.metadata.get("calendar_approved") and self.metadata.get("manually_verified")
                    and critical <= verified)

    def fetch(self, request: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.configured:
            raise AdapterError(f"Macro calendar not found: {self.path}")
        raw = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        self.last_success_utc, self.last_error = utc_now(), None
        return raw

    def normalize(self, raw: dict[str, Any]) -> list[MacroEvent]:
        from zoneinfo import ZoneInfo
        self.metadata = dict(raw.get("calendar", {}))
        events: list[MacroEvent] = []
        present, verified = set(), set()
        for index, row in enumerate(raw.get("events", [])):
            event_type = str(row.get("event_type", "")).upper()
            if event_type:
                present.add(event_type)
            if row.get("manually_verified"):
                verified.add(event_type)
            if not row.get("date") or not row.get("time_et"):
                continue
            local = datetime.fromisoformat(f"{row['date']}T{row['time_et']}").replace(
                tzinfo=ZoneInfo("America/New_York"))
            event_id = str(row.get("event_id") or f"macro-{event_type.lower()}-{row['date']}-{index}")
            affected = row.get("affected_symbols") or []
            events.append(MacroEvent(
                event_id=event_id, event_name=str(row.get("event_name") or event_type), event_type=event_type,
                event_time_utc=local.astimezone(timezone.utc), importance=str(row.get("severity", "medium")).lower(),
                scope="market" if not affected or "ALL" in affected else "ticker",
                tickers=[str(item).upper() for item in affected if str(item).upper() != "ALL"],
                block_before_minutes=int(row.get("block_before_minutes", 0)),
                block_after_minutes=int(row.get("block_after_minutes", 0)), notes=str(row.get("source_note", "")),
                source_note=str(row.get("source_note", "")), manually_verified=bool(row.get("manually_verified")),
                calendar_approved=bool(row.get("calendar_approved")),
            ))
        self.coverage = {"required_event_types": sorted(self.REQUIRED_TYPES),
                         "present_event_types": sorted(present), "verified_event_types": sorted(verified),
                         "missing_event_types": sorted(self.REQUIRED_TYPES-present),
                         "unverified_event_types": sorted(self.REQUIRED_TYPES-verified)}
        return events

    def status(self) -> dict[str, Any]:
        value = super().status()
        value.update({"calendar_approved": self.approved, "metadata": self.metadata, "coverage": self.coverage})
        return value


class GammaGridAdapter(DataSourceAdapter):
    name = "gammagrid"
    capabilities = ["chain_snapshots", "gex", "oi_change", "iv_surface", "greeks", "replay"]
    latency_type = "delayed"
    license_notes = "Local self-hosted database; upstream Yahoo wrapper has no SLA."

    def __init__(self, sqlite_path: str = "", database_url_env: str = "GAMMAGRID_DATABASE_URL"):
        super().__init__()
        self.sqlite_path = Path(sqlite_path) if sqlite_path else None
        self.database_url = os.getenv(database_url_env, "")

    @property
    def configured(self) -> bool:
        return bool((self.sqlite_path and self.sqlite_path.exists()) or self.database_url)

    def fetch(self, request: dict[str, Any]) -> dict[str, Any]:
        ticker = str(request.get("ticker", "")).upper()
        if self.database_url:
            try:
                import psycopg
                from psycopg.rows import dict_row
                with psycopg.connect(self.database_url, autocommit=True, row_factory=dict_row) as connection:
                    moment = connection.execute(
                        """SELECT source, collected_at FROM option_snapshots
                           WHERE ticker=%s ORDER BY collected_at DESC LIMIT 1""", (ticker,)).fetchone()
                    if not moment:
                        raise AdapterError(f"GammaGrid has no snapshot for {ticker}")
                    rows = connection.execute(
                        """SELECT ticker, collected_at, underlying_price, expiry, strike, option_type,
                                  last_price, bid, ask, volume, open_interest, implied_volatility,
                                  delta, gamma, theta, vega, source
                           FROM option_snapshots
                           WHERE ticker=%s AND source=%s AND collected_at=%s
                           ORDER BY expiry, strike, option_type""",
                        (ticker, moment["source"], moment["collected_at"]),
                    ).fetchall()
                self.last_success_utc, self.last_error = utc_now(), None
                return {"ticker": ticker, "collected_at": moment["collected_at"],
                        "chain_source": moment["source"], "storage": "postgres",
                        "rows": [dict(row) for row in rows]}
            except Exception as exc:
                self.last_error = str(exc)
                if isinstance(exc, AdapterError):
                    raise
                raise AdapterError(f"GammaGrid Postgres fetch failed for {ticker}: {exc}") from exc
        if not self.configured:
            raise AdapterError("GammaGrid database is not configured")
        try:
            with sqlite3.connect(f"file:{self.sqlite_path}?mode=ro", uri=True) as connection:
                connection.row_factory = sqlite3.Row
                moment = connection.execute(
                    "SELECT source, collected_at FROM option_snapshots WHERE ticker=? ORDER BY collected_at DESC LIMIT 1",
                    (ticker,),
                ).fetchone()
                if not moment:
                    raise AdapterError(f"GammaGrid has no snapshot for {ticker}")
                rows = connection.execute(
                    """SELECT ticker, collected_at, underlying_price, expiry, strike, option_type,
                              last_price, bid, ask, volume, open_interest, implied_volatility,
                              delta, gamma, theta, vega, source
                       FROM option_snapshots WHERE ticker=? AND source=? AND collected_at=?
                       ORDER BY expiry, strike, option_type""",
                    (ticker, moment["source"], moment["collected_at"]),
                ).fetchall()
            self.last_success_utc, self.last_error = utc_now(), None
            return {"ticker": ticker, "collected_at": moment["collected_at"],
                    "chain_source": moment["source"], "storage": "legacy_sqlite",
                    "rows": [dict(row) for row in rows]}
        except Exception as exc:
            self.last_error = str(exc)
            if isinstance(exc, AdapterError):
                raise
            raise AdapterError(f"GammaGrid SQLite fetch failed for {ticker}: {exc}") from exc

    @staticmethod
    def _greeks(spot: float, strike: float, years: float, iv: float, option_type: str,
                rate: float = .04) -> dict[str, float]:
        if min(spot, strike, years, iv) <= 0:
            return {}
        root = math.sqrt(years)
        d1 = (math.log(spot / strike) + (rate + iv * iv / 2) * years) / (iv * root)
        d2 = d1 - iv * root
        pdf = math.exp(-d1 * d1 / 2) / math.sqrt(2 * math.pi)
        cdf1 = .5 * (1 + math.erf(d1 / math.sqrt(2)))
        cdf2 = .5 * (1 + math.erf(d2 / math.sqrt(2)))
        if option_type == "call":
            delta = cdf1
            theta = (-(spot * pdf * iv) / (2 * root) - rate * strike * math.exp(-rate * years) * cdf2) / 365
            rho = strike * years * math.exp(-rate * years) * cdf2 / 100
        else:
            delta = cdf1 - 1
            theta = (-(spot * pdf * iv) / (2 * root) + rate * strike * math.exp(-rate * years) * (1-cdf2)) / 365
            rho = -strike * years * math.exp(-rate * years) * (1-cdf2) / 100
        gamma = pdf / (spot * iv * root)
        vega = spot * pdf * root / 100
        vanna = -pdf * d2 / iv
        charm = -pdf * (2 * rate * years - d2 * iv * root) / (2 * years * iv * root)
        return {"delta": delta, "gamma": gamma, "theta": theta, "vega": vega,
                "rho": rho, "vanna": vanna, "charm": charm}

    def normalize(self, raw: dict[str, Any]) -> GexMap:
        rows = raw.get("rows", [])
        if not rows:
            raise AdapterError("GammaGrid snapshot is empty")
        timestamp = raw.get("collected_at")
        if not isinstance(timestamp, datetime):
            timestamp = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        timestamp = timestamp.astimezone(timezone.utc)
        now = utc_now()
        spot = float(rows[0].get("underlying_price") or 0)
        by_strike: dict[float, dict[str, float]] = {}
        greek_totals = {key: 0.0 for key in ("delta", "gamma", "theta", "vega", "rho", "vanna", "charm")}
        greek_weight = 0.0
        valid_oi = valid_iv = valid_greeks = 0
        nearest_expiry_days: float | None = None
        atm_row: tuple[float, float] | None = None
        normalized_rows = []
        for row in rows:
            strike = float(row.get("strike") or 0)
            option_type = str(row.get("option_type", "")).lower()
            oi_raw, iv_raw = row.get("open_interest"), row.get("implied_volatility")
            oi = float(oi_raw or 0)
            iv = float(iv_raw or 0)
            valid_oi += oi_raw is not None
            valid_iv += iv_raw is not None and iv > 0
            expiry = datetime.fromisoformat(str(row["expiry"])[:10]).replace(hour=21, tzinfo=timezone.utc)
            years = max((expiry - timestamp).total_seconds() / (365.25 * 86400), 1 / (365.25 * 24))
            computed = self._greeks(spot, strike, years, iv, option_type)
            supplied = {key: row.get(key) for key in ("delta", "gamma", "theta", "vega")}
            greeks = {key: float(supplied[key]) if supplied.get(key) is not None else computed.get(key)
                      for key in greek_totals}
            if all(value is not None for value in greeks.values()):
                valid_greeks += 1
                weight = max(oi, 1)
                greek_weight += weight
                for key, value in greeks.items():
                    greek_totals[key] += float(value) * weight
            gamma_value = greeks.get("gamma") or 0
            signed_gex = float(gamma_value) * oi * 100 * spot * (-1 if option_type == "put" else 1)
            node = by_strike.setdefault(strike, {"net_gex": 0.0, "call_oi": 0.0, "put_oi": 0.0})
            node["net_gex"] += signed_gex
            node[f"{option_type}_oi"] = node.get(f"{option_type}_oi", 0.0) + oi
            days = years * 365.25
            if nearest_expiry_days is None or days < nearest_expiry_days:
                nearest_expiry_days = days
            distance = abs(strike - spot)
            if iv > 0 and (atm_row is None or distance < atm_row[0]):
                atm_row = (distance, iv)
            normalized_rows.append({"strike": strike, "option_type": option_type, "open_interest": oi,
                                    "implied_volatility": iv, "greeks": greeks})
        strikes = [{"strike": strike, **values} for strike, values in sorted(by_strike.items())]
        call_wall = max(strikes, key=lambda item: item["call_oi"])["strike"] if strikes else None
        put_wall = max(strikes, key=lambda item: item["put_oi"])["strike"] if strikes else None
        cumulative = 0.0
        prior: tuple[float, float] | None = None
        gamma_flip = None
        for item in strikes:
            cumulative += item["net_gex"]
            if prior and prior[1] * cumulative <= 0 and cumulative != prior[1]:
                gamma_flip = prior[0] + (item["strike"] - prior[0]) * (-prior[1]) / (cumulative - prior[1])
                break
            prior = (item["strike"], cumulative)
        pain = []
        for candidate in by_strike:
            payout = sum(item["open_interest"] * max(0, candidate-item["strike"] if item["option_type"] == "call"
                                                     else item["strike"]-candidate) for item in normalized_rows)
            pain.append((payout, candidate))
        max_pain = min(pain)[1] if pain else None
        oi_rank = sorted(strikes, key=lambda item: item["call_oi"] + item["put_oi"], reverse=True)
        oi_nodes = [float(item["strike"]) for item in oi_rank[:8] if item["call_oi"] + item["put_oi"] > 0]
        count = len(rows)
        coverage = {"oi": valid_oi/count, "iv": valid_iv/count, "greeks": valid_greeks/count,
                    "gex": sum(1 for item in strikes if item["net_gex"] != 0)/max(len(strikes), 1)}
        missing = []
        for field, present in (("gamma_flip", gamma_flip is not None), ("call_wall", call_wall is not None),
                               ("put_wall", put_wall is not None), ("open_interest", bool(oi_nodes)),
                               ("atm_iv", atm_row is not None), ("greeks", valid_greeks > 0)):
            if not present:
                missing.append(field)
        complete = not missing and coverage["oi"] >= .8 and coverage["iv"] >= .8 and coverage["greeks"] >= .8
        total_gex = sum(item["net_gex"] for item in strikes)
        atm_iv = atm_row[1] if atm_row else None
        return GexMap(ticker=raw["ticker"], source=self.name, source_timestamp_utc=timestamp,
                      ingestion_timestamp_utc=now, spot=spot, gamma_flip=gamma_flip,
                      call_wall=call_wall, put_wall=put_wall, max_pain=max_pain,
                      expected_move=(spot * atm_iv * math.sqrt(max(nearest_expiry_days or 1, 1)/365.25)
                                     if atm_iv else None), atm_iv=atm_iv,
                      gamma_regime="positive" if total_gex > 0 else "negative" if total_gex < 0 else "neutral",
                      strikes=strikes, oi_nodes=oi_nodes,
                      greeks_summary={key: value/greek_weight for key, value in greek_totals.items()} if greek_weight else {},
                      field_coverage=coverage, missing_required_fields=missing,
                      free_validation_complete=bool(spot > 0 and strikes and (call_wall or put_wall)),
                      freshness_seconds=max(0, (now-timestamp).total_seconds()),
                      confidence_score=min(.9, .55 + .35 * min(coverage.values())),
                      required_fields_complete=complete)


class QuantDataAdapter(DataSourceAdapter):
    name = "quantdata"
    capabilities = ["options_flow", "gex", "oi_change", "equity_prints", "dark_flow", "stock_bars"]
    latency_type = "realtime"
    requires_api_key = True
    cost_tier = "paid"
    license_notes = "Exchange-licensed; OPRA agreement and subscription may be required."

    def __init__(self):
        super().__init__()
        self.key = os.getenv("QUANTDATA_API_KEY", "")

    @property
    def configured(self) -> bool:
        return bool(self.key)

    def fetch(self, request: dict[str, Any]) -> dict[str, Any]:
        if not self.configured:
            raise AdapterError("Quant Data key is not configured")
        endpoint = request["endpoint"].lstrip("/")
        response = httpx.post(f"https://api.quantdata.us/{endpoint}", json=request.get("body", {}),
                              headers={"Authorization": f"Bearer {self.key}"}, timeout=20)
        response.raise_for_status()
        self.last_success_utc = utc_now()
        return response.json()

    def normalize(self, raw_payload: Any) -> Any:
        return raw_payload


class UnusualWhalesAdapter(DataSourceAdapter):
    name = "unusual_whales"
    capabilities = ["options_flow", "gex", "dark_pool", "market_data"]
    latency_type = "realtime"
    requires_api_key = True
    cost_tier = "paid"
    license_notes = "Plan and exchange entitlements apply; review redistribution rights."

    def __init__(self):
        super().__init__()
        self.key = os.getenv("UW_API_KEY", "")

    @property
    def configured(self) -> bool:
        return bool(self.key)

    def fetch(self, request: dict[str, Any]) -> dict[str, Any]:
        if not self.configured:
            raise AdapterError("Unusual Whales key is not configured")
        endpoint = request["endpoint"].lstrip("/")
        response = httpx.get(f"https://api.unusualwhales.com/{endpoint}", params=request.get("params", {}),
                             headers={"Authorization": f"Bearer {self.key}"}, timeout=20)
        response.raise_for_status()
        self.last_success_utc = utc_now()
        return response.json()

    def normalize(self, raw_payload: Any) -> Any:
        return raw_payload


class DemoFixtureAdapter(DataSourceAdapter):
    name = "demo_fixture"
    capabilities = ["synthetic_gex", "synthetic_ohlcv", "synthetic_features"]
    latency_type = "eod"
    license_notes = "Synthetic deterministic QA data. Never valid for Production Paper."

    BASES = {"SPY": 640, "QQQ": 575, "IWM": 245, "NVDA": 180, "TSLA": 350, "PLTR": 155,
             "AMD": 205, "META": 790, "GOOGL": 220, "MSFT": 525, "AAPL": 240, "OKLO": 72}

    def fetch(self, request: dict[str, Any]) -> dict[str, Any]:
        ticker = request["ticker"].upper()
        base = float(self.BASES.get(ticker, 100))
        now = request.get("now") or utc_now()
        width = max(round(base * 0.001, 2), 0.1)
        return {"ticker": ticker, "base": base, "width": width, "now": now.isoformat()}

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        now = datetime.fromisoformat(raw["now"])
        ticker, base, width = raw["ticker"], raw["base"], raw["width"]
        gex = GexMap(ticker=ticker, source=self.name, source_timestamp_utc=now - timedelta(minutes=15),
                     spot=base + width * 1.5, gamma_flip=base, call_wall=base + width * 16,
                     put_wall=base - width * 14, max_pain=base - width * 2, expected_move=width * 20,
                     atm_iv=35, gamma_regime="positive",
                     strikes=[{"strike": base + width * i, "net_gex": float(10 - abs(i))}
                              for i in (-14, -8, 0, 8, 16)],
                     oi_nodes=[base - width * 14, base - width * 8, base + width * 8, base + width * 16],
                     freshness_seconds=300)
        previous = Bar(ticker=ticker, bar_start_utc=now - timedelta(minutes=10), bar_end_utc=now - timedelta(minutes=5),
                       open=base + width, high=base + width * 2, low=base - width * 2,
                       close=base - width, volume=100_000, vwap=base, atr=width * 2, relative_volume=1.1)
        confirm = Bar(ticker=ticker, bar_start_utc=now - timedelta(minutes=5), bar_end_utc=now,
                      open=base - width, high=base + width * 3, low=base - width * 1.5,
                      close=base + width * 1.5, volume=180_000, vwap=base + width * .5,
                      atr=width * 2, relative_volume=1.8)
        state = TickerState(ticker=ticker, timestamp_utc=now, source=self.name, spot_price=confirm.close,
                            bid=confirm.close - width * .05, ask=confirm.close + width * .05, last=confirm.close,
                            spread_bps=(width * .1 / confirm.close) * 10_000, volume_today=2_000_000,
                            relative_volume=1.5, average_daily_volume=10_000_000,
                            ticker_class="index_etf" if ticker in {"SPY", "QQQ", "IWM"} else "high_beta_growth")
        return {"gex": gex, "previous_bar": previous, "confirmation_bar": confirm, "ticker_state": state}
