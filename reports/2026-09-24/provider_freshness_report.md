# Provider Freshness Report - 2026-09-24

Generated: 2026-09-24T20:15:21.707924+00:00

This report measures free candle-data usability only. It does not change strategy logic, gates, weights, stops, targets, sizing, or lane rules.

## Summary

- Valid scans by candle provider: {"YFINANCE": {"stale_scans": 366, "valid_scans": 921}}
- Average candle publication lag: 159.0568 seconds
- Median/P95/max lag: 177.0672 / 285.1421 / 299.2095 seconds
- Fallback success rate: 0
- Cross-provider conflicts: 0

## Symbol Reliability

| symbol | tier | valid_scans | stale_scans | primary_provider | fallback_success | avg_lag | p95_lag | reliability |
|---|---|---:|---:|---|---:|---:|---:|---:|
| AAPL | tier_2_liquid_growth | 17 | 10 | YFINANCE | 0 | 156.77 | 281.25 | 0.6296 |
| AMD | tier_1_core | 15 | 34 | YFINANCE | 0 | 183.22 | 289.51 | 0.3061 |
| AMZN | tier_2_liquid_growth | 20 | 7 | YFINANCE | 0 | 140.0 | 241.18 | 0.7407 |
| ARKK | tier_4_etfs_macro | 11 | 4 | YFINANCE | 0 | 149.99 | 287.06 | 0.7333 |
| ARM | tier_2_liquid_growth | 18 | 9 | YFINANCE | 0 | 155.36 | 275.39 | 0.6667 |
| AVGO | tier_2_liquid_growth | 22 | 5 | YFINANCE | 0 | 142.14 | 249.37 | 0.8148 |
| BE | tier_3_high_beta_theme | 9 | 6 | YFINANCE | 0 | 133.96 | 243.16 | 0.6 |
| CEG | tier_3_high_beta_theme | 13 | 2 | YFINANCE | 0 | 153.0 | 255.3 | 0.8667 |
| CLSK | tier_3_high_beta_theme | 14 | 1 | YFINANCE | 0 | 131.75 | 241.96 | 0.9333 |
| COIN | tier_2_liquid_growth | 21 | 6 | YFINANCE | 0 | 153.72 | 257.02 | 0.7778 |
| CRWD | tier_2_liquid_growth | 20 | 7 | YFINANCE | 0 | 160.81 | 263.12 | 0.7407 |
| CRWV | tier_3_high_beta_theme | 9 | 6 | YFINANCE | 0 | 137.31 | 247.28 | 0.6 |
| DDOG | tier_2_liquid_growth | 15 | 12 | YFINANCE | 0 | 152.41 | 272.39 | 0.5556 |
| ETN | tier_3_high_beta_theme | 12 | 3 | YFINANCE | 0 | 140.4 | 250.04 | 0.8 |
| GOOGL | tier_2_liquid_growth | 21 | 6 | YFINANCE | 0 | 137.82 | 244.47 | 0.7778 |
| HOOD | tier_1_core | 32 | 17 | YFINANCE | 0 | 177.69 | 296.27 | 0.6531 |
| INTC | tier_2_liquid_growth | 17 | 10 | YFINANCE | 0 | 174.34 | 290.33 | 0.6296 |
| IONQ | tier_3_high_beta_theme | 5 | 10 | YFINANCE | 0 | 156.38 | 260.98 | 0.3333 |
| IWM | tier_1_core | 39 | 11 | YFINANCE | 0 | 168.2 | 278.82 | 0.78 |
| KRE | tier_4_etfs_macro | 12 | 3 | YFINANCE | 0 | 140.01 | 292.96 | 0.8 |
| MARA | tier_3_high_beta_theme | 11 | 4 | YFINANCE | 0 | 126.29 | 238.69 | 0.7333 |
| META | tier_2_liquid_growth | 20 | 7 | YFINANCE | 0 | 130.44 | 236.74 | 0.7407 |
| MSFT | tier_2_liquid_growth | 23 | 4 | YFINANCE | 0 | 149.16 | 267.56 | 0.8519 |
| MSTR | tier_2_liquid_growth | 20 | 7 | YFINANCE | 0 | 157.66 | 260.56 | 0.7407 |
| MU | tier_2_liquid_growth | 13 | 14 | YFINANCE | 0 | 159.78 | 281.81 | 0.4815 |
| NET | tier_2_liquid_growth | 19 | 8 | YFINANCE | 0 | 158.66 | 263.9 | 0.7037 |
| NNE | tier_3_high_beta_theme | 10 | 5 | YFINANCE | 0 | 157.72 | 257.19 | 0.6667 |
| NVDA | tier_1_core | 38 | 12 | YFINANCE | 0 | 174.13 | 283.55 | 0.76 |
| OKLO | tier_1_core | 32 | 17 | YFINANCE | 0 | 186.7 | 294.37 | 0.6531 |
| PLTR | tier_1_core | 40 | 9 | YFINANCE | 0 | 183.4 | 292.38 | 0.8163 |
| QBTS | tier_3_high_beta_theme | 12 | 3 | YFINANCE | 0 | 170.43 | 278.12 | 0.8 |
| QQQ | tier_1_core | 43 | 7 | YFINANCE | 0 | 162.14 | 272.67 | 0.86 |
| RGTI | tier_3_high_beta_theme | 9 | 5 | YFINANCE | 0 | 168.1 | 265.38 | 0.6429 |
| RIOT | tier_3_high_beta_theme | 9 | 6 | YFINANCE | 0 | 129.23 | 240.23 | 0.6 |
| RIVN | tier_3_high_beta_theme | 12 | 3 | YFINANCE | 0 | 123.81 | 237.22 | 0.8 |
| RKLB | tier_3_high_beta_theme | 8 | 7 | YFINANCE | 0 | 149.14 | 234.27 | 0.5333 |
| SMCI | tier_2_liquid_growth | 18 | 9 | YFINANCE | 0 | 148.15 | 253.56 | 0.6667 |
| SMR | tier_3_high_beta_theme | 6 | 8 | YFINANCE | 0 | 155.94 | 258.34 | 0.4286 |
| SNOW | tier_2_liquid_growth | 22 | 5 | YFINANCE | 0 | 148.7 | 268.33 | 0.8148 |
| SOFI | tier_3_high_beta_theme | 13 | 2 | YFINANCE | 0 | 121.72 | 234.53 | 0.8667 |
| SOXX | tier_4_etfs_macro | 9 | 6 | YFINANCE | 0 | 152.75 | 290.27 | 0.6 |
| SPY | tier_1_core | 36 | 14 | YFINANCE | 0 | 151.01 | 265.11 | 0.72 |
| TSLA | tier_1_core | 40 | 10 | YFINANCE | 0 | 177.45 | 286.76 | 0.8 |
| TSM | tier_2_liquid_growth | 19 | 8 | YFINANCE | 0 | 166.51 | 287.26 | 0.7037 |
| VRT | tier_3_high_beta_theme | 8 | 7 | YFINANCE | 0 | 144.61 | 253.23 | 0.5333 |
| XBI | tier_4_etfs_macro | 11 | 4 | YFINANCE | 0 | 156.38 | 293.63 | 0.7333 |
| XLE | tier_4_etfs_macro | 14 | 1 | YFINANCE | 0 | 178.69 | 291.33 | 0.9333 |
| XLF | tier_4_etfs_macro | 11 | 4 | YFINANCE | 0 | 176.03 | 284.49 | 0.7333 |
| XLI | tier_4_etfs_macro | 13 | 2 | YFINANCE | 0 | 161.58 | 279.16 | 0.8667 |
| XLK | tier_4_etfs_macro | 14 | 1 | YFINANCE | 0 | 172.69 | 280.92 | 0.9333 |
| XLU | tier_4_etfs_macro | 12 | 3 | YFINANCE | 0 | 147.48 | 285.14 | 0.8 |
| XLV | tier_4_etfs_macro | 14 | 1 | YFINANCE | 0 | 164.37 | 282.98 | 0.9333 |

## Recommendation

Keep Yahoo as the bulk OHLCV source, Finnhub as quote freshness confirmation, and Alpha Vantage as a Tier 1 fallback only until a larger real-time sample proves a better free priority order.
