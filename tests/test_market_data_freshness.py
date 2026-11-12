from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

import yaml

from options_structure_trader.config import PROJECT_ROOT, Settings, load_local_env
from options_structure_trader.market_data import CandleProviderRouter, expected_completed_close
from options_structure_trader.models import Bar, TickerState


class FakeCandleAdapter:
    name = "yfinance"
    configured = True
    last_success_utc = None
    last_error = None

    def __init__(self, bars, *, unofficial=True):
        self.bars = bars
        self.unofficial = unofficial
        self.requests = 0

    def fetch(self, request):
        self.requests += 1
        return {"ticker": request["ticker"], "bars": self.bars, "provider": self.name}

    def normalize(self, raw):
        bars = raw["bars"]
        latest = bars[-1]
        state = TickerState(ticker=latest.ticker, timestamp_utc=latest.bar_end_utc, source=self.name,
                            spot_price=latest.close, bid=latest.close, ask=latest.close, last=latest.close,
                            spread_bps=0, source_freshness_seconds=latest.source_freshness_seconds,
                            confidence_score=.45)
        return {"bars": bars, "ticker_state": state, "core_fields_complete": len(bars) >= 2,
                "required_fields_complete": False, "unofficial_source": self.unofficial,
                "missing_fields": ["bid", "ask"],
                "provider_timing": {"provider": self.name}}


class FakeQuoteAdapter:
    name = "finnhub"
    configured = True
    last_success_utc = None
    last_error = None

    def __init__(self, age=5):
        self.age = age
        self.requests = 0

    def fetch(self, request):
        self.requests += 1
        return {"ticker": request["ticker"], "endpoint": "quote"}

    def normalize(self, raw):
        return {"provider": self.name, "ticker": raw["ticker"], "authenticated": True,
                "quote_available": True, "current_price": 100, "previous_close": 99,
                "quote_age_seconds": self.age, "production_grade": False,
                "free_validation_eligible": True}


class FakeAlphaAdapter(FakeCandleAdapter):
    name = "alpha_vantage"


def router_settings(tmp_path):
    data = yaml.safe_load((PROJECT_ROOT / "config" / "config.yaml").read_text(encoding="utf-8"))
    data = copy.deepcopy(data)
    data["database"]["path"] = str(tmp_path / "test.db")
    data["sources"]["alpha_vantage"]["enabled"] = True
    data["sources"]["alpha_vantage"]["daily_limit"] = 2
    data["sources"]["finnhub"]["enabled"] = True
    data["sources"]["yfinance"]["enabled"] = True
    data["freshness"]["completed_bar_grace_seconds"] = 60
    data["freshness"]["retry_after_seconds"] = 1
    data["freshness"]["max_retries"] = 1
    return Settings(data, PROJECT_ROOT)


def bars_for(symbol: str, latest_end: datetime):
    prior_end = latest_end - timedelta(minutes=5)
    return [
        Bar(ticker=symbol, bar_start_utc=prior_end-timedelta(minutes=5), bar_end_utc=prior_end,
            open=99, high=101, low=98, close=100, volume=1000, atr=.5,
            source_freshness_seconds=0),
        Bar(ticker=symbol, bar_start_utc=latest_end-timedelta(minutes=5), bar_end_utc=latest_end,
            open=100, high=102, low=99, close=101, volume=1200, atr=.5,
            source_freshness_seconds=0),
    ]


def test_credentials_are_loaded_from_local_env(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("FINNHUB_API_KEY=fh_test\nALPHA_VANTAGE_API_KEY=av_test\n", encoding="utf-8")
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)
    load_local_env(env_path)
    assert __import__("os").environ["FINNHUB_API_KEY"] == "fh_test"
    assert __import__("os").environ["ALPHA_VANTAGE_API_KEY"] == "av_test"


def test_expected_completed_candle_uses_rth_open_alignment():
    now = datetime(2026, 9, 2, 14, 17, tzinfo=timezone.utc)
    assert expected_completed_close(now, "5m").astimezone(timezone.utc) == datetime(
        2026, 9, 2, 14, 15, tzinfo=timezone.utc)


def test_yahoo_fresh_completed_candle_selected(tmp_path):
    now = datetime(2026, 9, 2, 14, 17, tzinfo=timezone.utc)
    adapters = {"yfinance": FakeCandleAdapter(bars_for("SPY", datetime(2026, 9, 2, 14, 15, tzinfo=timezone.utc))),
                "finnhub": FakeQuoteAdapter(),
                "alpha_vantage": FakeAlphaAdapter([])}
    result = CandleProviderRouter(router_settings(tmp_path), adapters, now_fn=lambda: now).route(
        "SPY", tier="tier_1_core", current_time=now)
    assert result.selected_provider == "YFINANCE"
    assert result.free_validation_eligible
    assert result.providers_attempted == ["YFINANCE"]


def test_yahoo_delayed_retries_inside_grace_window(tmp_path):
    now_values = [datetime(2026, 9, 2, 14, 35, tzinfo=timezone.utc),
                  datetime(2026, 9, 2, 14, 36, tzinfo=timezone.utc)]
    latest = datetime(2026, 9, 2, 14, 30, tzinfo=timezone.utc)
    fresh = datetime(2026, 9, 2, 14, 35, tzinfo=timezone.utc)
    adapter = FakeCandleAdapter(bars_for("SPY", latest))

    def fetch(request):
        adapter.requests += 1
        adapter.bars = bars_for("SPY", fresh if adapter.requests > 1 else latest)
        return {"ticker": "SPY", "bars": adapter.bars}

    adapter.fetch = fetch
    adapters = {"yfinance": adapter, "finnhub": FakeQuoteAdapter(),
                "alpha_vantage": FakeAlphaAdapter([])}
    router = CandleProviderRouter(router_settings(tmp_path), adapters,
                                  now_fn=lambda: now_values[min(adapter.requests, 1)],
                                  sleeper=lambda _: None)
    result = router.route("SPY", tier="tier_1_core", current_time=now_values[0])
    assert result.selected_provider == "YFINANCE"
    assert adapter.requests == 2


def test_yahoo_stale_finnhub_fresh_is_candle_provider_delay_not_valid(tmp_path):
    now = datetime(2026, 9, 2, 14, 42, tzinfo=timezone.utc)
    adapters = {"yfinance": FakeCandleAdapter(bars_for("SPY", datetime(2026, 9, 2, 14, 30, tzinfo=timezone.utc))),
                "finnhub": FakeQuoteAdapter(age=3),
                "alpha_vantage": FakeAlphaAdapter([])}
    result = CandleProviderRouter(router_settings(tmp_path), adapters, now_fn=lambda: now).route(
        "SPY", tier="tier_3_high_beta_theme", current_time=now)
    assert result.rejection_reason == "CANDLE_PROVIDER_DELAY"
    assert not result.free_validation_eligible
    assert result.quote_confirmation["quote_age_seconds"] == 3


def test_yahoo_stale_alpha_fresh_selects_alpha_for_tier1(tmp_path):
    now = datetime(2026, 9, 2, 14, 42, tzinfo=timezone.utc)
    adapters = {"yfinance": FakeCandleAdapter(bars_for("SPY", datetime(2026, 9, 2, 14, 30, tzinfo=timezone.utc))),
                "finnhub": FakeQuoteAdapter(age=3),
                "alpha_vantage": FakeAlphaAdapter(bars_for("SPY", datetime(2026, 9, 2, 14, 40, tzinfo=timezone.utc)))}
    result = CandleProviderRouter(router_settings(tmp_path), adapters, now_fn=lambda: now).route(
        "SPY", tier="tier_1_core", current_time=now)
    assert result.selected_provider == "ALPHA_VANTAGE"
    assert result.fallback_used
    assert result.free_validation_eligible


def test_tier3_does_not_consume_alpha_quota(tmp_path):
    now = datetime(2026, 9, 2, 14, 42, tzinfo=timezone.utc)
    alpha = FakeAlphaAdapter(bars_for("SPY", datetime(2026, 9, 2, 14, 40, tzinfo=timezone.utc)))
    adapters = {"yfinance": FakeCandleAdapter(bars_for("SPY", datetime(2026, 9, 2, 14, 30, tzinfo=timezone.utc))),
                "finnhub": FakeQuoteAdapter(age=3), "alpha_vantage": alpha}
    result = CandleProviderRouter(router_settings(tmp_path), adapters, now_fn=lambda: now).route(
        "SPY", tier="tier_3_high_beta_theme", current_time=now)
    assert "ALPHA_VANTAGE" not in result.providers_attempted
    assert alpha.requests == 0


def test_unfinished_candle_rejected(tmp_path):
    now = datetime(2026, 9, 2, 14, 17, tzinfo=timezone.utc)
    bars = bars_for("SPY", datetime(2026, 9, 2, 14, 20, tzinfo=timezone.utc))
    bars[-1].closed = False
    adapters = {"yfinance": FakeCandleAdapter(bars), "finnhub": FakeQuoteAdapter(),
                "alpha_vantage": FakeAlphaAdapter([])}
    result = CandleProviderRouter(router_settings(tmp_path), adapters, now_fn=lambda: now).route(
        "SPY", tier="tier_3_high_beta_theme", current_time=now)
    assert result.rejection_reason == "UNFINISHED_CANDLE_REJECTED"


def test_cross_provider_major_conflict_goes_shadow():
    primary = {"bars": bars_for("SPY", datetime(2026, 9, 2, 14, 15, tzinfo=timezone.utc))}
    fallback = {"bars": bars_for("SPY", datetime(2026, 9, 2, 14, 15, tzinfo=timezone.utc))}
    fallback["bars"][-1].close = 120
    assert CandleProviderRouter.crosscheck(primary, fallback)["state"] == "MAJOR_CONFLICT"
