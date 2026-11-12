# Provider Freshness Report - 2026-09-25

Generated: 2026-09-25T20:15:13.536526+00:00

This report measures free candle-data usability only. It does not change strategy logic, gates, weights, stops, targets, sizing, or lane rules.

## Summary

- Valid scans by candle provider: {"YFINANCE": {"stale_scans": 303, "valid_scans": 832}}
- Average candle publication lag: 136.9647 seconds
- Median/P95/max lag: 126.5293 / 277.9986 / 298.3408 seconds
- Fallback success rate: 0
- Cross-provider conflicts: 0

## Symbol Reliability

| symbol | tier | valid_scans | stale_scans | primary_provider | fallback_success | avg_lag | p95_lag | reliability |
|---|---|---:|---:|---|---:|---:|---:|---:|
| AAPL | tier_2_liquid_growth | 17 | 6 | YFINANCE | 0 | 113.76 | 260.45 | 0.7391 |
| AMD | tier_1_core | 25 | 16 | YFINANCE | 0 | 104.12 | 254.73 | 0.6098 |
| AMZN | tier_2_liquid_growth | 21 | 2 | YFINANCE | 0 | 129.19 | 274.38 | 0.913 |
| ARKK | tier_4_etfs_macro | 12 | 3 | YFINANCE | 0 | 173.99 | 279.21 | 0.8 |
| ARM | tier_2_liquid_growth | 9 | 14 | YFINANCE | 0 | 135.09 | 257.17 | 0.3913 |
| AVGO | tier_2_liquid_growth | 17 | 6 | YFINANCE | 0 | 136.78 | 279.69 | 0.7391 |
| BE | tier_3_high_beta_theme | 9 | 6 | YFINANCE | 0 | 155.22 | 235.91 | 0.6 |
| CEG | tier_3_high_beta_theme | 13 | 2 | YFINANCE | 0 | 146.04 | 243.33 | 0.8667 |
| CLSK | tier_3_high_beta_theme | 11 | 2 | YFINANCE | 0 | 184.61 | 278.14 | 0.8462 |
| COIN | tier_2_liquid_growth | 18 | 5 | YFINANCE | 0 | 145.9 | 285.92 | 0.7826 |
| CRWD | tier_2_liquid_growth | 14 | 9 | YFINANCE | 0 | 151.16 | 248.49 | 0.6087 |
| CRWV | tier_3_high_beta_theme | 10 | 5 | YFINANCE | 0 | 161.33 | 251.96 | 0.6667 |
| DDOG | tier_2_liquid_growth | 15 | 8 | YFINANCE | 0 | 130.42 | 246.71 | 0.6522 |
| ETN | tier_3_high_beta_theme | 13 | 2 | YFINANCE | 0 | 177.81 | 288.74 | 0.8667 |
| GOOGL | tier_2_liquid_growth | 16 | 7 | YFINANCE | 0 | 132.82 | 277.36 | 0.6957 |
| HOOD | tier_1_core | 26 | 15 | YFINANCE | 0 | 108.39 | 259.0 | 0.6341 |
| INTC | tier_2_liquid_growth | 10 | 13 | YFINANCE | 0 | 148.29 | 238.41 | 0.4348 |
| IONQ | tier_3_high_beta_theme | 6 | 9 | YFINANCE | 0 | 158.69 | 257.54 | 0.4 |
| IWM | tier_1_core | 40 | 1 | YFINANCE | 0 | 98.12 | 242.01 | 0.9756 |
| KRE | tier_4_etfs_macro | 11 | 4 | YFINANCE | 0 | 166.15 | 280.74 | 0.7333 |
| MARA | tier_3_high_beta_theme | 14 | 1 | YFINANCE | 0 | 155.88 | 229.33 | 0.9333 |
| META | tier_2_liquid_growth | 16 | 7 | YFINANCE | 0 | 123.41 | 269.0 | 0.6957 |
| MSFT | tier_2_liquid_growth | 16 | 7 | YFINANCE | 0 | 117.55 | 264.05 | 0.6957 |
| MSTR | tier_2_liquid_growth | 20 | 3 | YFINANCE | 0 | 151.97 | 288.26 | 0.8696 |
| MU | tier_2_liquid_growth | 14 | 9 | YFINANCE | 0 | 139.82 | 263.71 | 0.6087 |
| NET | tier_2_liquid_growth | 10 | 13 | YFINANCE | 0 | 141.66 | 252.29 | 0.4348 |
| NNE | tier_3_high_beta_theme | 12 | 3 | YFINANCE | 0 | 151.25 | 247.98 | 0.8 |
| NVDA | tier_1_core | 31 | 4 | YFINANCE | 0 | 105.23 | 248.32 | 0.8857 |
| OKLO | tier_1_core | 33 | 8 | YFINANCE | 0 | 110.13 | 259.85 | 0.8049 |
| PLTR | tier_1_core | 35 | 6 | YFINANCE | 0 | 106.72 | 257.85 | 0.8537 |
| QBTS | tier_3_high_beta_theme | 12 | 3 | YFINANCE | 0 | 147.99 | 261.83 | 0.8 |
| QQQ | tier_1_core | 28 | 13 | YFINANCE | 0 | 95.67 | 235.44 | 0.6829 |
| RGTI | tier_3_high_beta_theme | 11 | 4 | YFINANCE | 0 | 145.13 | 258.95 | 0.7333 |
| RIOT | tier_3_high_beta_theme | 8 | 7 | YFINANCE | 0 | 160.76 | 231.27 | 0.5333 |
| RIVN | tier_3_high_beta_theme | 11 | 4 | YFINANCE | 0 | 154.02 | 227.61 | 0.7333 |
| RKLB | tier_3_high_beta_theme | 8 | 7 | YFINANCE | 0 | 151.63 | 222.96 | 0.5333 |
| SMCI | tier_2_liquid_growth | 14 | 9 | YFINANCE | 0 | 142.58 | 283.08 | 0.6087 |
| SMR | tier_3_high_beta_theme | 13 | 2 | YFINANCE | 0 | 154.05 | 251.55 | 0.8667 |
| SNOW | tier_2_liquid_growth | 16 | 7 | YFINANCE | 0 | 136.92 | 254.56 | 0.6957 |
| SOFI | tier_3_high_beta_theme | 14 | 1 | YFINANCE | 0 | 151.8 | 226.09 | 0.9333 |
| SOXX | tier_4_etfs_macro | 11 | 4 | YFINANCE | 0 | 177.93 | 282.54 | 0.7333 |
| SPY | tier_1_core | 23 | 18 | YFINANCE | 0 | 175.05 | 294.62 | 0.561 |
| TSLA | tier_1_core | 24 | 17 | YFINANCE | 0 | 110.86 | 254.17 | 0.5854 |
| TSM | tier_2_liquid_growth | 18 | 5 | YFINANCE | 0 | 145.83 | 270.82 | 0.7826 |
| VRT | tier_3_high_beta_theme | 12 | 3 | YFINANCE | 0 | 173.34 | 249.69 | 0.8 |
| XBI | tier_4_etfs_macro | 12 | 3 | YFINANCE | 0 | 162.35 | 276.5 | 0.8 |
| XLE | tier_4_etfs_macro | 15 | 0 | YFINANCE | 0 | 157.58 | 270.0 | 1.0 |
| XLF | tier_4_etfs_macro | 14 | 1 | YFINANCE | 0 | 154.47 | 267.54 | 0.9333 |
| XLI | tier_4_etfs_macro | 14 | 1 | YFINANCE | 0 | 160.8 | 272.54 | 0.9333 |
| XLK | tier_4_etfs_macro | 15 | 0 | YFINANCE | 0 | 150.39 | 264.21 | 1.0 |
| XLU | tier_4_etfs_macro | 13 | 2 | YFINANCE | 0 | 171.45 | 277.65 | 0.8667 |
| XLV | tier_4_etfs_macro | 12 | 3 | YFINANCE | 0 | 166.12 | 275.08 | 0.8 |

## Recommendation

Keep Yahoo as the bulk OHLCV source, Finnhub as quote freshness confirmation, and Alpha Vantage as a Tier 1 fallback only until a larger real-time sample proves a better free priority order.
