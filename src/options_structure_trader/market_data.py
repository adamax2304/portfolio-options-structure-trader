from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from statistics import median
from typing import Any, Callable
from zoneinfo import ZoneInfo

from .adapters import AdapterError


EASTERN = ZoneInfo("America/New_York")


def interval_minutes(value: str) -> int:
    text = str(value or "5m").lower().replace("min", "m")
    if text.endswith("m"):
        return max(1, int(text[:-1]))
    if text.endswith("s"):
        return max(1, int(text[:-1]) // 60)
    return 5


def expected_completed_close(now_utc: datetime, interval: str = "5m",
                             session: dict[str, Any] | None = None) -> datetime:
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    now_utc = now_utc.astimezone(timezone.utc)
    minutes = interval_minutes(interval)
    local = now_utc.astimezone(EASTERN)
    open_utc = session.get("session_open_utc") if session else None
    close_utc = session.get("session_close_utc") if session else None
    open_local = (datetime.fromisoformat(open_utc).astimezone(EASTERN)
                  if open_utc else datetime.combine(local.date(), time(9, 30), EASTERN))
    close_local = (datetime.fromisoformat(close_utc).astimezone(EASTERN)
                   if close_utc else datetime.combine(local.date(), time(16, 0), EASTERN))
    if local <= open_local:
        return open_local.astimezone(timezone.utc)
    bounded = min(local, close_local)
    elapsed_seconds = max(0, int((bounded-open_local).total_seconds()))
    completed = elapsed_seconds // (minutes * 60)
    return (open_local + timedelta(minutes=completed*minutes)).astimezone(timezone.utc)


@dataclass
class AlphaVantageRateBudget:
    per_minute_limit: int = 5
    daily_limit: int = 25
    clock: Callable[[], datetime] | None = None
    requests_today: int = 0
    rate_limit_responses: int = 0
    cooldown_until: datetime | None = None
    _request_times: list[datetime] = field(default_factory=list)
    _day: str | None = None

    def _now(self) -> datetime:
        return (self.clock or (lambda: datetime.now(timezone.utc)))().astimezone(timezone.utc)

    def _roll(self, now: datetime) -> None:
        day = now.astimezone(EASTERN).date().isoformat()
        if self._day != day:
            self._day = day
            self.requests_today = 0
            self.rate_limit_responses = 0
            self.cooldown_until = None
            self._request_times.clear()
        self._request_times = [item for item in self._request_times if (now-item).total_seconds() < 60]

    def status(self) -> dict[str, Any]:
        now = self._now()
        self._roll(now)
        return {"requests_today": self.requests_today, "requests_last_minute": len(self._request_times),
                "last_request_time": self._request_times[-1].isoformat() if self._request_times else None,
                "rate_limit_responses": self.rate_limit_responses,
                "daily_limit_remaining": max(0, self.daily_limit-self.requests_today),
                "cooldown_until": self.cooldown_until.isoformat() if self.cooldown_until else None}

    def can_use(self, tier: str, comfortable: bool = False) -> bool:
        now = self._now()
        self._roll(now)
        if self.cooldown_until and now < self.cooldown_until:
            return False
        remaining = self.daily_limit - self.requests_today
        if remaining <= 0 or len(self._request_times) >= self.per_minute_limit:
            return False
        if comfortable and tier not in {"tier_1_core"} and remaining <= max(5, self.daily_limit // 3):
            return False
        return True

    def record_request(self) -> None:
        now = self._now()
        self._roll(now)
        self.requests_today += 1
        self._request_times.append(now)

    def record_rate_limit(self, cooldown_seconds: int = 60) -> None:
        now = self._now()
        self._roll(now)
        self.rate_limit_responses += 1
        self.cooldown_until = now + timedelta(seconds=cooldown_seconds)


@dataclass
class CandleRouteResult:
    symbol: str
    interval: str
    selected_provider: str | None
    raw_payload: dict[str, Any] | None
    normalized: dict[str, Any] | None
    providers_attempted: list[str]
    statuses: dict[str, Any]
    expected_completed_bar_time: datetime
    candle_age_seconds: float | None
    fallback_used: bool = False
    quote_confirmation: dict[str, Any] | None = None
    data_quality: dict[str, Any] = field(default_factory=dict)
    rejection_reason: str | None = None

    @property
    def free_validation_eligible(self) -> bool:
        return bool(self.normalized and not self.rejection_reason)

    @property
    def selected_adapter_name(self) -> str | None:
        return self.selected_provider.lower() if self.selected_provider else None

    def provider_payload(self) -> dict[str, Any]:
        latest = None
        if self.normalized:
            bar = self.normalized["bars"][-1]
            latest = bar.bar_end_utc.isoformat()
        return {"selected_candle_provider": self.selected_provider,
                "selected_provider": self.selected_provider,
                "candle_timestamp": latest,
                "candle_age_seconds": self.candle_age_seconds,
                "expected_completed_bar_time": self.expected_completed_bar_time.isoformat(),
                "fallback_used": self.fallback_used,
                "providers_attempted": self.providers_attempted,
                "quote_confirmation": self.quote_confirmation,
                "router_status": self.statuses,
                "rejection_reason": self.rejection_reason,
                "free_validation_eligible": self.free_validation_eligible}


class CandleProviderRouter:
    def __init__(self, settings: Any, adapters: dict[str, Any], *,
                 now_fn: Callable[[], datetime] | None = None,
                 sleeper: Callable[[float], None] | None = None):
        self.settings = settings
        self.adapters = adapters
        self.now_fn = now_fn or (lambda: datetime.now(timezone.utc))
        self.sleeper = sleeper or (lambda seconds: None)
        self.alpha_budget = AlphaVantageRateBudget(
            per_minute_limit=int(settings.get("sources.alpha_vantage.per_minute_limit", 5)),
            daily_limit=int(settings.get("sources.alpha_vantage.daily_limit", 25)),
            clock=self.now_fn,
        )

    def _enabled(self, name: str) -> bool:
        adapter = self.adapters.get(name)
        return bool(adapter and self.settings.get(f"sources.{name}.enabled", False) and adapter.configured)

    def _freshness_status(self, normalized: dict[str, Any], now: datetime, expected_close: datetime,
                          interval: str, grace_seconds: int) -> tuple[str, float, dict[str, Any]]:
        bars = normalized.get("bars") or []
        if not bars:
            return "NO_BARS", 0, {}
        latest = bars[-1]
        interval_delta = timedelta(minutes=interval_minutes(interval))
        candle_age = max(0, (now-latest.bar_end_utc).total_seconds())
        expected_age = max(0, (now-expected_close).total_seconds())
        timing = dict(normalized.get("provider_timing") or {})
        timing.update({"latest_bar_close_time": latest.bar_end_utc.isoformat(),
                       "expected_completed_bar_time": expected_close.isoformat(),
                       "candle_age_seconds": candle_age,
                       "expected_completed_bar_age_seconds": expected_age})
        if not latest.closed or latest.bar_end_utc > now + timedelta(seconds=1):
            return "UNFINISHED", candle_age, timing
        if latest.bar_end_utc >= expected_close:
            return "FRESH", candle_age, timing
        if now-expected_close <= timedelta(seconds=grace_seconds) and latest.bar_end_utc >= expected_close-interval_delta:
            return "PUBLISH_DELAY_GRACE", candle_age, timing
        return "STALE", candle_age, timing

    def _fetch_normalized(self, provider: str, symbol: str, interval: str, *,
                          force_refresh: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
        adapter = self.adapters[provider]
        raw = adapter.fetch({"ticker": symbol, "timeframe": "5Min", "interval": interval,
                             "limit": 200, "force_refresh": force_refresh})
        return raw, adapter.normalize(raw)

    def _finnhub_quote(self, symbol: str) -> dict[str, Any] | None:
        if not self._enabled("finnhub"):
            return None
        adapter = self.adapters["finnhub"]
        raw = adapter.fetch({"ticker": symbol, "endpoint": "quote"})
        quote = adapter.normalize(raw)
        quote["status"] = "FRESH" if quote.get("quote_available") and (
            quote.get("quote_age_seconds") is not None and
            float(quote["quote_age_seconds"]) <= int(self.settings.get(
                "freshness.free_validation_price_max_seconds", 420))) else "STALE"
        return quote

    def _try_alpha(self, symbol: str, tier: str, now: datetime, expected_close: datetime,
                   interval: str, statuses: dict[str, Any],
                   providers_attempted: list[str]) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str]:
        if not self._enabled("alpha_vantage"):
            statuses["alpha_vantage_status"] = "NOT_CONFIGURED"
            return None, None, "NOT_CONFIGURED"
        if tier not in {"tier_1_core"} and not self.alpha_budget.can_use(tier, comfortable=True):
            statuses["alpha_vantage_status"] = "BUDGET_RESERVED_FOR_PRIORITY"
            return None, None, "BUDGET_RESERVED_FOR_PRIORITY"
        if not self.alpha_budget.can_use(tier, comfortable=False):
            statuses["alpha_vantage_status"] = "RATE_BUDGET_EXHAUSTED"
            return None, None, "RATE_BUDGET_EXHAUSTED"
        providers_attempted.append("ALPHA_VANTAGE")
        self.alpha_budget.record_request()
        try:
            raw, normalized = self._fetch_normalized("alpha_vantage", symbol, interval, force_refresh=True)
        except Exception as exc:
            if "rate" in str(exc).lower():
                self.alpha_budget.record_rate_limit()
                status = "RATE_LIMITED"
            elif "premium endpoint" in str(exc).lower() or "entitlement" in str(exc).lower():
                status = "ENTITLEMENT_UNAVAILABLE"
            elif "key" in str(exc).lower() or "apikey" in str(exc).lower():
                status = "AUTH_INVALID"
            else:
                status = "ERROR"
            statuses["alpha_vantage_status"] = status
            statuses["alpha_vantage_error"] = str(exc)
            return None, None, status
        status, age, timing = self._freshness_status(normalized, now, expected_close, interval, 0)
        statuses["alpha_vantage_status"] = status
        statuses["alpha_vantage_timing"] = timing
        statuses["alpha_vantage_candle_age_seconds"] = age
        return (raw, normalized, status) if status == "FRESH" else (None, normalized, status)

    @staticmethod
    def crosscheck(primary: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
        left, right = primary["bars"][-1], fallback["bars"][-1]
        if left.bar_end_utc != right.bar_end_utc:
            return {"state": "TIMESTAMP_MISMATCH", "timestamp_alignment": False}
        base = max(abs(left.close), 0.01)
        deviations = {
            "open_deviation_bps": abs(left.open-right.open) / base * 10_000,
            "high_deviation_bps": abs(left.high-right.high) / base * 10_000,
            "low_deviation_bps": abs(left.low-right.low) / base * 10_000,
            "close_deviation_bps": abs(left.close-right.close) / base * 10_000,
            "volume_deviation_pct": abs(left.volume-right.volume) / max(abs(left.volume), 1) * 100,
            "timestamp_alignment": True,
        }
        price_max = max(deviations[key] for key in (
            "open_deviation_bps", "high_deviation_bps", "low_deviation_bps", "close_deviation_bps"))
        if price_max >= 30 or deviations["volume_deviation_pct"] >= 50:
            state = "MAJOR_CONFLICT"
        elif price_max >= 8 or deviations["volume_deviation_pct"] >= 20:
            state = "MINOR_DEVIATION"
        else:
            state = "AGREE"
        return {"state": state, **deviations}

    def route(self, symbol: str, *, interval: str = "5m", tier: str = "tier_1_core",
              current_time: datetime | None = None, required_freshness: int | None = None,
              paper_mode: str = "free-validation",
              session: dict[str, Any] | None = None) -> CandleRouteResult:
        now = (current_time or self.now_fn()).astimezone(timezone.utc)
        grace = int(self.settings.get("freshness.completed_bar_grace_seconds", 60))
        retry_after = int(self.settings.get("freshness.retry_after_seconds", 20))
        max_retries = int(self.settings.get("freshness.max_retries", 3))
        expected = expected_completed_close(now, interval, session)
        providers_attempted: list[str] = []
        statuses: dict[str, Any] = {"paper_mode": paper_mode,
                                    "required_freshness_seconds": required_freshness,
                                    "alpha_vantage_budget": self.alpha_budget.status()}
        yf_raw = yf_norm = None
        yf_status = "NOT_CONFIGURED"
        if self._enabled("yfinance"):
            for attempt in range(max_retries + 1):
                if "YFINANCE" not in providers_attempted:
                    providers_attempted.append("YFINANCE")
                try:
                    yf_raw, yf_norm = self._fetch_normalized(
                        "yfinance", symbol, interval, force_refresh=attempt > 0)
                    yf_status, yf_age, yf_timing = self._freshness_status(
                        yf_norm, now, expected, interval, grace)
                    statuses["yfinance_status"] = yf_status
                    statuses["yfinance_timing"] = yf_timing
                    statuses["yfinance_candle_age_seconds"] = yf_age
                    if yf_status == "FRESH":
                        return CandleRouteResult(
                            symbol, interval, "YFINANCE", yf_raw, yf_norm, providers_attempted,
                            statuses, expected, yf_age,
                            data_quality={"official_source": False, "candle_source": "YFINANCE",
                                          "completed": True})
                    if yf_status != "PUBLISH_DELAY_GRACE" or attempt >= max_retries:
                        break
                    self.sleeper(retry_after)
                    now = self.now_fn().astimezone(timezone.utc)
                    expected = expected_completed_close(now, interval, session)
                except Exception as exc:
                    yf_status = "ERROR"
                    statuses["yfinance_status"] = yf_status
                    statuses["yfinance_error"] = str(exc)
                    break
        statuses["yfinance_status"] = yf_status
        quote = None
        if tier in {"tier_1_core", "tier_2_liquid_growth"} or self._enabled("finnhub"):
            providers_attempted.append("FINNHUB")
            try:
                quote = self._finnhub_quote(symbol)
                statuses["finnhub_quote_status"] = quote.get("status") if quote else "NOT_CONFIGURED"
                statuses["finnhub_quote_age_seconds"] = quote.get("quote_age_seconds") if quote else None
            except Exception as exc:
                status = "AUTH_INVALID" if "401" in str(exc) or "403" in str(exc) else (
                    "RATE_LIMITED" if "429" in str(exc) else "ERROR")
                statuses["finnhub_quote_status"] = status
                statuses["finnhub_error"] = str(exc)
        if tier in {"tier_1_core", "tier_2_liquid_growth"}:
            alpha_raw, alpha_norm, alpha_status = self._try_alpha(
                symbol, tier, now, expected, interval, statuses, providers_attempted)
            if alpha_raw and alpha_norm:
                crosscheck = None
                if yf_norm and yf_status == "FRESH":
                    crosscheck = self.crosscheck(yf_norm, alpha_norm)
                    statuses["provider_crosscheck_status"] = crosscheck
                    if crosscheck["state"] == "MAJOR_CONFLICT":
                        return CandleRouteResult(
                            symbol, interval, None, None, None, providers_attempted,
                            statuses, expected, None, fallback_used=True, quote_confirmation=quote,
                            rejection_reason="CROSS_PROVIDER_MAJOR_CONFLICT",
                            data_quality={"provider_crosscheck_status": crosscheck})
                age = statuses.get("alpha_vantage_candle_age_seconds")
                return CandleRouteResult(
                    symbol, interval, "ALPHA_VANTAGE", alpha_raw, alpha_norm, providers_attempted,
                    statuses, expected, age, fallback_used=True, quote_confirmation=quote,
                    data_quality={"official_source": False, "candle_source": "ALPHA_VANTAGE",
                                  "completed": True,
                                  "provider_crosscheck_status": crosscheck or {"state": "NOT_COMPARED"}})
        quote_fresh = quote and quote.get("status") == "FRESH"
        reason = "CANDLE_PROVIDER_DELAY" if quote_fresh and yf_status in {
            "STALE", "PUBLISH_DELAY_GRACE", "ERROR"} else "MARKET_DATA_STALE"
        if yf_status == "UNFINISHED":
            reason = "UNFINISHED_CANDLE_REJECTED"
        return CandleRouteResult(
            symbol, interval, None, None, None, providers_attempted, statuses, expected, None,
            fallback_used=bool("ALPHA_VANTAGE" in providers_attempted), quote_confirmation=quote,
            rejection_reason=reason,
            data_quality={"official_source": False, "completed": False,
                          "candle_source": None, "finnhub_quote_only": bool(quote_fresh)})


def summarize_provider_freshness(observations: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for item in observations:
        providers = item.get("providers", {})
        router = providers.get("candle_router") or {}
        selected = router.get("selected_candle_provider") or providers.get("price")
        lag = router.get("candle_age_seconds") or providers.get("price_freshness_seconds")
        if selected or lag is not None:
            rows.append({"ticker": item.get("ticker"), "lane": item.get("lane"),
                         "free_validation": bool(item.get("free_validation_eligible")),
                         "provider": selected, "tier": item.get("data_quality", {}).get("watchlist_tier"),
                         "lag": float(lag or 0), "reason": router.get("rejection_reason"),
                         "fallback_used": bool(router.get("fallback_used"))})
    lags = [row["lag"] for row in rows if row["lag"] is not None]
    valid = [row for row in rows if row["free_validation"]]
    fallback_attempts = [row for row in rows if row["fallback_used"]]
    fallback_success = [row for row in fallback_attempts if row["free_validation"]]
    by_provider = {}
    for row in rows:
        key = row["provider"] or "NONE"
        bucket = by_provider.setdefault(key, {"valid_scans": 0, "stale_scans": 0})
        bucket["valid_scans"] += int(row["free_validation"])
        bucket["stale_scans"] += int(not row["free_validation"])
    return {"valid_scans_by_candle_provider": by_provider,
            "average_candle_publication_lag": round(sum(lags)/len(lags), 4) if lags else 0,
            "median_publication_lag": round(median(lags), 4) if lags else 0,
            "p95_publication_lag": round(sorted(lags)[max(0, int(len(lags)*.95)-1)], 4) if lags else 0,
            "maximum_lag": round(max(lags), 4) if lags else 0,
            "fallback_success_rate": round(len(fallback_success)/len(fallback_attempts), 4) if fallback_attempts else 0,
            "rows": rows}
