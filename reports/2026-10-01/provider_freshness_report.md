# Provider Freshness Report - 2026-10-01

Generated: 2026-10-01T21:12:40.779921+00:00

This report measures free candle-data usability only. It does not change strategy logic, gates, weights, stops, targets, sizing, or lane rules.

## Summary

- Valid scans by candle provider: {"YFINANCE": {"stale_scans": 266, "valid_scans": 558}}
- Average candle publication lag: 155.4509 seconds
- Median/P95/max lag: 157.4995 / 286.3612 / 298.7789 seconds
- Fallback success rate: 0
- Cross-provider conflicts: 0

## Symbol Reliability

| symbol | tier | valid_scans | stale_scans | primary_provider | fallback_success | avg_lag | p95_lag | reliability |
|---|---|---:|---:|---|---:|---:|---:|---:|
| AAPL | tier_2_liquid_growth | 11 | 6 | YFINANCE | 0 | 156.27 | 282.45 | 0.6471 |
| AMD | tier_1_core | 9 | 20 | YFINANCE | 0 | 170.15 | 287.33 | 0.3103 |
| AMZN | tier_2_liquid_growth | 12 | 5 | YFINANCE | 0 | 171.16 | 268.85 | 0.7059 |
| ARKK | tier_4_etfs_macro | 9 | 3 | YFINANCE | 0 | 131.77 | 271.19 | 0.75 |
| ARM | tier_2_liquid_growth | 13 | 4 | YFINANCE | 0 | 182.8 | 261.62 | 0.7647 |
| AVGO | tier_2_liquid_growth | 13 | 1 | YFINANCE | 0 | 153.23 | 239.26 | 0.9286 |
| BE | tier_3_high_beta_theme | 5 | 7 | YFINANCE | 0 | 178.25 | 280.33 | 0.4167 |
| CEG | tier_3_high_beta_theme | 6 | 6 | YFINANCE | 0 | 153.54 | 294.52 | 0.5 |
| CLSK | tier_3_high_beta_theme | 10 | 2 | YFINANCE | 0 | 174.25 | 276.77 | 0.8333 |
| COIN | tier_2_liquid_growth | 10 | 7 | YFINANCE | 0 | 164.58 | 268.54 | 0.5882 |
| CRWD | tier_2_liquid_growth | 11 | 6 | YFINANCE | 0 | 159.32 | 244.24 | 0.6471 |
| CRWV | tier_3_high_beta_theme | 5 | 7 | YFINANCE | 0 | 188.07 | 285.08 | 0.4167 |
| DDOG | tier_2_liquid_growth | 10 | 7 | YFINANCE | 0 | 169.75 | 257.44 | 0.5882 |
| ETN | tier_3_high_beta_theme | 8 | 4 | YFINANCE | 0 | 194.93 | 290.22 | 0.6667 |
| GOOGL | tier_2_liquid_growth | 14 | 3 | YFINANCE | 0 | 143.81 | 257.67 | 0.8235 |
| HOOD | tier_1_core | 15 | 14 | YFINANCE | 0 | 167.99 | 276.55 | 0.5172 |
| INTC | tier_2_liquid_growth | 10 | 7 | YFINANCE | 0 | 205.58 | 296.67 | 0.5882 |
| IONQ | tier_3_high_beta_theme | 5 | 7 | YFINANCE | 0 | 122.77 | 274.54 | 0.4167 |
| IWM | tier_1_core | 21 | 8 | YFINANCE | 0 | 156.27 | 260.52 | 0.7241 |
| KRE | tier_4_etfs_macro | 10 | 2 | YFINANCE | 0 | 104.81 | 165.76 | 0.8333 |
| MARA | tier_3_high_beta_theme | 12 | 0 | YFINANCE | 0 | 164.41 | 270.12 | 1.0 |
| META | tier_2_liquid_growth | 14 | 3 | YFINANCE | 0 | 156.65 | 261.96 | 0.8235 |
| MSFT | tier_2_liquid_growth | 14 | 3 | YFINANCE | 0 | 145.58 | 257.4 | 0.8235 |
| MSTR | tier_2_liquid_growth | 8 | 9 | YFINANCE | 0 | 161.48 | 255.04 | 0.4706 |
| MU | tier_2_liquid_growth | 4 | 13 | YFINANCE | 0 | 196.2 | 267.87 | 0.2353 |
| NET | tier_2_liquid_growth | 10 | 7 | YFINANCE | 0 | 173.6 | 256.54 | 0.5882 |
| NNE | tier_3_high_beta_theme | 11 | 1 | YFINANCE | 0 | 114.24 | 269.25 | 0.9167 |
| OKLO | tier_1_core | 20 | 9 | YFINANCE | 0 | 154.76 | 268.11 | 0.6897 |
| PLTR | tier_1_core | 15 | 10 | YFINANCE | 0 | 167.12 | 286.11 | 0.6 |
| QBTS | tier_3_high_beta_theme | 11 | 1 | YFINANCE | 0 | 143.42 | 286.71 | 0.9167 |
| QQQ | tier_1_core | 18 | 11 | YFINANCE | 0 | 157.35 | 245.55 | 0.6207 |
| RGTI | tier_3_high_beta_theme | 12 | 0 | YFINANCE | 0 | 137.08 | 283.48 | 1.0 |
| RIOT | tier_3_high_beta_theme | 8 | 4 | YFINANCE | 0 | 168.86 | 273.46 | 0.6667 |
| RIVN | tier_3_high_beta_theme | 12 | 0 | YFINANCE | 0 | 160.63 | 267.04 | 1.0 |
| RKLB | tier_3_high_beta_theme | 6 | 6 | YFINANCE | 0 | 174.0 | 261.21 | 0.5 |
| SMCI | tier_2_liquid_growth | 12 | 5 | YFINANCE | 0 | 154.52 | 243.13 | 0.7059 |
| SMR | tier_3_high_beta_theme | 9 | 3 | YFINANCE | 0 | 118.44 | 272.34 | 0.75 |
| SNOW | tier_2_liquid_growth | 8 | 9 | YFINANCE | 0 | 171.42 | 263.11 | 0.4706 |
| SOFI | tier_3_high_beta_theme | 11 | 1 | YFINANCE | 0 | 182.02 | 264.9 | 0.9167 |
| SOXX | tier_4_etfs_macro | 6 | 6 | YFINANCE | 0 | 72.46 | 130.91 | 0.5 |
| SPY | tier_1_core | 23 | 6 | YFINANCE | 0 | 132.22 | 231.81 | 0.7931 |
| TSLA | tier_1_core | 16 | 13 | YFINANCE | 0 | 160.87 | 267.41 | 0.5517 |
| TSM | tier_2_liquid_growth | 14 | 3 | YFINANCE | 0 | 197.41 | 288.94 | 0.8235 |
| VRT | tier_3_high_beta_theme | 8 | 4 | YFINANCE | 0 | 175.98 | 290.81 | 0.6667 |
| XBI | tier_4_etfs_macro | 9 | 3 | YFINANCE | 0 | 94.94 | 160.8 | 0.75 |
| XLE | tier_4_etfs_macro | 10 | 2 | YFINANCE | 0 | 120.53 | 283.0 | 0.8333 |
| XLF | tier_4_etfs_macro | 9 | 3 | YFINANCE | 0 | 138.96 | 295.0 | 0.75 |
| XLI | tier_4_etfs_macro | 9 | 3 | YFINANCE | 0 | 102.76 | 169.58 | 0.75 |
| XLK | tier_4_etfs_macro | 10 | 2 | YFINANCE | 0 | 125.19 | 289.8 | 0.8333 |
| XLU | tier_4_etfs_macro | 11 | 1 | YFINANCE | 0 | 122.96 | 223.76 | 0.9167 |
| XLV | tier_4_etfs_macro | 11 | 1 | YFINANCE | 0 | 110.66 | 193.48 | 0.9167 |

## Recommendation

Keep Yahoo as the bulk OHLCV source, Finnhub as quote freshness confirmation, and Alpha Vantage as a Tier 1 fallback only until a larger real-time sample proves a better free priority order.
