# Historical Options Source Matrix

Generated: 2026-09-03T23:58:45.321500+00:00

This matrix is for Phase 3B historical reconstruction only. It does not authorize paid signups, purchases, live trading, or changes to the running daemon.

## Source matrix

| source | free/trial/paid | account required | API key required | historical depth | option chain | OI | IV | Greeks | bid/ask | volume | intraday timestamps | EOD only | suitability | URL |
|---|---|---:|---:|---|---|---|---|---|---|---|---|---|---:|---|
| Cboe Historical Options Data Download | free public web form | False | False | monthly/yearly historical volume by Cboe exchange/product/symbol | False | False | False | False | False | True | False | True | 20 | https://www.cboe.com/us/options/market_statistics/historical_data/ |
| Cboe DataShop Option Quote Intervals | paid | True | account/download access | January 2012 to present | True | not primary field; depends on package | optional add-on | optional add-on | True | True | True | False | 90 | https://datashop.cboe.com/option-quote-intervals |
| OCC Volume and Open Interest Reports | free public reports | False | False | public report history varies; daily volume page indicates recent history | False | aggregate/report-level, not full quoted chain | False | False | False | True | False | True | 30 | https://www.theocc.com/market-data/market-data-reports/volume-and-open-interest/daily-volume |
| NYSE Options Open-Close Volume Summary | paid product with sample | True | purchase/download access | previous trading day EOD; intraday 10-minute snapshots in product | False | False | False | False | False | True | True | False | 25 | https://www.nyse.com/data-products/catalog/open-close-volume-summary |
| Yahoo Finance / yfinance | free unofficial | False | False | 5m underlying candles available for recent windows; option chains are current/future snapshots | current only | current chain has openInterest | current chain has impliedVolatility | False | True | True | underlying only | False | 40 | https://pypi.org/project/yfinance/ |
| Alpha Vantage Historical Options | premium endpoint; free key available for other endpoints | True | True | docs state 15+ years for HISTORICAL_OPTIONS | True | True | True | True | depends on endpoint fields | True | False | True | 75 | https://www.alphavantage.co/documentation/ |
| Finnhub | free key plus paid tiers | True | True | equity quote/candles vary; options chain access plan-dependent | plan-dependent | plan-dependent | plan-dependent | plan-dependent | plan-dependent | plan-dependent | not usable in current probe | unknown | 20 | https://finnhub.io/docs/api |
| MarketData.app | free trial; paid subscription after | True | True | docs state historical EOD options quotes back to 2010 | True | True | real-time yes; docs say not currently for historical EOD | real-time yes; docs say not currently for historical EOD | True | True | False | True | 65 | https://www.marketdata.app/data/options/ |
| ThetaData | trial/paid | True | True | historical options and stocks; flat files available | True | True | True | True | True | True | True | False | 90 | https://www.thetadata.net/ |
| Intrinio | sales/trial/paid | True | True | historical EOD options chain available via third party/contact sales | True | True | True | True | True | True | separate intraday product | EOD endpoint; intraday product separate | 85 | https://docs.intrinio.com/documentation/web_api/get_options_chain_v2 |
| Databento OPRA | usage-based with advertised starter credits | True | True | OPRA historical coverage; plan/dataset dependent | True | True | not precomputed | not precomputed | True | True | True | False | 88 | https://databento.com/options |
| Massive / Polygon Options | free reference tier; useful snapshots/market data require paid options plan | True | True | contract reference and option OHLC; snapshot history not applicable | current snapshot only on paid options plans | True | True | True | True | True | option trades/quotes/bars on paid plans | False | 70 | https://massive.com/docs/rest/options/overview |
| Tradier | developer/brokerage account; market data entitlement dependent | True | True | current chains; daily/weekly/monthly historical pricing by OCC option symbol | current chain by expiration | True | True | True | True | True | False | historical endpoint is daily/weekly/monthly | 45 | https://docs.tradier.com/reference/brokerage-api-markets-get-options-chains |
| Public Kaggle/GitHub/academic archives | varies/free | varies | varies | dataset-specific | dataset-specific | dataset-specific | dataset-specific | dataset-specific | dataset-specific | dataset-specific | dataset-specific | dataset-specific | 35 | https://github.com/topics/options-data |

## Local entitlement probes

The probes below intentionally omit API keys and raw payload bodies.

```json
{
  "alpha_vantage": {
    "authenticated": true,
    "configured": true,
    "historical_options_rows": 0,
    "http_status": 200,
    "latency_ms": 1005,
    "message_type": "Information",
    "status": "ENTITLEMENT_OR_PREMIUM_LIMIT"
  },
  "finnhub": {
    "authenticated": false,
    "configured": true,
    "expiration_count": 0,
    "http_status": 401,
    "latency_ms": 958,
    "option_chain_rows": 0,
    "status": "AUTH_OR_ENTITLEMENT_FAILED"
  },
  "yfinance": {
    "current_chain_available": true,
    "expiration_count": 28,
    "first_underlying_bar": "2026-08-28 09:30:00-04:00",
    "has_greeks": false,
    "has_implied_volatility": true,
    "has_open_interest": true,
    "historical_chain_snapshots_available": false,
    "last_underlying_bar": "2026-09-03 15:55:00-04:00",
    "latency_ms": 1915,
    "sample_call_rows": 90,
    "sample_expiration": "2026-09-03",
    "status": "AVAILABLE",
    "underlying_5m_available": true,
    "underlying_rows": 390
  }
}
```

## Current conclusion

No currently configured free/no-signup source produced historical option-chain/OI/IV/Greeks rows suitable for a strict H1/H2 GEX reconstruction. The pipeline therefore keeps historical option chains empty unless a valid entitled source is added, uses yfinance only for recent underlying 5m candles, uses the local live archive only as H3 partial structure validation, and produces H4 price-only controls.
