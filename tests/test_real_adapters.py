from __future__ import annotations

from datetime import datetime, timedelta, timezone

from options_structure_trader.adapters import AlgoXAdapter, GammaGridAdapter, YFinanceMarketBarsAdapter


def test_algox_is_real_but_incomplete_without_oi_and_greeks():
    now = datetime.now(timezone.utc)
    value = AlgoXAdapter().normalize({"ticker": "SPY", "updated": now.isoformat(), "spot": 100,
                                      "flip": 100, "callWall": 105, "putWall": 95, "atmIv": .2,
                                      "strikes": [{"k": 95, "g": -1}, {"k": 105, "g": 1}]})
    assert value.required_fields_complete is False
    assert value.missing_required_fields == ["open_interest", "greeks"]


def test_gammagrid_chain_normalizes_oi_iv_greeks_and_levels():
    now = datetime.now(timezone.utc) - timedelta(minutes=5)
    expiry = (now + timedelta(days=7)).date().isoformat()
    rows = []
    for strike, side, oi in ((95, "call", 2000), (100, "call", 800),
                             (100, "put", 800), (105, "put", 4000)):
        rows.append({"underlying_price": 100, "expiry": expiry, "strike": strike,
                     "option_type": side, "open_interest": oi, "implied_volatility": .3,
                     "delta": None, "gamma": None, "theta": None, "vega": None,
                     "source": "yahoo"})
    value = GammaGridAdapter().normalize({"ticker": "SPY", "collected_at": now,
                                           "chain_source": "yahoo", "rows": rows})
    assert value.call_wall == 95
    assert value.put_wall == 105
    assert value.gamma_flip is not None
    assert value.oi_nodes
    assert set(value.greeks_summary) == {"delta", "gamma", "theta", "vega", "rho", "vanna", "charm"}
    assert value.required_fields_complete


def test_yfinance_normalization_is_never_production_complete():
    now = datetime.now(timezone.utc)
    raw = {"ticker": "SPY", "last_price": 100, "last_volume": 1000, "average_volume": 100000,
           "bars": [{"t": (now-timedelta(minutes=10)).isoformat(), "o": 99, "h": 101,
                     "l": 98, "c": 100, "v": 1000}]}
    value = YFinanceMarketBarsAdapter().normalize(raw)
    assert value["required_fields_complete"] is False
    assert "authoritative_feed_latency" in value["missing_fields"]
