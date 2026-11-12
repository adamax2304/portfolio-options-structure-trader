# Provider Freshness Report - 2026-09-30

Generated: 2026-09-30T20:15:41.459762+00:00

This report measures free candle-data usability only. It does not change strategy logic, gates, weights, stops, targets, sizing, or lane rules.

## Summary

- Valid scans by candle provider: {"YFINANCE": {"stale_scans": 290, "valid_scans": 933}}
- Average candle publication lag: 144.1623 seconds
- Median/P95/max lag: 133.3663 / 282.4177 / 299.0399 seconds
- Fallback success rate: 0
- Cross-provider conflicts: 0

## Symbol Reliability

| symbol | tier | valid_scans | stale_scans | primary_provider | fallback_success | avg_lag | p95_lag | reliability |
|---|---|---:|---:|---|---:|---:|---:|---:|
| AAPL | tier_2_liquid_growth | 17 | 6 | YFINANCE | 0 | 161.06 | 279.16 | 0.7391 |
| AMD | tier_1_core | 38 | 9 | YFINANCE | 0 | 143.1 | 261.5 | 0.8085 |
| AMZN | tier_2_liquid_growth | 16 | 7 | YFINANCE | 0 | 120.35 | 258.21 | 0.6957 |
| ARKK | tier_4_etfs_macro | 17 | 1 | YFINANCE | 0 | 152.21 | 256.76 | 0.9444 |
| ARM | tier_2_liquid_growth | 18 | 5 | YFINANCE | 0 | 112.86 | 243.91 | 0.7826 |
| AVGO | tier_2_liquid_growth | 18 | 5 | YFINANCE | 0 | 120.37 | 268.21 | 0.7826 |
| BE | tier_3_high_beta_theme | 11 | 7 | YFINANCE | 0 | 154.48 | 289.74 | 0.6111 |
| CEG | tier_3_high_beta_theme | 11 | 7 | YFINANCE | 0 | 147.88 | 270.28 | 0.6111 |
| CLSK | tier_3_high_beta_theme | 12 | 6 | YFINANCE | 0 | 167.46 | 287.65 | 0.6667 |
| COIN | tier_2_liquid_growth | 12 | 11 | YFINANCE | 0 | 133.59 | 279.95 | 0.5217 |
| CRWD | tier_2_liquid_growth | 9 | 12 | YFINANCE | 0 | 127.46 | 264.02 | 0.4286 |
| CRWV | tier_3_high_beta_theme | 11 | 7 | YFINANCE | 0 | 151.64 | 255.48 | 0.6111 |
| DDOG | tier_2_liquid_growth | 16 | 7 | YFINANCE | 0 | 118.64 | 246.57 | 0.6957 |
| ETN | tier_3_high_beta_theme | 16 | 2 | YFINANCE | 0 | 136.8 | 259.54 | 0.8889 |
| GOOGL | tier_2_liquid_growth | 16 | 7 | YFINANCE | 0 | 128.4 | 276.66 | 0.6957 |
| HOOD | tier_1_core | 30 | 17 | YFINANCE | 0 | 162.21 | 274.5 | 0.6383 |
| INTC | tier_2_liquid_growth | 13 | 10 | YFINANCE | 0 | 146.04 | 262.24 | 0.5652 |
| IONQ | tier_3_high_beta_theme | 10 | 8 | YFINANCE | 0 | 148.95 | 261.66 | 0.5556 |
| IWM | tier_1_core | 45 | 2 | YFINANCE | 0 | 144.5 | 260.15 | 0.9574 |
| KRE | tier_4_etfs_macro | 17 | 1 | YFINANCE | 0 | 177.95 | 270.43 | 0.9444 |
| MARA | tier_3_high_beta_theme | 13 | 5 | YFINANCE | 0 | 160.4 | 278.64 | 0.7222 |
| META | tier_2_liquid_growth | 16 | 7 | YFINANCE | 0 | 160.52 | 290.03 | 0.6957 |
| MSFT | tier_2_liquid_growth | 16 | 7 | YFINANCE | 0 | 167.23 | 284.4 | 0.6957 |
| MSTR | tier_2_liquid_growth | 18 | 5 | YFINANCE | 0 | 129.18 | 264.18 | 0.7826 |
| MU | tier_2_liquid_growth | 13 | 10 | YFINANCE | 0 | 123.34 | 247.96 | 0.5652 |
| NET | tier_2_liquid_growth | 17 | 6 | YFINANCE | 0 | 132.23 | 272.67 | 0.7391 |
| NNE | tier_3_high_beta_theme | 16 | 2 | YFINANCE | 0 | 147.22 | 255.72 | 0.8889 |
| OKLO | tier_1_core | 35 | 12 | YFINANCE | 0 | 152.41 | 270.9 | 0.7447 |
| PLTR | tier_1_core | 39 | 8 | YFINANCE | 0 | 147.61 | 267.82 | 0.8298 |
| QBTS | tier_3_high_beta_theme | 17 | 1 | YFINANCE | 0 | 143.57 | 270.89 | 0.9444 |
| QQQ | tier_1_core | 36 | 11 | YFINANCE | 0 | 132.6 | 250.91 | 0.766 |
| RGTI | tier_3_high_beta_theme | 15 | 3 | YFINANCE | 0 | 138.88 | 266.93 | 0.8333 |
| RIOT | tier_3_high_beta_theme | 14 | 4 | YFINANCE | 0 | 163.72 | 282.01 | 0.7778 |
| RIVN | tier_3_high_beta_theme | 14 | 4 | YFINANCE | 0 | 153.18 | 275.7 | 0.7778 |
| RKLB | tier_3_high_beta_theme | 10 | 8 | YFINANCE | 0 | 158.83 | 280.45 | 0.5556 |
| SMCI | tier_2_liquid_growth | 14 | 9 | YFINANCE | 0 | 134.12 | 274.0 | 0.6087 |
| SMR | tier_3_high_beta_theme | 15 | 3 | YFINANCE | 0 | 145.06 | 258.43 | 0.8333 |
| SNOW | tier_2_liquid_growth | 11 | 12 | YFINANCE | 0 | 108.07 | 233.47 | 0.4783 |
| SOFI | tier_3_high_beta_theme | 17 | 1 | YFINANCE | 0 | 150.19 | 272.98 | 0.9444 |
| SOXX | tier_4_etfs_macro | 15 | 3 | YFINANCE | 0 | 158.24 | 260.1 | 0.8333 |
| SPY | tier_1_core | 41 | 6 | YFINANCE | 0 | 135.63 | 288.52 | 0.8723 |
| TSLA | tier_1_core | 34 | 13 | YFINANCE | 0 | 148.1 | 262.8 | 0.7234 |
| TSM | tier_2_liquid_growth | 20 | 3 | YFINANCE | 0 | 137.55 | 257.22 | 0.8696 |
| VRT | tier_3_high_beta_theme | 14 | 4 | YFINANCE | 0 | 142.64 | 265.91 | 0.7778 |
| XBI | tier_4_etfs_macro | 12 | 6 | YFINANCE | 0 | 160.86 | 265.83 | 0.6667 |
| XLE | tier_4_etfs_macro | 17 | 1 | YFINANCE | 0 | 147.62 | 243.75 | 0.9444 |
| XLF | tier_4_etfs_macro | 17 | 1 | YFINANCE | 0 | 151.52 | 281.05 | 0.9444 |
| XLI | tier_4_etfs_macro | 18 | 0 | YFINANCE | 0 | 144.57 | 248.18 | 1.0 |
| XLK | tier_4_etfs_macro | 16 | 2 | YFINANCE | 0 | 146.75 | 274.4 | 0.8889 |
| XLU | tier_4_etfs_macro | 15 | 0 | YFINANCE | 0 | 146.76 | 252.4 | 1.0 |
| XLV | tier_4_etfs_macro | 15 | 3 | YFINANCE | 0 | 159.67 | 251.04 | 0.8333 |

## Recommendation

Keep Yahoo as the bulk OHLCV source, Finnhub as quote freshness confirmation, and Alpha Vantage as a Tier 1 fallback only until a larger real-time sample proves a better free priority order.
