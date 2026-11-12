# Provider Freshness Report - 2026-09-28

Generated: 2026-09-28T20:20:07.517320+00:00

This report measures free candle-data usability only. It does not change strategy logic, gates, weights, stops, targets, sizing, or lane rules.

## Summary

- Valid scans by candle provider: {"YFINANCE": {"stale_scans": 280, "valid_scans": 972}}
- Average candle publication lag: 128.072 seconds
- Median/P95/max lag: 108.5824 / 277.5059 / 298.7934 seconds
- Fallback success rate: 0
- Cross-provider conflicts: 0

## Symbol Reliability

| symbol | tier | valid_scans | stale_scans | primary_provider | fallback_success | avg_lag | p95_lag | reliability |
|---|---|---:|---:|---|---:|---:|---:|---:|
| AAPL | tier_2_liquid_growth | 25 | 4 | YFINANCE | 0 | 124.82 | 260.6 | 0.8621 |
| AMD | tier_1_core | 36 | 15 | YFINANCE | 0 | 117.02 | 251.29 | 0.7059 |
| AMZN | tier_2_liquid_growth | 26 | 3 | YFINANCE | 0 | 126.88 | 271.29 | 0.8966 |
| ARKK | tier_4_etfs_macro | 11 | 8 | YFINANCE | 0 | 131.54 | 233.08 | 0.5789 |
| ARM | tier_2_liquid_growth | 19 | 9 | YFINANCE | 0 | 115.94 | 200.91 | 0.6786 |
| AVGO | tier_2_liquid_growth | 23 | 5 | YFINANCE | 0 | 134.8 | 277.13 | 0.8214 |
| BE | tier_3_high_beta_theme | 11 | 8 | YFINANCE | 0 | 132.38 | 263.41 | 0.5789 |
| CEG | tier_3_high_beta_theme | 14 | 5 | YFINANCE | 0 | 149.11 | 274.65 | 0.7368 |
| CLSK | tier_3_high_beta_theme | 11 | 8 | YFINANCE | 0 | 145.84 | 269.77 | 0.5789 |
| COIN | tier_2_liquid_growth | 13 | 15 | YFINANCE | 0 | 142.54 | 284.03 | 0.4643 |
| CRWD | tier_2_liquid_growth | 22 | 6 | YFINANCE | 0 | 138.02 | 290.51 | 0.7857 |
| CRWV | tier_3_high_beta_theme | 9 | 10 | YFINANCE | 0 | 136.56 | 265.48 | 0.4737 |
| DDOG | tier_2_liquid_growth | 17 | 11 | YFINANCE | 0 | 110.73 | 195.25 | 0.6071 |
| ETN | tier_3_high_beta_theme | 14 | 5 | YFINANCE | 0 | 140.8 | 267.88 | 0.7368 |
| GOOGL | tier_2_liquid_growth | 19 | 7 | YFINANCE | 0 | 126.45 | 274.56 | 0.7308 |
| HOOD | tier_1_core | 36 | 15 | YFINANCE | 0 | 129.86 | 263.03 | 0.7059 |
| INTC | tier_2_liquid_growth | 15 | 13 | YFINANCE | 0 | 117.72 | 211.25 | 0.5357 |
| IONQ | tier_3_high_beta_theme | 9 | 11 | YFINANCE | 0 | 153.57 | 281.22 | 0.45 |
| IWM | tier_1_core | 44 | 8 | YFINANCE | 0 | 105.58 | 243.19 | 0.8462 |
| KRE | tier_4_etfs_macro | 14 | 5 | YFINANCE | 0 | 144.26 | 247.78 | 0.7368 |
| MARA | tier_3_high_beta_theme | 15 | 6 | YFINANCE | 0 | 133.14 | 255.97 | 0.7143 |
| META | tier_2_liquid_growth | 15 | 14 | YFINANCE | 0 | 121.8 | 266.06 | 0.5172 |
| MSFT | tier_2_liquid_growth | 21 | 8 | YFINANCE | 0 | 128.68 | 265.65 | 0.7241 |
| MSTR | tier_2_liquid_growth | 19 | 9 | YFINANCE | 0 | 146.32 | 288.46 | 0.6786 |
| MU | tier_2_liquid_growth | 22 | 6 | YFINANCE | 0 | 119.9 | 205.19 | 0.7857 |
| NET | tier_2_liquid_growth | 17 | 11 | YFINANCE | 0 | 129.74 | 280.11 | 0.6071 |
| NNE | tier_3_high_beta_theme | 16 | 4 | YFINANCE | 0 | 147.86 | 277.51 | 0.8 |
| NVDA | tier_1_core | 1 | 4 | YFINANCE | 0 | 76.33 | 76.33 | 0.2 |
| OKLO | tier_1_core | 35 | 16 | YFINANCE | 0 | 126.66 | 260.53 | 0.6863 |
| PLTR | tier_1_core | 41 | 10 | YFINANCE | 0 | 123.63 | 258.67 | 0.8039 |
| QBTS | tier_3_high_beta_theme | 9 | 11 | YFINANCE | 0 | 160.2 | 287.02 | 0.45 |
| QQQ | tier_1_core | 36 | 16 | YFINANCE | 0 | 101.62 | 260.4 | 0.6923 |
| RGTI | tier_3_high_beta_theme | 16 | 4 | YFINANCE | 0 | 157.52 | 284.82 | 0.8 |
| RIOT | tier_3_high_beta_theme | 13 | 8 | YFINANCE | 0 | 136.48 | 258.96 | 0.619 |
| RIVN | tier_3_high_beta_theme | 12 | 9 | YFINANCE | 0 | 130.33 | 253.16 | 0.5714 |
| RKLB | tier_3_high_beta_theme | 12 | 9 | YFINANCE | 0 | 123.88 | 247.56 | 0.5714 |
| SMCI | tier_2_liquid_growth | 12 | 16 | YFINANCE | 0 | 138.48 | 279.98 | 0.4286 |
| SMR | tier_3_high_beta_theme | 14 | 6 | YFINANCE | 0 | 150.34 | 279.29 | 0.7 |
| SNOW | tier_2_liquid_growth | 15 | 13 | YFINANCE | 0 | 124.04 | 234.78 | 0.5357 |
| SOFI | tier_3_high_beta_theme | 18 | 3 | YFINANCE | 0 | 127.92 | 251.0 | 0.8571 |
| SOXX | tier_4_etfs_macro | 15 | 4 | YFINANCE | 0 | 136.04 | 237.56 | 0.7895 |
| SPY | tier_1_core | 31 | 21 | YFINANCE | 0 | 88.97 | 224.69 | 0.5962 |
| TSLA | tier_1_core | 43 | 9 | YFINANCE | 0 | 111.5 | 247.68 | 0.8269 |
| TSM | tier_2_liquid_growth | 21 | 7 | YFINANCE | 0 | 125.11 | 210.17 | 0.75 |
| VRT | tier_3_high_beta_theme | 13 | 6 | YFINANCE | 0 | 145.08 | 271.17 | 0.6842 |
| XBI | tier_4_etfs_macro | 11 | 8 | YFINANCE | 0 | 140.52 | 243.0 | 0.5789 |
| XLE | tier_4_etfs_macro | 15 | 4 | YFINANCE | 0 | 153.06 | 294.09 | 0.7895 |
| XLF | tier_4_etfs_macro | 12 | 7 | YFINANCE | 0 | 149.86 | 290.78 | 0.6316 |
| XLI | tier_4_etfs_macro | 15 | 4 | YFINANCE | 0 | 147.89 | 228.7 | 0.7895 |
| XLK | tier_4_etfs_macro | 15 | 4 | YFINANCE | 0 | 145.64 | 285.68 | 0.7895 |
| XLU | tier_4_etfs_macro | 17 | 2 | YFINANCE | 0 | 128.64 | 229.76 | 0.8947 |
| XLV | tier_4_etfs_macro | 17 | 2 | YFINANCE | 0 | 125.17 | 225.0 | 0.8947 |

## Recommendation

Keep Yahoo as the bulk OHLCV source, Finnhub as quote freshness confirmation, and Alpha Vantage as a Tier 1 fallback only until a larger real-time sample proves a better free priority order.
