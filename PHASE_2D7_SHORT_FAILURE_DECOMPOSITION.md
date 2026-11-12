# Phase 2D.7 SHORT Failure Decomposition

Generated: 2026-09-03T20:21:32.242370+00:00

Research-only diagnostics. Canonical/live strategy parameters, thresholds, score weights, setup definitions, watchlist, stops, targets, provider gates, and management variants were not changed.

## Activation

- Phase 2D.7 activated at: 2026-09-03T20:20:30.277436+00:00
- New prospective cohort: `SHORT_13_00_14_30`
- Existing Phase 2D.6 cohorts continue unchanged.
- SHORT rules were not disabled or optimized.

## Resolved SHORT summary

- Resolved natural SHORT setups analyzed: 231
- Current SHORT expectancy: -0.2223R
- Current SHORT PF: 0.4156
- Classification counts: {'NO_EDGE': 108, 'IMMEDIATE_FAILURE': 7, 'COUNTERTREND_FAILURE': 25, 'LATE_ENTRY': 23, 'GOOD_MOVE_POOR_EXIT': 31, 'EARLY_MFE_THEN_REVERSAL': 8, 'GOOD_MOVE_FULLY_MONETIZED': 29}

## SHORT classification

| class | count |
| --- | --- |
| NO_EDGE | 108 |
| GOOD_MOVE_POOR_EXIT | 31 |
| GOOD_MOVE_FULLY_MONETIZED | 29 |
| COUNTERTREND_FAILURE | 25 |
| LATE_ENTRY | 23 |
| EARLY_MFE_THEN_REVERSAL | 8 |
| IMMEDIATE_FAILURE | 7 |

## Entry timing

| bucket | N | expectancy | profit_factor | win_rate | avg_MFE | avg_MAE | max_drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1_candle_after_reclaim | 69 | -0.2373 | 0.5257 | 0.5217 | 0.7913 | 1.1737 | 16.8008 |
| 2_plus_candles_after_reclaim | 101 | -0.3463 | 0.3443 | 0.4554 | 0.6011 | 1.2963 | 34.9775 |
| NO_FILL | 61 | 0.0 | nan | 0.0 | 0.0 | 0.0 | 0.0 |

## Market alignment

| bucket | N | expectancy | profit_factor | win_rate | avg_MFE | avg_MAE | max_drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- |
| COUNTERTREND | 60 | -0.3403 | 0.2179 | 0.2833 | 0.3851 | 0.9971 | 20.4195 |
| FULLY_ALIGNED | 5 | -0.6096 | 0.0165 | 0.2 | 0.0999 | 0.8388 | 3.0991 |
| MARKET_ALIGNED | 14 | -0.2041 | 0.0734 | 0.3571 | 0.1343 | 0.5144 | 2.8899 |
| SYMBOL_ONLY | 142 | -0.1715 | 0.5439 | 0.4014 | 0.6056 | 0.9535 | 25.1557 |
| UNKNOWN | 10 | -0.0677 | 0.6917 | 0.2 | 0.3828 | 0.5293 | 2.1956 |

## Forward SHORT time buckets

| time_bucket | management_version | parent_setup_count | N | expectancy | profit_factor | win_rate | avg_MFE | avg_MAE | max_drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 11:30-13:00 | TM_V0_CURRENT | 16 | 15 | -0.4043 | 0.0303 | 0.1333 | 0.1176 | 0.7274 | 6.0778 |
| 11:30-13:00 | TM_V3_TP1_PLUS_RUNNER | 16 | 15 | -0.3794 | 0.0515 | 0.1333 | 0.1409 | 0.7389 | 5.7237 |
| 13:00-14:30 | TM_V0_CURRENT | 22 | 18 | 0.0407 | 1.1737 | 0.3889 | 0.494 | 0.4475 | 4.156 |
| 13:00-14:30 | TM_V3_TP1_PLUS_RUNNER | 22 | 18 | 0.0064 | 1.0289 | 0.3889 | 0.6353 | 0.4445 | 3.8957 |
| 14:30-15:30 | TM_V0_CURRENT | 13 | 8 | -0.7957 | 0.0028 | 0.125 | 0.2385 | 0.9723 | 6.3829 |
| 14:30-15:30 | TM_V3_TP1_PLUS_RUNNER | 13 | 8 | -0.7448 | 0.007 | 0.125 | 0.3121 | 1.1688 | 6.0 |
| 15:30-close | TM_V0_CURRENT | 7 | 0 | 0.0 | nan | 0.0 | 0.0 | 0.0 | 0.0 |
| 15:30-close | TM_V3_TP1_PLUS_RUNNER | 7 | 0 | 0.0 | nan | 0.0 | 0.0 | 0.0 | 0.0 |

## SHORT-only management replay

| bucket | N | expectancy | profit_factor | win_rate | avg_MFE | avg_MAE | max_drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SHORT_TM_A_CURRENT | 231 | -0.2223 | 0.4156 | 0.355 | 0.4992 | 0.9174 | 51.4517 |
| SHORT_TM_B_FULL_EXIT_0_5R | 170 | -0.3428 | 0.5848 | 0.4588 | 0.4071 | 0.6652 | 71.1525 |
| SHORT_TM_C_HALF_0_5R_REST_BE_RUNNER | 170 | -0.1845 | 0.5465 | 0.4588 | 0.5917 | 0.737 | 37.8634 |
| SHORT_TM_D_FULL_EXIT_1R | 170 | -0.3503 | 0.6368 | 0.3941 | 0.5481 | 0.7618 | 88.6022 |
| SHORT_TM_E_HALF_0_5R_HALF_1R | 170 | -0.1613 | 0.6147 | 0.4118 | 0.5481 | 0.7618 | 35.8692 |

## LONG 11:30–13:00 holdout continuation

| management_version | parent_setup_count | resolved_N | unresolved_N | expectancy | profit_factor | win_rate | max_drawdown | top_symbol | top_symbol_share | top_day | top_day_share | bootstrap_expectancy_ci_low | bootstrap_expectancy_ci_high | promotion_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TM_V0_CURRENT | 27 | 26 | 1 | -0.0763 | 0.7617 | 0.4231 | 5.0797 | MSTR | 0.1154 | 2026-09-03 | 1.0 | -0.3853 | 0.1869 | REJECTED |
| TM_V3_TP1_PLUS_RUNNER | 27 | 25 | 2 | 0.0182 | 1.057 | 0.4 | 3.5295 | MSTR | 0.12 | 2026-09-03 | 1.0 | -0.3454 | 0.3539 | EXPLORATORY |

## Output artifacts

- `PHASE_2D7_SHORT_FAILURE_DECOMPOSITION.md`
- `short_path_decomposition.csv`
- `short_entry_timing.csv`
- `short_market_alignment.csv`
- `short_time_bucket_forward.csv`
- `short_management_replay.csv`
- `long_midday_holdout_update.csv`
