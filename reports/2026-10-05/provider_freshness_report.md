# Provider Freshness Report - 2026-10-05

Generated: 2026-10-05T20:15:43.097035+00:00

This report measures free candle-data usability only. It does not change strategy logic, gates, weights, stops, targets, sizing, or lane rules.

## Summary

- Valid scans by candle provider: {"YFINANCE": {"stale_scans": 439, "valid_scans": 1426}}
- Average candle publication lag: 162.7816 seconds
- Median/P95/max lag: 174.1472 / 281.9273 / 299.2134 seconds
- Fallback success rate: 0
- Cross-provider conflicts: 0

## Symbol Reliability

| symbol | tier | valid_scans | stale_scans | primary_provider | fallback_success | avg_lag | p95_lag | reliability |
|---|---|---:|---:|---|---:|---:|---:|---:|
| AAPL | tier_2_liquid_growth | 26 | 12 | YFINANCE | 0 | 159.61 | 269.86 | 0.6842 |
| AMD | tier_1_core | 53 | 20 | YFINANCE | 0 | 138.28 | 248.79 | 0.726 |
| AMZN | tier_2_liquid_growth | 27 | 8 | YFINANCE | 0 | 175.05 | 275.7 | 0.7714 |
| ARKK | tier_4_etfs_macro | 19 | 6 | YFINANCE | 0 | 175.28 | 281.6 | 0.76 |
| ARM | tier_2_liquid_growth | 34 | 4 | YFINANCE | 0 | 177.37 | 286.56 | 0.8947 |
| AVGO | tier_2_liquid_growth | 28 | 10 | YFINANCE | 0 | 170.25 | 270.38 | 0.7368 |
| BE | tier_3_high_beta_theme | 14 | 11 | YFINANCE | 0 | 172.39 | 271.65 | 0.56 |
| CEG | tier_3_high_beta_theme | 18 | 7 | YFINANCE | 0 | 179.62 | 261.5 | 0.72 |
| CLSK | tier_3_high_beta_theme | 19 | 6 | YFINANCE | 0 | 169.75 | 269.95 | 0.76 |
| COIN | tier_2_liquid_growth | 24 | 14 | YFINANCE | 0 | 180.81 | 282.2 | 0.6316 |
| CRWD | tier_2_liquid_growth | 35 | 3 | YFINANCE | 0 | 183.76 | 280.93 | 0.9211 |
| CRWV | tier_3_high_beta_theme | 16 | 9 | YFINANCE | 0 | 177.47 | 274.98 | 0.64 |
| DDOG | tier_2_liquid_growth | 31 | 7 | YFINANCE | 0 | 172.5 | 280.37 | 0.8158 |
| ETN | tier_3_high_beta_theme | 22 | 3 | YFINANCE | 0 | 182.75 | 277.95 | 0.88 |
| GOOGL | tier_2_liquid_growth | 28 | 10 | YFINANCE | 0 | 173.21 | 278.48 | 0.7368 |
| HOOD | tier_1_core | 50 | 23 | YFINANCE | 0 | 154.93 | 264.52 | 0.6849 |
| INTC | tier_2_liquid_growth | 26 | 12 | YFINANCE | 0 | 171.37 | 293.77 | 0.6842 |
| IONQ | tier_3_high_beta_theme | 19 | 6 | YFINANCE | 0 | 166.07 | 267.0 | 0.76 |
| IWM | tier_1_core | 61 | 12 | YFINANCE | 0 | 134.25 | 249.5 | 0.8356 |
| KRE | tier_4_etfs_macro | 22 | 3 | YFINANCE | 0 | 165.58 | 287.27 | 0.88 |
| MARA | tier_3_high_beta_theme | 22 | 3 | YFINANCE | 0 | 175.99 | 272.35 | 0.88 |
| META | tier_2_liquid_growth | 31 | 7 | YFINANCE | 0 | 162.36 | 270.23 | 0.8158 |
| MSFT | tier_2_liquid_growth | 34 | 4 | YFINANCE | 0 | 164.07 | 273.33 | 0.8947 |
| MSTR | tier_2_liquid_growth | 22 | 11 | YFINANCE | 0 | 183.19 | 286.94 | 0.6667 |
| MU | tier_2_liquid_growth | 23 | 15 | YFINANCE | 0 | 182.52 | 292.24 | 0.6053 |
| NET | tier_2_liquid_growth | 20 | 18 | YFINANCE | 0 | 173.75 | 279.74 | 0.5263 |
| NNE | tier_3_high_beta_theme | 20 | 5 | YFINANCE | 0 | 184.26 | 267.44 | 0.8 |
| OKLO | tier_1_core | 45 | 28 | YFINANCE | 0 | 149.34 | 260.4 | 0.6164 |
| PLTR | tier_1_core | 51 | 22 | YFINANCE | 0 | 148.62 | 257.92 | 0.6986 |
| QBTS | tier_3_high_beta_theme | 20 | 5 | YFINANCE | 0 | 168.95 | 260.3 | 0.8 |
| QQQ | tier_1_core | 51 | 22 | YFINANCE | 0 | 135.78 | 288.01 | 0.6986 |
| RGTI | tier_3_high_beta_theme | 20 | 5 | YFINANCE | 0 | 171.15 | 270.56 | 0.8 |
| RIOT | tier_3_high_beta_theme | 17 | 8 | YFINANCE | 0 | 166.94 | 267.79 | 0.68 |
| RIVN | tier_3_high_beta_theme | 19 | 6 | YFINANCE | 0 | 172.83 | 264.68 | 0.76 |
| RKLB | tier_3_high_beta_theme | 16 | 9 | YFINANCE | 0 | 171.65 | 259.01 | 0.64 |
| SMCI | tier_2_liquid_growth | 29 | 9 | YFINANCE | 0 | 175.55 | 278.04 | 0.7632 |
| SMR | tier_3_high_beta_theme | 23 | 2 | YFINANCE | 0 | 163.66 | 264.32 | 0.92 |
| SNOW | tier_2_liquid_growth | 28 | 7 | YFINANCE | 0 | 181.94 | 276.43 | 0.8 |
| SOFI | tier_3_high_beta_theme | 19 | 6 | YFINANCE | 0 | 169.56 | 261.53 | 0.76 |
| SOXX | tier_4_etfs_macro | 19 | 6 | YFINANCE | 0 | 167.73 | 284.14 | 0.76 |
| SPY | tier_1_core | 61 | 12 | YFINANCE | 0 | 130.92 | 279.27 | 0.8356 |
| TSLA | tier_1_core | 47 | 26 | YFINANCE | 0 | 134.07 | 243.6 | 0.6438 |
| TSM | tier_2_liquid_growth | 33 | 5 | YFINANCE | 0 | 165.84 | 289.39 | 0.8684 |
| VRT | tier_3_high_beta_theme | 21 | 4 | YFINANCE | 0 | 175.96 | 256.23 | 0.84 |
| XBI | tier_4_etfs_macro | 21 | 4 | YFINANCE | 0 | 173.11 | 289.45 | 0.84 |
| XLE | tier_4_etfs_macro | 22 | 3 | YFINANCE | 0 | 171.95 | 268.67 | 0.88 |
| XLF | tier_4_etfs_macro | 23 | 2 | YFINANCE | 0 | 168.92 | 265.14 | 0.92 |
| XLI | tier_4_etfs_macro | 23 | 2 | YFINANCE | 0 | 176.16 | 273.02 | 0.92 |
| XLK | tier_4_etfs_macro | 25 | 0 | YFINANCE | 0 | 164.9 | 261.99 | 1.0 |
| XLU | tier_4_etfs_macro | 25 | 0 | YFINANCE | 0 | 172.4 | 279.57 | 1.0 |
| XLV | tier_4_etfs_macro | 24 | 1 | YFINANCE | 0 | 168.22 | 276.32 | 0.96 |

## Recommendation

Keep Yahoo as the bulk OHLCV source, Finnhub as quote freshness confirmation, and Alpha Vantage as a Tier 1 fallback only until a larger real-time sample proves a better free priority order.
