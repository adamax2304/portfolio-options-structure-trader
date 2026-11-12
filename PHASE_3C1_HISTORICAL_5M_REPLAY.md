# Phase 3C.1 Historical 5m OHLCV Acquisition + Full Level Replay

Generated: 2026-09-04T19:12:07.021244+00:00

Status: **EXPLORATORY REPLAY COMPLETE**

No live daemon, live strategy, forward cohort, threshold, score weight, stop/target, canonical management, provider gate, Portfolio OS, or live-execution behavior was changed.

## Source-gate result before replay

### Massive / Polygon

- Credential state: `NOT_CONFIGURED`
- Adapter status: `MASSIVE_API_KEY_NOT_CONFIGURED`
- Minute aggregates authenticated test: `False`

No Massive key is configured locally, so no authenticated earliest-depth test was possible. `.env.example` now contains only the placeholder `MASSIVE_API_KEY=`.

### WRDS GitHub 5m

| symbol | rows | dates | range | bad OHLC rows | duplicate timestamps | removed early-close/post-close bars |
|---|---:|---:|---|---:|---:|---:|
| SPY | 30966 | 397 | 2024-06-03 to 2025-12-31 | 0 | 0 | 216 |
| QQQ | 30966 | 397 | 2024-06-03 to 2025-12-31 | 0 | 0 | 216 |
| IWM | 30966 | 397 | 2024-06-03 to 2025-12-31 | 0 | 0 | 216 |

WRDS suitability: `EXPLORATORY_RESEARCH`, not `SERIOUS_BACKTEST`, because the GitHub repository has no explicit license metadata and WRDS TAQ redistribution authority is not proven here.

### Daily reference cross-check

```json
{
  "IWM": {
    "status": "DAILY_ROLLUP_CROSSCHECK_COMPLETE",
    "overlap_days": 385,
    "close_median_bps": 4.4559,
    "close_p95_bps": 12.9579,
    "open_median_bps": 0.0,
    "high_p95_bps": 612.0878,
    "low_p95_bps": 687.8672,
    "volume_median_deviation_pct": 9.7511,
    "assessment": "CLOSES_USABLE_HIGH_LOW_VOLUME_REQUIRE_CAUTION"
  },
  "QQQ": {
    "status": "DAILY_ROLLUP_CROSSCHECK_COMPLETE",
    "overlap_days": 386,
    "close_median_bps": 4.2781,
    "close_p95_bps": 13.6623,
    "open_median_bps": 0.0,
    "high_p95_bps": 436.5609,
    "low_p95_bps": 834.8591,
    "volume_median_deviation_pct": 11.1882,
    "assessment": "CLOSES_USABLE_HIGH_LOW_VOLUME_REQUIRE_CAUTION"
  },
  "SPY": {
    "status": "DAILY_ROLLUP_CROSSCHECK_COMPLETE",
    "overlap_days": 385,
    "close_median_bps": 4.0555,
    "close_p95_bps": 13.705,
    "open_median_bps": 0.0,
    "high_p95_bps": 192.1951,
    "low_p95_bps": 924.8352,
    "volume_median_deviation_pct": 16.075,
    "assessment": "CLOSES_USABLE_HIGH_LOW_VOLUME_REQUIRE_CAUTION"
  }
}
```

## Clean 5m dataset

- File: `historical_intraday_5m_v2.parquet`
- Rows: 89,628
- Symbols: IWM, QQQ, SPY
- Date range: 2024-06-03 to 2025-12-15
- Unique trading dates: 386
- RTH only: true
- Early-close bars after official close: excluded
- Provider label: `WRDS_TAQ_PUBLIC_GITHUB`

## Options / price alignment

- Existing D-1 option levels used: `historical_daily_option_levels.parquet`
- Expanded detector-compatible option level rows: 90,690
- Control level rows: 5,765
- Strict rule enforced: `source_chain_date < trade_date`
- Same-day EOD option chains were not used for same-day intraday decisions.

## Replay summary

Default evaluation slice: `TM_V0_CURRENT`, `SLIPPAGE_3BP`, resolved `closed/censored` trades.

| bucket | N | unique_trading_days | expectancy_R | profit_factor | win_rate | median_R | avg_winner | avg_loser | MFE | MAE | max_DD | positive_day_pct | remove_best_day_expectancy | remove_best_month_expectancy | remove_best_symbol_expectancy | day_block_bootstrap_low | day_block_bootstrap_high |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ALL_OPTIONS_DEFAULT_3BP_TM_V0 | 43703 | 385 | -0.225 | 0.2827 | 0.4698 | -0.0075 | 0.1888 | -0.5917 | 0.5563 | 1.1978 | 9835.8017 | 0.1532 | -0.2274 | -0.2266 | -0.2313 | -0.2506 | -0.2026 |
| GEX_MODEL_C_DEFAULT_3BP_TM_V0 | 13635 | 385 | -0.2301 | 0.2787 | 0.4605 | -0.0148 | 0.1931 | -0.5915 | 0.5565 | 1.1964 | 3139.9432 | 0.1558 | -0.2316 | -0.2318 | -0.2352 | -0.2562 | -0.2058 |
| ALL_CONTROLS_DEFAULT_3BP_TM_V0 | 10251 | 383 | -0.1822 | 0.351 | 0.5143 | 0.0021 | 0.1916 | -0.578 | 0.6163 | 1.1168 | 1870.5808 | 0.2324 | -0.1853 | -0.1912 | -0.2048 | -0.2088 | -0.1557 |

## Long / short

| direction | N | unique_trading_days | expectancy_R | profit_factor | win_rate | median_R | avg_winner | avg_loser | MFE | MAE | max_DD | positive_day_pct | remove_best_day_expectancy | remove_best_month_expectancy | remove_best_symbol_expectancy | day_block_bootstrap_low | day_block_bootstrap_high |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| LONG | 23666 | 381 | -0.246 | 0.2376 | 0.4593 | -0.0115 | 0.1669 | -0.5968 | 0.4247 | 1.3585 | 5821.6469 | 0.2572 | -0.2494 | -0.2497 | -0.2586 | -0.2789 | -0.2121 |
| SHORT | 20037 | 346 | -0.2002 | 0.3394 | 0.4822 | -0.0042 | 0.2134 | -0.5855 | 0.7117 | 1.0079 | 4031.0624 | 0.3179 | -0.2068 | -0.2035 | -0.1975 | -0.2445 | -0.1577 |

## GEX model comparison

| gex_model_version | N | unique_trading_days | expectancy_R | profit_factor | win_rate | median_R | avg_winner | avg_loser | MFE | MAE | max_DD | positive_day_pct | remove_best_day_expectancy | remove_best_month_expectancy | remove_best_symbol_expectancy | day_block_bootstrap_low | day_block_bootstrap_high |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GEX_MODEL_A_CALL_POSITIVE_PUT_NEGATIVE | 15034 | 385 | -0.2227 | 0.2846 | 0.474 | -0.0059 | 0.1869 | -0.5918 | 0.5562 | 1.1984 | 3349.9504 | 0.1688 | -0.2252 | -0.2242 | -0.2294 | -0.2478 | -0.2013 |
| GEX_MODEL_B_CALL_NEGATIVE_PUT_POSITIVE | 15034 | 385 | -0.2227 | 0.2846 | 0.474 | -0.0059 | 0.1869 | -0.5918 | 0.5562 | 1.1984 | 3349.9504 | 0.1688 | -0.2252 | -0.2242 | -0.2294 | -0.2478 | -0.2013 |
| GEX_MODEL_C_ABSOLUTE_GAMMA_CONCENTRATION | 13635 | 385 | -0.2301 | 0.2787 | 0.4605 | -0.0148 | 0.1931 | -0.5915 | 0.5565 | 1.1964 | 3139.9432 | 0.1558 | -0.2316 | -0.2318 | -0.2352 | -0.2562 | -0.2058 |

## Level type

| level_type | N | unique_trading_days | expectancy_R | profit_factor | win_rate | median_R | avg_winner | avg_loser | MFE | MAE | max_DD | positive_day_pct | remove_best_day_expectancy | remove_best_month_expectancy | remove_best_symbol_expectancy | day_block_bootstrap_low | day_block_bootstrap_high |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CALL_WALL | 8784 | 299 | -0.2476 | 0.252 | 0.4258 | -0.042 | 0.1959 | -0.5764 | 0.514 | 1.2322 | 2174.777 | 0.3411 | -0.2566 | -0.2649 | -0.2631 | -0.2904 | -0.2011 |
| GAMMA_FLIP | 5423 | 294 | -0.2072 | 0.3172 | 0.5014 | 0.0003 | 0.1919 | -0.6085 | 0.6541 | 1.2048 | 1122.4238 | 0.3265 | -0.2141 | -0.2171 | -0.2341 | -0.2514 | -0.1661 |
| GEX_NODE | 21205 | 370 | -0.2177 | 0.2784 | 0.4823 | -0.0029 | 0.1741 | -0.5829 | 0.5211 | 1.2118 | 4620.2251 | 0.2541 | -0.2207 | -0.2198 | -0.2271 | -0.2477 | -0.1855 |
| OI_NODE | 2015 | 81 | -0.2213 | 0.2517 | 0.4323 | -0.0379 | 0.1723 | -0.521 | 0.4281 | 1.2003 | 448.8394 | 0.3827 | -0.2356 | -0.2301 | -0.2355 | -0.2951 | -0.1561 |
| PUT_WALL | 6276 | 182 | -0.2347 | 0.3191 | 0.4739 | -0.0094 | 0.2322 | -0.6552 | 0.6911 | 1.0952 | 1485.8102 | 0.3736 | -0.2493 | -0.2583 | -0.2142 | -0.3078 | -0.1647 |

## Options vs controls

| strategy_type | control_type | N | unique_trading_days | expectancy_R | profit_factor | win_rate | median_R | avg_winner | avg_loser | MFE | MAE | max_DD | positive_day_pct | remove_best_day_expectancy | remove_best_month_expectancy | remove_best_symbol_expectancy | day_block_bootstrap_low | day_block_bootstrap_high |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| OPTIONS_STRUCTURE_RECON | OPTIONS_LEVELS | 43703 | 385 | -0.225 | 0.2827 | 0.4698 | -0.0075 | 0.1888 | -0.5917 | 0.5563 | 1.1978 | 9835.8017 | 0.1532 | -0.2274 | -0.2266 | -0.2313 | -0.2506 | -0.2026 |
| PRICE_CONTROL | PREVIOUS_DAY_HIGH | 1241 | 177 | -0.194 | 0.3193 | 0.5036 | 0.0003 | 0.1807 | -0.5742 | 0.6122 | 1.3062 | 240.7944 | 0.4181 | -0.1989 | -0.2053 | -0.2417 | -0.2561 | -0.1307 |
| PRICE_CONTROL | PREVIOUS_DAY_LOW | 1194 | 152 | -0.2115 | 0.3319 | 0.4933 | -0.0005 | 0.2129 | -0.6246 | 0.5934 | 1.088 | 258.6275 | 0.4145 | -0.2267 | -0.2193 | -0.1952 | -0.2692 | -0.1443 |
| PRICE_CONTROL | PRIOR_RANGE_MIDPOINT | 2591 | 290 | -0.168 | 0.3436 | 0.5473 | 0.0066 | 0.1607 | -0.5654 | 0.562 | 1.043 | 441.9112 | 0.431 | -0.1738 | -0.1785 | -0.1649 | -0.218 | -0.1219 |
| PRICE_CONTROL | RANDOM_NEARBY_LEVEL | 942 | 156 | -0.1942 | 0.2742 | 0.4989 | -0.0002 | 0.147 | -0.5339 | 0.6599 | 1.0873 | 183.2256 | 0.5064 | -0.2018 | -0.2076 | -0.1981 | -0.2548 | -0.1315 |
| PRICE_CONTROL | ROUND_NUMBER_LEVEL | 4283 | 334 | -0.1766 | 0.3856 | 0.5067 | 0.0014 | 0.2188 | -0.5827 | 0.6471 | 1.121 | 755.8815 | 0.3473 | -0.1841 | -0.1917 | -0.2144 | -0.2161 | -0.1383 |

## Interpretation guardrails

- This is a true replay mechanically: D-1 EOD option structure joins to D 5m bars without same-day chain lookahead.
- It remains exploratory because the public WRDS GitHub data has weak redistribution/licensing provenance and Massive cross-check was not available without a key.
- Do not promote any live rule or management variant from this run alone.
- Serious validation still needs authenticated Massive/Polygon or another licensed 5m source to cross-check the WRDS bars.

## Output files

- `historical_options_vs_controls_v2.csv`
- `historical_long_short_v2.csv`
- `historical_level_type_v2.csv`
- `historical_gex_model_comparison.csv`
- `historical_discovery_holdout_v2.csv`
- `historical_walkforward_v2.csv`
- `historical_daily_robustness_v2.csv`
- `historical_intraday_5m_v2.parquet`
- `historical_replay_v2.parquet`
