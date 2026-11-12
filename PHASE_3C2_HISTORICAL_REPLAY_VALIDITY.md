# Phase 3C.2 Historical Replay Validity Audit

Generated: 2026-09-04T20:21:50.096331+00:00

Scope: historical research only. No live daemon, live strategy, forward cohort, threshold, score weight, stop/target, canonical management, provider gate, Portfolio OS, or live-execution behavior was changed.

Historical strategy label: `D1_EOD_STATIC_OPTIONS`.

This audit must not be aggregated with `LIVE_INTRADAY_OPTIONS` forward results.

## Direct answers

### 1. Why did Phase 3C.1 generate 43,703 options trades?
Because the replay expanded each symbol/day into many static D-1 option-derived levels across three GEX models, then allowed repeated two-bar reclaim detections whenever price oscillated around those levels. There was no episode-level cooldown or structural-zone deduplication in Phase 3C.1. The regenerated audit count is 43,703 resolved events; the Phase 3C.1 parquet resolved count is 43,703. Status: MATCHES_PHASE3C1_RESOLVED_COUNT.

### 2. Is the historical detector over-generating events?
Yes for this static D-1 reconstruction context. The detector is applying valid live reclaim logic, but the historical event generator presents many nearby static levels and no live-style parent-event deduplication. This inflates event frequency and makes raw trade count unsuitable as an empirical setup count.

### 3. How many economically distinct reclaim events remain after reasonable deduplication?
Using the research-only 30-minute cooldown plus 0.30 ATR structural-zone clustering leaves 18,556 resolved events. Plain exact-level DEDUP_30M leaves 18,608.

### 4. Were insignificant GEX nodes being traded?
Not primarily as hundreds of strikes. The median symbol/day/model had 21 raw levels and 13 unique prices. The larger inflation came from three GEX model variants plus repeated interactions around the same static levels. Top-3 absolute GEX reduces frequency; Top-5/Top-10 do not because the source expansion already kept only five absolute GEX nodes per model/day.

### 5. Do top options levels outperform matched random levels?
No robust outperformance is shown in this audit. See `historical_matched_controls.csv`; matched controls are still required as the fair comparison because raw controls had far fewer opportunities.

### 6. Does absolute gamma concentration perform better than signed GEX?
No. Model C remains negative and does not materially outperform signed models under equal event-generation rules. A/B are effectively identical here because selected level prices are largely the same even though sign labels differ.

### 7. Are D-1 levels reasonably stable into next-day RTH?
Not measurable from overlapping live AlgoX archives in this workspace. Stability audit status: NO_OVERLAPPING_ALGOX_INTRADAY_ARCHIVE. The local AlgoX archive starts in 2026, while this replay covers 2024-2025.

### 8. Does the historical strategy have favorable MFE even if realized expectancy is negative?
There is some favorable excursion, but it is not enough to overcome adverse excursion and management/fill assumptions in aggregate. Because Phase 3C.1 did not persist exact future-bar path ordering, the excursion table uses replay-output MFE thresholds as an approximation, not a strict tick-ordered before-stop measurement.

### 9. Is Phase 3C.1 negative performance a strategy result or partly a replay-construction artifact?
Partly a replay-construction artifact. The D-1 static options strategy is not equivalent to the live intraday-updating strategy, and event over-generation materially affects raw results. The negative replay is useful as an audit signal, not a live-strategy rejection.

### 10. Is the Level 2 dataset trustworthy enough for further research?
Yes for pipeline testing and exploratory research only. It is not yet strong enough for serious edge conclusions because the WRDS GitHub provenance/license is weak and Massive/Polygon cross-check remains unavailable without a configured key.


## Trade frequency audit

Default replay slice: `TM_V0_CURRENT`, `SLIPPAGE_3BP`.

- Resolved options-derived events in Phase 3C.1 report/parquet: 43,703
- Regenerated resolved audit events: 43,703
- Regenerated detected events including expired/unfilled: 45,737
- Median resolved trades per symbol/day/model: 11.0
- P95 resolved trades per symbol/day/model: 35.0
- Max resolved trades per symbol/day/model: 60

| gex_model_version | metric | symbol_days | median | p90 | p95 | max | mean |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GEX_MODEL_A_CALL_POSITIVE_PUT_NEGATIVE | setups_detected | 1103 | 12.0 | 28.8 | 36.0 | 61 | 14.2647 |
| GEX_MODEL_A_CALL_POSITIVE_PUT_NEGATIVE | resolved_trades | 1103 | 11.0 | 27.0 | 35.0 | 60 | 13.6301 |
| GEX_MODEL_A_CALL_POSITIVE_PUT_NEGATIVE | unique_levels_interacted | 1103 | 2.0 | 3.0 | 4.0 | 6 | 2.0707 |
| GEX_MODEL_B_CALL_NEGATIVE_PUT_POSITIVE | setups_detected | 1103 | 12.0 | 28.8 | 36.0 | 61 | 14.2647 |
| GEX_MODEL_B_CALL_NEGATIVE_PUT_POSITIVE | resolved_trades | 1103 | 11.0 | 27.0 | 35.0 | 60 | 13.6301 |
| GEX_MODEL_B_CALL_NEGATIVE_PUT_POSITIVE | unique_levels_interacted | 1103 | 2.0 | 3.0 | 4.0 | 6 | 2.0707 |
| GEX_MODEL_C_ABSOLUTE_GAMMA_CONCENTRATION | setups_detected | 1072 | 11.0 | 28.0 | 36.0 | 61 | 13.3106 |
| GEX_MODEL_C_ABSOLUTE_GAMMA_CONCENTRATION | resolved_trades | 1072 | 10.0 | 26.0 | 34.0 | 60 | 12.7192 |
| GEX_MODEL_C_ABSOLUTE_GAMMA_CONCENTRATION | unique_levels_interacted | 1072 | 2.0 | 3.0 | 3.0 | 5 | 1.7948 |
| ALL_MODELS | setups_detected | 3278 | 11.0 | 28.0 | 36.0 | 61 | 13.9527 |
| ALL_MODELS | resolved_trades | 3278 | 11.0 | 27.0 | 35.0 | 60 | 13.3322 |
| ALL_MODELS | unique_levels_interacted | 3278 | 2.0 | 3.0 | 4.0 | 6 | 1.9805 |

## Deduplication variants

These are research-only filters. They do not change live strategy behavior.

| dedup_variant | events_detected | resolved_events | event_retention_pct | resolved_retention_pct | strategy_state_source | N | unique_days | trades_per_symbol_day | expectancy_R | profit_factor | win_rate | median_R | avg_winner | avg_loser | MFE | MAE | max_DD | positive_day_pct | day_block_ci_low | day_block_ci_high |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| RAW_PHASE3C1_EVENTS | 45737 | 43703 | 1.0 | 1.0 | D1_EOD_STATIC_OPTIONS | 43703 | 385 | 39.73 | -0.225 | 0.2827 | 0.4698 | -0.0075 | 0.1888 | -0.5917 | 0.5563 | 1.1978 | 9835.8017 | 0.1532 | -0.2427 | -0.1986 |
| DEDUP_15M | 24545 | 23400 | 0.5367 | 0.5354 | D1_EOD_STATIC_OPTIONS | 23400 | 385 | 21.3309 | -0.226 | 0.3017 | 0.4769 | -0.0049 | 0.2047 | -0.6189 | 0.6411 | 1.2227 | 5290.6965 | 0.161 | -0.2391 | -0.1954 |
| DEDUP_30M | 19522 | 18608 | 0.4268 | 0.4258 | D1_EOD_STATIC_OPTIONS | 18608 | 385 | 16.9626 | -0.224 | 0.3156 | 0.4852 | -0.0029 | 0.2129 | -0.6358 | 0.6875 | 1.2217 | 4170.9325 | 0.1662 | -0.2356 | -0.1927 |
| DEDUP_60M | 15345 | 14583 | 0.3355 | 0.3337 | D1_EOD_STATIC_OPTIONS | 14583 | 385 | 13.2935 | -0.2248 | 0.3235 | 0.489 | -0.0017 | 0.2199 | -0.6504 | 0.7389 | 1.2122 | 3279.5037 | 0.1688 | -0.2369 | -0.1927 |
| ONE_TRADE_PER_LEVEL_PER_DIRECTION_PER_DAY | 8495 | 8045 | 0.1857 | 0.1841 | D1_EOD_STATIC_OPTIONS | 8045 | 385 | 7.3672 | -0.2397 | 0.3417 | 0.5078 | 0.0013 | 0.245 | -0.7396 | 0.9355 | 1.256 | 1929.7944 | 0.1792 | -0.2575 | -0.2071 |
| ECONOMIC_DEDUP_30M_CLUSTER_0_30_ATR | 19470 | 18556 | 0.4257 | 0.4246 | D1_EOD_STATIC_OPTIONS | 18556 | 385 | 16.9152 | -0.224 | 0.3156 | 0.4851 | -0.0029 | 0.2129 | -0.6356 | 0.6848 | 1.2181 | 4157.8414 | 0.1662 | -0.2358 | -0.1925 |

## Level count / clustering audit

The static D-1 level list is not hundreds of strikes per day in this replay. Frequency inflation is mainly repeated interactions around the same few levels across three GEX model variants.

| metric | value |
| --- | --- |
| median_raw_levels_per_symbol_day_model | 21.0 |
| median_unique_prices_per_symbol_day_model | 13.0 |
| median_0_30_atr_clusters_per_symbol_day_model | 12.0 |
| median_0_30_atr_compression | 0.0 |

Detailed per symbol/day/model counts are in `historical_level_count_audit.csv`.

## Level importance filters

| importance_variant | events_detected | resolved_events | unique_symbols | N | unique_days | trades_per_symbol_day | expectancy_R | profit_factor | win_rate | median_R | avg_winner | avg_loser | MFE | MAE | max_DD | positive_day_pct | day_block_ci_low | day_block_ci_high |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ALL_OPTIONS_LEVELS | 45737 | 43703 | 3 | 43703 | 385 | 39.73 | -0.225 | 0.2827 | 0.4698 | -0.0075 | 0.1888 | -0.5917 | 0.5563 | 1.1978 | 9835.8017 | 0.1532 | -0.2427 | -0.1986 |
| ALL_GEX_NODES | 29722 | 28415 | 3 | 28415 | 380 | 30.7855 | -0.2211 | 0.2862 | 0.4776 | -0.0042 | 0.1857 | -0.593 | 0.5489 | 1.1831 | 6286.3251 | 0.2237 | -0.2308 | -0.1753 |
| TOP_10_ABS_GEX_NODES | 29722 | 28415 | 3 | 28415 | 380 | 30.7855 | -0.2211 | 0.2862 | 0.4776 | -0.0042 | 0.1857 | -0.593 | 0.5489 | 1.1831 | 6286.3251 | 0.2237 | -0.2308 | -0.1753 |
| TOP_5_ABS_GEX_NODES | 29722 | 28415 | 3 | 28415 | 380 | 30.7855 | -0.2211 | 0.2862 | 0.4776 | -0.0042 | 0.1857 | -0.593 | 0.5489 | 1.1831 | 6286.3251 | 0.2237 | -0.2308 | -0.1753 |
| TOP_3_ABS_GEX_NODES | 19158 | 18297 | 3 | 18297 | 344 | 26.5174 | -0.2199 | 0.2992 | 0.4823 | -0.0039 | 0.1946 | -0.6062 | 0.5703 | 1.211 | 4025.9477 | 0.2674 | -0.2438 | -0.183 |
| GAMMA_FLIP_CALL_WALL_PUT_WALL_ONLY | 14904 | 14207 | 3 | 14207 | 359 | 19.0442 | -0.2321 | 0.2756 | 0.4546 | -0.0156 | 0.1942 | -0.5876 | 0.5675 | 1.2218 | 3297.0075 | 0.2925 | -0.2167 | -0.1571 |
| TOP_GEX_OI_CLUSTERS_ONLY | 6209 | 5965 | 3 | 5965 | 255 | 14.9125 | -0.2234 | 0.3006 | 0.4592 | -0.0194 | 0.2091 | -0.5909 | 0.546 | 1.1851 | 1340.5628 | 0.349 | -0.2094 | -0.126 |
| OI_NODES_ONLY | 1111 | 1081 | 3 | 1081 | 30 | 29.2162 | -0.2342 | 0.2871 | 0.4644 | -0.0234 | 0.2031 | -0.6133 | 0.6034 | 1.2669 | 254.8964 | 0.4 | -0.266 | 0.0311 |

## Matched controls

Matched controls are sampled from price-control events using symbol/day/direction/time/distance buckets where possible, with documented fallback matching. This is more appropriate than the raw unequal-N comparison from Phase 3C.1.

| comparison | side | matched_rows | strict_match_rows | fallback_match_rows | match_quality | N | unique_days | trades_per_symbol_day | expectancy_R | profit_factor | win_rate | median_R | avg_winner | avg_loser | MFE | MAE | max_DD | positive_day_pct | day_block_ci_low | day_block_ci_high |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ALL_OPTIONS_LEVEL_EVENTS | OPTIONS_LEVEL | 43703 | 17735 | 25968 | SOURCE | 43703 | 385 | 39.73 | -0.225 | 0.2827 | 0.4698 | -0.0075 | 0.1888 | -0.5917 | 0.5563 | 1.1978 | 9835.8017 | 0.1532 | -0.2427 | -0.1986 |
| ALL_OPTIONS_LEVEL_EVENTS | RANDOM_MATCHED_LEVEL | 43703 | 17735 | 25968 | {"STRICT_SYMBOL_DAY_DIRECTION_TIME_DISTANCE": 17735, "SYMBOL_DAY_DIRECTION": 11093, "SYMBOL_DAY_DIRECTION_TIME": 8634, "SYMBOL_DIRECTION": 6241} | 43703 | 383 | 43.6158 | -0.1476 | 0.4053 | 0.5521 | 0.0064 | 0.1822 | -0.554 | 0.5988 | 1.048 | 6469.1633 | 0.2689 | -0.171 | -0.1232 |

## GEX model comparison under equal generation

| model | N | unique_days | trades_per_symbol_day | expectancy_R | profit_factor | win_rate | median_R | avg_winner | avg_loser | MFE | MAE | max_DD | positive_day_pct | day_block_ci_low | day_block_ci_high |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GEX_MODEL_A_CALL_POSITIVE_PUT_NEGATIVE | 15034 | 385 | 13.6797 | -0.2227 | 0.2846 | 0.474 | -0.0059 | 0.1869 | -0.5918 | 0.5562 | 1.1984 | 3349.9504 | 0.1688 | -0.2418 | -0.1974 |
| GEX_MODEL_B_CALL_NEGATIVE_PUT_POSITIVE | 15034 | 385 | 13.6797 | -0.2227 | 0.2846 | 0.474 | -0.0059 | 0.1869 | -0.5918 | 0.5562 | 1.1984 | 3349.9504 | 0.1688 | -0.2418 | -0.1974 |
| GEX_MODEL_C_ABSOLUTE_GAMMA_CONCENTRATION | 13635 | 385 | 12.7549 | -0.2301 | 0.2787 | 0.4605 | -0.0148 | 0.1931 | -0.5915 | 0.5565 | 1.1964 | 3139.9432 | 0.1558 | -0.2456 | -0.1983 |

Model C sign-agnostic gamma concentration is negative in this exploratory replay and does not outperform signed models enough to support an edge claim.

## Reclaim state machine audit

The historical replay uses the same detector sequence:

`APPROACH/SWEEP on previous+confirmation bars -> RECLAIM close -> CONFIRMATION closed candle -> ENTRY no earlier than a future bar`

Audit findings:

- Simple crossing only: not intentionally accepted by detector; detector requires sweep through the zone and close reclaim/loss of zone.
- Same confirmation-candle entry: not observed as a required fill path; simulator evaluates future bars after confirmation.
- Entry before confirmation close: 0
- Trace sample size: 100

Entry delay distribution:

| entry_delay_bucket | N |
| --- | --- |
| NEXT_CANDLE | 42134 |
| ONE_CANDLE_AFTER | 1040 |
| TWO_PLUS_CANDLES_AFTER | 529 |

Manual trace samples are in `historical_reclaim_trace_sample.csv`.

## Forward excursion before stop

| variant | N | P_plus_0_25R_before_stop | P_plus_0_5R_before_stop | P_plus_1R_before_stop | avg_MFE_R | avg_MAE_R |
| --- | --- | --- | --- | --- | --- | --- |
| ALL_OPTIONS | 43703 | 0.3969 | 0.2307 | 0.12 | 0.5563 | 1.1978 |
| DEDUP_30M | 18608 | 0.4535 | 0.2776 | 0.1521 | 0.6875 | 1.2217 |
| ECONOMIC_DEDUP_30M_CLUSTER_0_30_ATR | 18556 | 0.4523 | 0.2769 | 0.1516 | 0.6848 | 1.2181 |

Ordering note: Phase 3C.1 did not persist exact per-event future-bar path ordering. These probabilities are MFE-threshold approximations from replay output, not strict tick-ordered before-stop measurements.

## D-1 static vs intraday AlgoX stability

| symbol | status | historical_trade_start | historical_trade_end | algox_snapshot_start | algox_snapshot_end | overlapping_trade_days | level_persistence_rate | gamma_flip_median_abs_deviation | call_wall_median_abs_deviation | put_wall_median_abs_deviation | note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SPY | NO_OVERLAPPING_ALGOX_INTRADAY_ARCHIVE | 2024-01-03 | 2025-12-12 | 2026-09-01 | 2026-09-04 | 0 |  |  |  |  | Historical replay covers 2024-2025; local AlgoX archive currently starts in 2026 for these symbols. |
| QQQ | NO_OVERLAPPING_ALGOX_INTRADAY_ARCHIVE | 2024-01-03 | 2025-12-15 | 2026-09-01 | 2026-09-04 | 0 |  |  |  |  | Historical replay covers 2024-2025; local AlgoX archive currently starts in 2026 for these symbols. |
| IWM | NO_OVERLAPPING_ALGOX_INTRADAY_ARCHIVE | 2024-01-03 | 2025-12-15 | 2026-09-01 | 2026-09-04 | 0 |  |  |  |  | Historical replay covers 2024-2025; local AlgoX archive currently starts in 2026 for these symbols. |

This section is not a pass/fail on the strategy. It says only that this workspace currently lacks overlapping 2024-2025 intraday AlgoX history needed to validate D-1 level persistence.

## Options data / GEX formula sanity audit

Formula audited: `gamma * open_interest * 100 * spot_reference^2 * 0.01`.

- Contract multiplier: 100
- Call/put sign models: A, B, C retained as research variants
- Formula/wall mismatches in sampled rows: 0

| symbol | trade_date | source_chain_date | contract_rows | duplicate_contract_rows | oi_missing_pct | iv_missing_pct | gamma_missing_pct | negative_gamma_rows | bid_gt_ask_rows | call_wall_matches | put_wall_matches | gamma_flip_abs_deviation |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| IWM | 2024-01-03 | 2024-01-02 | 4520 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | True | True | 0.0 |
| IWM | 2024-08-27 | 2024-08-26 | 4788 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | True | True | 0.0 |
| IWM | 2025-04-24 | 2025-04-23 | 5300 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | True | True | 0.0 |
| IWM | 2025-12-15 | 2025-12-12 | 4650 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | True | True | 0.0 |
| QQQ | 2024-01-03 | 2024-01-02 | 12206 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | True | True | 0.0 |
| QQQ | 2024-08-27 | 2024-08-26 | 6966 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | True | True | 0.0 |
| QQQ | 2025-04-23 | 2025-04-22 | 9982 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | True | True | 0.0 |
| QQQ | 2025-12-15 | 2025-12-12 | 8450 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | True | True | 0.0 |
| SPY | 2024-01-03 | 2024-01-02 | 7950 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | True | True | 0.0 |
| SPY | 2024-08-27 | 2024-08-26 | 9732 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | True | True | 0.0 |
| SPY | 2025-04-23 | 2025-04-22 | 11150 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | True | True | 0.0 |
| SPY | 2025-12-12 | 2025-12-11 | 10924 | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | True | True | 0.0 |

Full sampled formula audit is in `historical_gex_formula_audit.csv`.

## Validity verdict

- Phase 3C.1 should be treated as a valid mechanical replay of `D1_EOD_STATIC_OPTIONS`, not as a direct test of the live intraday-updating strategy.
- The high trade count is materially inflated by repeated static-level interactions and lack of event-level cooldown/zone deduplication.
- Matched controls and top-K/clustered level variants are required before any historical edge statement is credible.
- The dataset remains `EXPLORATORY_RESEARCH`, not `SERIOUS_BACKTEST`, until the 5m bars and option chains are independently licensed/cross-validated.
- No live strategy change is justified by this audit.

## Output files

- `historical_trade_frequency_audit.csv`
- `historical_level_count_audit.csv`
- `historical_dedup_variants.csv`
- `historical_level_importance.csv`
- `historical_matched_controls.csv`
- `historical_reclaim_trace_sample.csv`
- `historical_d1_vs_intraday_levels.csv`
- `historical_gex_formula_audit.csv`
