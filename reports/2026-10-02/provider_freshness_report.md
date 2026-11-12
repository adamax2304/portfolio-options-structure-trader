# Provider Freshness Report - 2026-10-02

Generated: 2026-10-02T20:16:14.666537+00:00

This report measures free candle-data usability only. It does not change strategy logic, gates, weights, stops, targets, sizing, or lane rules.

## Summary

- Valid scans by candle provider: {"YFINANCE": {"stale_scans": 569, "valid_scans": 1298}}
- Average candle publication lag: 141.4948 seconds
- Median/P95/max lag: 134.5881 / 284.9305 / 299.1276 seconds
- Fallback success rate: 0
- Cross-provider conflicts: 0

## Symbol Reliability

| symbol | tier | valid_scans | stale_scans | primary_provider | fallback_success | avg_lag | p95_lag | reliability |
|---|---|---:|---:|---|---:|---:|---:|---:|
| AAPL | tier_2_liquid_growth | 27 | 11 | YFINANCE | 0 | 146.79 | 287.66 | 0.7105 |
| AMD | tier_1_core | 42 | 32 | YFINANCE | 0 | 123.0 | 258.95 | 0.5676 |
| AMZN | tier_2_liquid_growth | 26 | 12 | YFINANCE | 0 | 132.93 | 261.72 | 0.6842 |
| ARKK | tier_4_etfs_macro | 23 | 2 | YFINANCE | 0 | 156.34 | 275.18 | 0.92 |
| ARM | tier_2_liquid_growth | 24 | 14 | YFINANCE | 0 | 148.51 | 274.11 | 0.6316 |
| AVGO | tier_2_liquid_growth | 27 | 11 | YFINANCE | 0 | 141.37 | 271.16 | 0.7105 |
| BE | tier_3_high_beta_theme | 17 | 8 | YFINANCE | 0 | 121.67 | 247.27 | 0.68 |
| CEG | tier_3_high_beta_theme | 15 | 7 | YFINANCE | 0 | 127.77 | 238.39 | 0.6818 |
| CLSK | tier_3_high_beta_theme | 18 | 7 | YFINANCE | 0 | 118.37 | 245.38 | 0.72 |
| COIN | tier_2_liquid_growth | 20 | 15 | YFINANCE | 0 | 140.39 | 268.95 | 0.5714 |
| CRWD | tier_2_liquid_growth | 26 | 12 | YFINANCE | 0 | 144.22 | 275.57 | 0.6842 |
| CRWV | tier_3_high_beta_theme | 10 | 15 | YFINANCE | 0 | 126.25 | 250.54 | 0.4 |
| DDOG | tier_2_liquid_growth | 30 | 8 | YFINANCE | 0 | 144.21 | 269.77 | 0.7895 |
| ETN | tier_3_high_beta_theme | 19 | 6 | YFINANCE | 0 | 131.02 | 253.63 | 0.76 |
| GOOGL | tier_2_liquid_growth | 27 | 11 | YFINANCE | 0 | 136.51 | 266.09 | 0.7105 |
| HOOD | tier_1_core | 38 | 36 | YFINANCE | 0 | 140.99 | 278.91 | 0.5135 |
| INTC | tier_2_liquid_growth | 21 | 17 | YFINANCE | 0 | 158.42 | 288.91 | 0.5526 |
| IONQ | tier_3_high_beta_theme | 8 | 17 | YFINANCE | 0 | 124.46 | 235.11 | 0.32 |
| IWM | tier_1_core | 53 | 21 | YFINANCE | 0 | 129.17 | 295.52 | 0.7162 |
| KRE | tier_4_etfs_macro | 21 | 4 | YFINANCE | 0 | 146.67 | 254.48 | 0.84 |
| MARA | tier_3_high_beta_theme | 19 | 6 | YFINANCE | 0 | 137.09 | 275.04 | 0.76 |
| META | tier_2_liquid_growth | 30 | 8 | YFINANCE | 0 | 141.46 | 282.92 | 0.7895 |
| MSFT | tier_2_liquid_growth | 35 | 3 | YFINANCE | 0 | 143.31 | 285.34 | 0.9211 |
| MSTR | tier_2_liquid_growth | 23 | 15 | YFINANCE | 0 | 139.75 | 271.86 | 0.6053 |
| MU | tier_2_liquid_growth | 21 | 17 | YFINANCE | 0 | 153.55 | 279.06 | 0.5526 |
| NET | tier_2_liquid_growth | 20 | 18 | YFINANCE | 0 | 148.2 | 279.44 | 0.5263 |
| NNE | tier_3_high_beta_theme | 20 | 5 | YFINANCE | 0 | 119.84 | 226.67 | 0.8 |
| OKLO | tier_1_core | 48 | 26 | YFINANCE | 0 | 136.47 | 274.99 | 0.6486 |
| PLTR | tier_1_core | 39 | 29 | YFINANCE | 0 | 141.64 | 266.43 | 0.5735 |
| QBTS | tier_3_high_beta_theme | 22 | 3 | YFINANCE | 0 | 132.35 | 248.03 | 0.88 |
| QQQ | tier_1_core | 55 | 19 | YFINANCE | 0 | 178.62 | 297.04 | 0.7432 |
| RGTI | tier_3_high_beta_theme | 21 | 4 | YFINANCE | 0 | 129.66 | 244.22 | 0.84 |
| RIOT | tier_3_high_beta_theme | 17 | 8 | YFINANCE | 0 | 127.56 | 271.08 | 0.68 |
| RIVN | tier_3_high_beta_theme | 19 | 6 | YFINANCE | 0 | 146.52 | 289.35 | 0.76 |
| RKLB | tier_3_high_beta_theme | 12 | 8 | YFINANCE | 0 | 154.93 | 285.46 | 0.6 |
| SMCI | tier_2_liquid_growth | 22 | 13 | YFINANCE | 0 | 144.41 | 273.97 | 0.6286 |
| SMR | tier_3_high_beta_theme | 19 | 6 | YFINANCE | 0 | 122.35 | 232.39 | 0.76 |
| SNOW | tier_2_liquid_growth | 20 | 18 | YFINANCE | 0 | 142.3 | 264.06 | 0.5263 |
| SOFI | tier_3_high_beta_theme | 23 | 2 | YFINANCE | 0 | 144.08 | 285.26 | 0.92 |
| SOXX | tier_4_etfs_macro | 19 | 6 | YFINANCE | 0 | 148.7 | 247.34 | 0.76 |
| SPY | tier_1_core | 56 | 18 | YFINANCE | 0 | 183.84 | 287.63 | 0.7568 |
| TSLA | tier_1_core | 46 | 28 | YFINANCE | 0 | 115.91 | 249.99 | 0.6216 |
| TSM | tier_2_liquid_growth | 31 | 7 | YFINANCE | 0 | 153.29 | 283.57 | 0.8158 |
| VRT | tier_3_high_beta_theme | 18 | 7 | YFINANCE | 0 | 124.1 | 235.96 | 0.72 |
| XBI | tier_4_etfs_macro | 21 | 4 | YFINANCE | 0 | 141.76 | 250.35 | 0.84 |
| XLE | tier_4_etfs_macro | 20 | 5 | YFINANCE | 0 | 141.81 | 260.26 | 0.8 |
| XLF | tier_4_etfs_macro | 24 | 1 | YFINANCE | 0 | 138.79 | 256.56 | 0.96 |
| XLI | tier_4_etfs_macro | 20 | 5 | YFINANCE | 0 | 145.5 | 265.39 | 0.8 |
| XLK | tier_4_etfs_macro | 23 | 2 | YFINANCE | 0 | 134.99 | 251.23 | 0.92 |
| XLU | tier_4_etfs_macro | 22 | 3 | YFINANCE | 0 | 153.34 | 272.83 | 0.88 |
| XLV | tier_4_etfs_macro | 21 | 4 | YFINANCE | 0 | 149.58 | 269.16 | 0.84 |

## Recommendation

Keep Yahoo as the bulk OHLCV source, Finnhub as quote freshness confirmation, and Alpha Vantage as a Tier 1 fallback only until a larger real-time sample proves a better free priority order.
