# Provider Freshness Report - 2026-09-29

Generated: 2026-09-29T20:15:29.848027+00:00

This report measures free candle-data usability only. It does not change strategy logic, gates, weights, stops, targets, sizing, or lane rules.

## Summary

- Valid scans by candle provider: {"YFINANCE": {"stale_scans": 383, "valid_scans": 1000}}
- Average candle publication lag: 145.877 seconds
- Median/P95/max lag: 138.2478 / 284.1929 / 299.0925 seconds
- Fallback success rate: 0
- Cross-provider conflicts: 0

## Symbol Reliability

| symbol | tier | valid_scans | stale_scans | primary_provider | fallback_success | avg_lag | p95_lag | reliability |
|---|---|---:|---:|---|---:|---:|---:|---:|
| AAPL | tier_2_liquid_growth | 20 | 9 | YFINANCE | 0 | 145.13 | 276.0 | 0.6897 |
| AMD | tier_1_core | 33 | 22 | YFINANCE | 0 | 156.66 | 284.75 | 0.6 |
| AMZN | tier_2_liquid_growth | 27 | 2 | YFINANCE | 0 | 146.9 | 272.96 | 0.931 |
| ARKK | tier_4_etfs_macro | 11 | 7 | YFINANCE | 0 | 162.65 | 291.38 | 0.6111 |
| ARM | tier_2_liquid_growth | 11 | 18 | YFINANCE | 0 | 133.17 | 295.89 | 0.3793 |
| AVGO | tier_2_liquid_growth | 16 | 10 | YFINANCE | 0 | 154.05 | 273.75 | 0.6154 |
| BE | tier_3_high_beta_theme | 7 | 11 | YFINANCE | 0 | 143.91 | 265.07 | 0.3889 |
| CEG | tier_3_high_beta_theme | 14 | 4 | YFINANCE | 0 | 176.49 | 292.51 | 0.7778 |
| CLSK | tier_3_high_beta_theme | 8 | 10 | YFINANCE | 0 | 139.19 | 259.58 | 0.4444 |
| COIN | tier_2_liquid_growth | 24 | 5 | YFINANCE | 0 | 134.12 | 279.65 | 0.8276 |
| CRWD | tier_2_liquid_growth | 16 | 10 | YFINANCE | 0 | 144.66 | 283.97 | 0.6154 |
| CRWV | tier_3_high_beta_theme | 8 | 10 | YFINANCE | 0 | 149.0 | 269.6 | 0.4444 |
| DDOG | tier_2_liquid_growth | 14 | 15 | YFINANCE | 0 | 137.55 | 291.79 | 0.4828 |
| ETN | tier_3_high_beta_theme | 13 | 5 | YFINANCE | 0 | 159.12 | 276.94 | 0.7222 |
| GOOGL | tier_2_liquid_growth | 25 | 4 | YFINANCE | 0 | 139.29 | 269.95 | 0.8621 |
| HOOD | tier_1_core | 34 | 21 | YFINANCE | 0 | 154.47 | 282.37 | 0.6182 |
| INTC | tier_2_liquid_growth | 15 | 14 | YFINANCE | 0 | 128.08 | 245.82 | 0.5172 |
| IONQ | tier_3_high_beta_theme | 8 | 10 | YFINANCE | 0 | 138.3 | 262.08 | 0.4444 |
| IWM | tier_1_core | 47 | 8 | YFINANCE | 0 | 154.33 | 278.89 | 0.8545 |
| KRE | tier_4_etfs_macro | 17 | 1 | YFINANCE | 0 | 129.05 | 237.5 | 0.9444 |
| MARA | tier_3_high_beta_theme | 7 | 9 | YFINANCE | 0 | 138.57 | 252.59 | 0.4375 |
| META | tier_2_liquid_growth | 14 | 15 | YFINANCE | 0 | 147.49 | 281.72 | 0.4828 |
| MSFT | tier_2_liquid_growth | 16 | 13 | YFINANCE | 0 | 150.99 | 282.46 | 0.5517 |
| MSTR | tier_2_liquid_growth | 25 | 4 | YFINANCE | 0 | 139.7 | 283.22 | 0.8621 |
| MU | tier_2_liquid_growth | 14 | 15 | YFINANCE | 0 | 112.78 | 233.78 | 0.4828 |
| NET | tier_2_liquid_growth | 21 | 8 | YFINANCE | 0 | 138.07 | 287.12 | 0.7241 |
| NNE | tier_3_high_beta_theme | 16 | 2 | YFINANCE | 0 | 157.02 | 278.21 | 0.8889 |
| OKLO | tier_1_core | 36 | 19 | YFINANCE | 0 | 160.29 | 291.56 | 0.6545 |
| PLTR | tier_1_core | 47 | 8 | YFINANCE | 0 | 155.02 | 286.57 | 0.8545 |
| QBTS | tier_3_high_beta_theme | 16 | 2 | YFINANCE | 0 | 149.09 | 269.03 | 0.8889 |
| QQQ | tier_1_core | 44 | 11 | YFINANCE | 0 | 145.58 | 271.51 | 0.8 |
| RGTI | tier_3_high_beta_theme | 14 | 4 | YFINANCE | 0 | 143.51 | 266.43 | 0.7778 |
| RIOT | tier_3_high_beta_theme | 17 | 1 | YFINANCE | 0 | 135.88 | 256.35 | 0.9444 |
| RIVN | tier_3_high_beta_theme | 16 | 2 | YFINANCE | 0 | 141.83 | 264.0 | 0.8889 |
| RKLB | tier_3_high_beta_theme | 12 | 6 | YFINANCE | 0 | 146.53 | 258.1 | 0.6667 |
| SMCI | tier_2_liquid_growth | 16 | 13 | YFINANCE | 0 | 149.86 | 279.46 | 0.5517 |
| SMR | tier_3_high_beta_theme | 15 | 3 | YFINANCE | 0 | 142.95 | 258.21 | 0.8333 |
| SNOW | tier_2_liquid_growth | 15 | 14 | YFINANCE | 0 | 147.44 | 291.08 | 0.5172 |
| SOFI | tier_3_high_beta_theme | 15 | 3 | YFINANCE | 0 | 146.55 | 261.18 | 0.8333 |
| SOXX | tier_4_etfs_macro | 12 | 6 | YFINANCE | 0 | 134.53 | 277.94 | 0.6667 |
| SPY | tier_1_core | 43 | 12 | YFINANCE | 0 | 128.79 | 244.95 | 0.7818 |
| TSLA | tier_1_core | 52 | 3 | YFINANCE | 0 | 162.39 | 283.51 | 0.9455 |
| TSM | tier_2_liquid_growth | 24 | 5 | YFINANCE | 0 | 118.07 | 238.85 | 0.8276 |
| VRT | tier_3_high_beta_theme | 15 | 3 | YFINANCE | 0 | 159.37 | 283.53 | 0.8333 |
| XBI | tier_4_etfs_macro | 15 | 3 | YFINANCE | 0 | 140.4 | 283.73 | 0.8333 |
| XLE | tier_4_etfs_macro | 15 | 3 | YFINANCE | 0 | 145.66 | 263.53 | 0.8333 |
| XLF | tier_4_etfs_macro | 18 | 0 | YFINANCE | 0 | 141.57 | 257.79 | 1.0 |
| XLI | tier_4_etfs_macro | 17 | 1 | YFINANCE | 0 | 149.95 | 269.61 | 0.9444 |
| XLK | tier_4_etfs_macro | 15 | 3 | YFINANCE | 0 | 135.86 | 250.48 | 0.8333 |
| XLU | tier_4_etfs_macro | 13 | 2 | YFINANCE | 0 | 161.38 | 284.23 | 0.8667 |
| XLV | tier_4_etfs_macro | 17 | 1 | YFINANCE | 0 | 154.73 | 275.89 | 0.9444 |

## Recommendation

Keep Yahoo as the bulk OHLCV source, Finnhub as quote freshness confirmation, and Alpha Vantage as a Tier 1 fallback only until a larger real-time sample proves a better free priority order.
