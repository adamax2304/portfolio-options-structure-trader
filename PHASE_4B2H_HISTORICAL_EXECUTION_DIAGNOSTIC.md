# Phase 4B.2-H Historical Execution & Edge Decomposition Replay

Generated: `2026-09-07T04:23:45.878548+00:00`

Scope: research-only historical diagnostic. Canonical strategy, live daemon, provider gates, prospective Phase 4B.2 branches, live-execution settings, and Portfolio OS isolation were not modified.

Historical limitation: `HIST_STATIC_D1` uses previous-day EOD options levels. It cannot reconstruct true intraday options persistence, strengthening/weakening, wall migration, gamma-flip migration, or dynamic GEX change. Those remain `FORWARD_ONLY`.

## Top answers

1. Raw directional excursion before management: yes in the sense that historical baseline median MFE is `0.5356`R and mean MFE is `1.9913`R, but realized expectancy remains `-0.1547`R. The raw excursion is fat-tailed, not broadly monetized.
2. 15m structure vs 5m: 5m baseline expectancy `-0.223`R / PF `0.4684` versus 15m confirmation expectancy `-0.1996`R / PF `0.3863`. This is historical/static-D1 only.
3. Direction classification: model-aligned events expectancy `-0.233`R / PF `0.4514` versus naive level direction `0.0247`R / PF `1.0641`. This is diagnostic, not a promotion.
4. Canonical stops: associated stop issue remains visible. S0 expectancy `-0.223`R; S1 zone invalidation `-0.4585`R; S2 15m proxy `-0.2183`R. Best tested stop row: `S2_15M_STRUCTURAL_INVALIDATION_PROXY (SHORT): expectancy -0.0295R, PF 0.9186, N 3731, days 366`.
5. Stopped-trade recovery: `0.6694` of canonical stop-outs had lifecycle MFE >= +0.5R in the post-stop proxy table. Exact post-stop ordering is not proven by this default artifact.
6. Normal winner MAE: historical canonical winner median MAE is `0.8132`R. See `phase4b2h_winner_mae.csv` for P10/P25/P75/P90/P95 by segment.
7. Losers first reaching favorable excursion: among `4944` losing baseline events, +0.5R `0.3896`, +0.7R `0.3032`, +1R `0.2079` before final loss by stored/derived MFE.
8. MFE giveback: median giveback across resolved baseline events is `1.0494`R. Large positive MFE with negative realized R remains an execution/management leak candidate.
9. Breakeven/protection: best research replay row by expectancy is `BE_AFTER_0_5R (SHORT): expectancy 0.5463R, PF 3.9937, N 3731, days 366`. Treat M4 as a structural-trail proxy, not a true live 15m swing manager.
10. Target range matching movement: `highest threshold with >=50% historical reach: 0.5R at rate 0.5054`
11. Natural holding time: median time-to-MFE in historical baseline is `80.0` minutes.
12. Static options info beyond structure: P0 controls expectancy `-0.2023`R / PF `0.4735`; P1 static options+structure `-0.223`R / PF `0.4684`; P4 static options+classifier+15m `-0.2029`R / PF `0.3723`. This does not answer dynamic intraday options edge.
13. Largest avoidable-loss association: `STOP_TOO_TIGHT_CANDIDATE` with share `0.5051` of negative R in its source bucket.
14. Top 3 prospective hypotheses to consider after current frozen Phase 4B.2 branches: historical stop/invalidation branch: S2_15M_STRUCTURAL_INVALIDATION_PROXY (SHORT): expectancy -0.0295R, PF 0.9186, N 3731, days 366; profit-protection extrema-proxy branch: BE_AFTER_0_5R (SHORT): expectancy 0.5463R, PF 3.9937, N 3731, days 366; options-value test: compare P4 expectancy -0.2029R/PF 0.3723 versus P0 -0.2023R/PF 0.4735 prospectively

## Dataset reconciliation

- Parent events written: `8975`
- Historical static-D1 events: `8356`
- Live recorded retrospective events: `619`
- Historical/live branches read: `336065`
- Primary baseline branches used for headline diagnostics: `8975`
- Synthetic/test records: excluded by source filters; no synthetic rows are intentionally included.

## Baseline performance by source

| label | N | unique_days | expectancy | PF | win_rate | median_R | MFE | MAE | max_DD |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| HIST_STATIC_D1 | 8356 | 384 | -0.1547 | 0.6279 | 0.4276 | -0.0675 | 1.9913 | 2.4008 | -1300.9044 |
| LIVE_RECORDED_RETROSPECTIVE | 565 | 2 | -0.0785 | 0.7162 | 0.4301 | 0.0 | 0.8119 | 0.6364 | -45.1976 |

## Stop experiment summary

| data_source | stop_experiment_variant | direction | N | unique_days | expectancy | PF | win_rate | MFE | MAE | stop_frequency |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| HIST_STATIC_D1 | RESEARCH_STRUCTURE_PLUS_0_15_ATR | LONG | 4625 | 377 | -0.2169 | 0.468 | 0.4048 | 1.0014 | 2.7101 | 0.4958 |
| HIST_STATIC_D1 | S0_CANONICAL_STOP | LONG | 4625 | 377 | -0.223 | 0.4684 | 0.3983 | 1.1275 | 2.9635 | 0.5051 |
| HIST_STATIC_D1 | S2_15M_STRUCTURAL_INVALIDATION_PROXY | LONG | 4625 | 377 | -0.2183 | 0.4417 | 0.408 | 0.8071 | 2.2895 | 0.4685 |
| HIST_STATIC_D1 | S1_FULL_OPTIONS_ZONE_INVALIDATION | LONG | 4625 | 377 | -0.4585 | 0.292 | 0.2822 | 2.5565 | 5.7386 | 0.7535 |
| HIST_STATIC_D1 | S3_LAST_CONFIRMED_HL_LH_INVALIDATION_PROXY | LONG | 4625 | 377 | -0.2224 | 0.447 | 0.4065 | 0.9056 | 2.5074 | 0.4919 |
| HIST_STATIC_D1 | RESEARCH_STRUCTURE_PLUS_0_15_ATR | SHORT | 3731 | 366 | -0.0616 | 0.8462 | 0.4648 | 2.7815 | 1.5437 | 0.5074 |
| HIST_STATIC_D1 | S0_CANONICAL_STOP | SHORT | 3731 | 366 | -0.0701 | 0.8296 | 0.464 | 3.0621 | 1.7033 | 0.5318 |
| HIST_STATIC_D1 | S1_FULL_OPTIONS_ZONE_INVALIDATION | SHORT | 3731 | 366 | -0.3445 | 0.4535 | 0.3286 | 5.383 | 3.8213 | 0.7703 |
| HIST_STATIC_D1 | S2_15M_STRUCTURAL_INVALIDATION_PROXY | SHORT | 3731 | 366 | -0.0295 | 0.9186 | 0.4795 | 2.3195 | 1.284 | 0.4618 |
| HIST_STATIC_D1 | S3_LAST_CONFIRMED_HL_LH_INVALIDATION_PROXY | SHORT | 3731 | 366 | -0.051 | 0.868 | 0.4693 | 2.5583 | 1.4179 | 0.4862 |
| LIVE_RECORDED_RETROSPECTIVE | S0_CANONICAL_STOP | LONG | 592 | 2 | 0.1089 | 1.5855 | 0.4764 | 1.0672 | 0.4357 | 0.3784 |
| LIVE_RECORDED_RETROSPECTIVE | S0_CANONICAL_STOP | SHORT | 406 | 2 | -0.2012 | 0.4391 | 0.3473 | 0.4598 | 0.9185 | 0.5369 |

## Profit protection / breakeven summary

| management_replay_variant | direction | N | unique_days | expectancy | PF | win_rate | BE_exit_rate | max_DD | research_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BE_AFTER_0_5R | LONG | 4625 | 377 | 0.2194 | 2.018 | 0.5046 | 0.1055 | -65.4946 | HYPOTHESIS_GENERATING_POSITIVE_HOLDOUT_REQUIRED |
| BE_AFTER_0_7R | LONG | 4625 | 377 | 0.166 | 1.634 | 0.4843 | 0.0759 | -89.6943 | HYPOTHESIS_GENERATING_POSITIVE_HOLDOUT_REQUIRED |
| BE_AFTER_1R | LONG | 4625 | 377 | 0.1053 | 1.3373 | 0.4621 | 0.0437 | -155.9064 | HYPOTHESIS_GENERATING_POSITIVE_HOLDOUT_REQUIRED |
| M1_HALF_0_5R_RUNNER | LONG | 4625 | 377 | 0.1201 | 1.5572 | 0.6102 | 0.1055 | -73.4509 | HYPOTHESIS_GENERATING_POSITIVE_HOLDOUT_REQUIRED |
| BE_AFTER_TP1 | LONG | 4625 | 377 | 0.1053 | 1.3373 | 0.4621 | 0.0437 | -155.9064 | HYPOTHESIS_GENERATING_POSITIVE_HOLDOUT_REQUIRED |
| BE_AFTER_STRUCTURE_CONFIRMATION_PROXY | LONG | 4625 | 377 | 0.1053 | 1.3373 | 0.4621 | 0.0437 | -155.9064 | HYPOTHESIS_GENERATING_POSITIVE_HOLDOUT_REQUIRED |
| M4_STRUCTURE_TRAIL_PROXY_NO_IMMEDIATE_BE | LONG | 4625 | 377 | 0.0395 | 1.1173 | 0.4757 | 0.0 | -261.8995 | HYPOTHESIS_GENERATING_POSITIVE_HOLDOUT_REQUIRED |
| NO_BE | LONG | 4625 | 377 | -0.0529 | 0.8722 | 0.3981 | 0.0 | -487.7266 | HYPOTHESIS_GENERATING_NEGATIVE_OR_MIXED |
| M3_PROTECT_AFTER_1R | LONG | 4625 | 377 | 0.1053 | 1.3373 | 0.4621 | 0.0437 | -155.9064 | HYPOTHESIS_GENERATING_POSITIVE_HOLDOUT_REQUIRED |
| M0_CURRENT | LONG | 4625 | 377 | 0.0767 | 1.2459 | 0.5057 | 0.0437 | -167.4121 | HYPOTHESIS_GENERATING_POSITIVE_HOLDOUT_REQUIRED |
| M2_HALF_0_7R_RUNNER | LONG | 4625 | 377 | 0.0936 | 1.3577 | 0.5602 | 0.0759 | -96.5169 | HYPOTHESIS_GENERATING_POSITIVE_HOLDOUT_REQUIRED |
| BE_AFTER_1R | SHORT | 3731 | 366 | 0.4454 | 2.6399 | 0.5419 | 0.0616 | -49.6616 | HYPOTHESIS_GENERATING_POSITIVE_HOLDOUT_REQUIRED |

## Options-value ablation

| ablation | direction | N | unique_days | expectancy | PF | win_rate | MFE | MAE | availability | research_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P0_PRICE_STRUCTURE_ONLY_CONTROLS | LONG | 23113 | 377 | -0.2023 | 0.4735 | 0.4067 | 1.0341 | 2.681 | AVAILABLE | HYPOTHESIS_GENERATING_NEGATIVE_OR_MIXED |
| P0_PRICE_STRUCTURE_ONLY_CONTROLS | SHORT | 18635 | 366 | -0.0466 | 0.8761 | 0.4688 | 3.1568 | 1.5462 | AVAILABLE | HYPOTHESIS_GENERATING_NEGATIVE_OR_MIXED |
| P1_PRICE_STRUCTURE_PLUS_STATIC_STRONG_OPTIONS_LEVEL | LONG | 4625 | 377 | -0.223 | 0.4684 | 0.3983 | 1.1275 | 2.9635 | AVAILABLE | HYPOTHESIS_GENERATING_NEGATIVE_OR_MIXED |
| P1_PRICE_STRUCTURE_PLUS_STATIC_STRONG_OPTIONS_LEVEL | SHORT | 3731 | 366 | -0.0701 | 0.8296 | 0.464 | 3.0621 | 1.7033 | AVAILABLE | HYPOTHESIS_GENERATING_NEGATIVE_OR_MIXED |
| P2_PERSISTENT_STRENGTHENING_OPTIONS_LEVEL |  | 0 | 0 |  |  |  |  |  | HISTORICALLY_UNAVAILABLE_FORWARD_ONLY | DESCRIPTIVE_INSUFFICIENT_SAMPLE |
| P3_OPTIONS_PLUS_HISTORICAL_DIRECTION_CLASSIFIER | LONG | 4343 | 374 | -0.233 | 0.4514 | 0.3926 | 1.0854 | 3.0007 | AVAILABLE | HYPOTHESIS_GENERATING_NEGATIVE_OR_MIXED |
| P3_OPTIONS_PLUS_HISTORICAL_DIRECTION_CLASSIFIER | SHORT | 3436 | 357 | -0.0776 | 0.8134 | 0.4601 | 3.1274 | 1.6873 | AVAILABLE | HYPOTHESIS_GENERATING_NEGATIVE_OR_MIXED |
| P4_OPTIONS_DIRECTION_CLASSIFIER_PLUS_15M_CONFIRMATION | LONG | 2127 | 357 | -0.2029 | 0.3723 | 0.3883 | 0.5931 | 1.7386 | AVAILABLE | HYPOTHESIS_GENERATING_NEGATIVE_OR_MIXED |
| P4_OPTIONS_DIRECTION_CLASSIFIER_PLUS_15M_CONFIRMATION | SHORT | 1357 | 305 | -0.0694 | 0.7963 | 0.4584 | 2.0509 | 1.3293 | AVAILABLE | HYPOTHESIS_GENERATING_NEGATIVE_OR_MIXED |

## 5m vs 15m structure

| strategy_variant | confirmation_tf | direction | N | unique_days | expectancy | PF | win_rate | MFE | MAE |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| VARIANT_A_HIST_5M_CONFIRM_5M_ENTRY | 5m | LONG | 4625 | 377 | -0.223 | 0.4684 | 0.3983 | 1.1275 | 2.9635 |
| VARIANT_A_HIST_5M_CONFIRM_5M_ENTRY | 5m | SHORT | 3731 | 366 | -0.0701 | 0.8296 | 0.464 | 3.0621 | 1.7033 |
| VARIANT_B_HIST_15M_CONFIRM_5M_ENTRY | 15m | LONG | 2296 | 362 | -0.1996 | 0.3863 | 0.3933 | 0.6221 | 1.7591 |
| VARIANT_E_HIST_30M_CONTEXT_15M_SETUP_5M_ENTRY | 15m | LONG | 2256 | 362 | -0.1992 | 0.3824 | 0.3923 | 0.606 | 1.7066 |
| VARIANT_B_HIST_15M_CONFIRM_5M_ENTRY | 15m | SHORT | 1527 | 309 | -0.0754 | 0.7801 | 0.4578 | 1.9804 | 1.3433 |
| VARIANT_E_HIST_30M_CONTEXT_15M_SETUP_5M_ENTRY | 15m | SHORT | 1499 | 306 | -0.0729 | 0.7855 | 0.4583 | 1.9649 | 1.3266 |

## Direction classifier comparison

| data_source | direction_model | direction | N | unique_days | expectancy | PF | win_rate | model_coverage | model_alignment_rate | all_events_expectancy |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| HIST_STATIC_D1 | MODEL_DIRECTION_CLASSIFIER | LONG | 4343 | 374 | -0.233 | 0.4514 | 0.3926 | 0.939 | 0.939 | -0.223 |
| HIST_STATIC_D1 | MODEL_DIRECTION_CLASSIFIER | SHORT | 3436 | 357 | -0.0776 | 0.8134 | 0.4601 | 0.9209 | 0.9209 | -0.0701 |
| LIVE_RECORDED_RETROSPECTIVE | MODEL_DIRECTION_CLASSIFIER | LONG | 268 | 2 | -0.0066 | 0.971 | 0.4813 | 0.806 | 0.806 | 0.019 |
| LIVE_RECORDED_RETROSPECTIVE | MODEL_DIRECTION_CLASSIFIER | SHORT | 153 | 2 | -0.2147 | 0.3991 | 0.366 | 0.6759 | 0.6759 | -0.2215 |
| HIST_STATIC_D1 | NAIVE_LEVEL_DIRECTION | LONG | 1059 | 269 | -0.1362 | 0.647 | 0.44 | 0.6288 | 0.229 | -0.223 |
| HIST_STATIC_D1 | NAIVE_LEVEL_DIRECTION | SHORT | 1434 | 305 | 0.0247 | 1.0641 | 0.5014 | 0.6449 | 0.3843 | -0.0701 |
| LIVE_RECORDED_RETROSPECTIVE | NAIVE_LEVEL_DIRECTION | LONG | 0 | 0 |  |  |  | 0.0 | 0.0 | 0.019 |
| LIVE_RECORDED_RETROSPECTIVE | NAIVE_LEVEL_DIRECTION | SHORT | 0 | 0 |  |  |  | 0.0 | 0.0 | -0.2215 |
| HIST_STATIC_D1 | PRICE_STRUCTURE_ONLY | LONG | 4625 | 377 | -0.223 | 0.4684 | 0.3983 | 1.0 | 1.0 | -0.223 |
| HIST_STATIC_D1 | PRICE_STRUCTURE_ONLY | SHORT | 3731 | 366 | -0.0701 | 0.8296 | 0.464 | 1.0 | 1.0 | -0.0701 |
| LIVE_RECORDED_RETROSPECTIVE | PRICE_STRUCTURE_ONLY | LONG | 336 | 2 | 0.019 | 1.0922 | 0.4821 | 1.0 | 1.0 | 0.019 |
| LIVE_RECORDED_RETROSPECTIVE | PRICE_STRUCTURE_ONLY | SHORT | 229 | 2 | -0.2215 | 0.4157 | 0.3537 | 1.0 | 1.0 | -0.2215 |

## Loss attribution

| data_source | primary_loss_reason | causality_language | N | total_negative_R | share_of_negative_R | unique_days |
| --- | --- | --- | --- | --- | --- | --- |
| HIST_STATIC_D1 | STOP_TOO_TIGHT_CANDIDATE | ASSOCIATED | 1755 | 1755.0 | 0.5051 | 328 |
| HIST_STATIC_D1 | NO_LEVEL_EDGE | ASSOCIATED | 1512 | 1052.4219 | 0.3029 | 331 |
| HIST_STATIC_D1 | UNKNOWN | UNKNOWN | 1231 | 553.0915 | 0.1592 | 318 |
| HIST_STATIC_D1 | STRUCTURE_MISREAD | ASSOCIATED | 112 | 48.7715 | 0.014 | 67 |
| HIST_STATIC_D1 | WRONG_DIRECTION | ASSOCIATED | 107 | 42.7465 | 0.0123 | 63 |
| HIST_STATIC_D1 | BAD_TARGET | ASSOCIATED | 66 | 22.7911 | 0.0066 | 39 |
| LIVE_RECORDED_RETROSPECTIVE | NO_LEVEL_EDGE | ASSOCIATED | 94 | 96.1287 | 0.6154 | 2 |
| LIVE_RECORDED_RETROSPECTIVE | UNKNOWN | UNKNOWN | 26 | 22.0838 | 0.1414 | 2 |
| LIVE_RECORDED_RETROSPECTIVE | BAD_STOP | ASSOCIATED | 19 | 18.1154 | 0.116 | 2 |
| LIVE_RECORDED_RETROSPECTIVE | WRONG_DIRECTION | ASSOCIATED | 15 | 15.5792 | 0.0997 | 2 |
| LIVE_RECORDED_RETROSPECTIVE | STRUCTURE_MISREAD | ASSOCIATED | 6 | 4.2816 | 0.0274 | 2 |
| LIVE_RECORDED_RETROSPECTIVE | BAD_TARGET | ASSOCIATED | 1 | 0.0199 | 0.0001 | 1 |

## Counterfactual rescue waterfall

Top rescue stages: `{"ALTERNATIVE_STOP": 1521, "NOT_RESCUED_BY_TESTED_COUNTERFACTUALS": 2637, "STRUCTURE_CONFIRMATION": 670}`

## Discovery / holdout and walk-forward

| data_source | sample_split | strategy_variant | direction | N | unique_days | expectancy | PF | win_rate | historical_result_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| HIST_STATIC_D1 | DISCOVERY | VARIANT_A_HIST_5M_CONFIRM_5M_ENTRY | LONG | 2785 | 226 | -0.1813 | 0.5598 | 0.4136 | HYPOTHESIS_GENERATING_NEGATIVE_OR_MIXED |
| HIST_STATIC_D1 | DISCOVERY | VARIANT_A_HIST_5M_CONFIRM_5M_ENTRY | SHORT | 2489 | 220 | -0.1309 | 0.6915 | 0.4512 | HYPOTHESIS_GENERATING_NEGATIVE_OR_MIXED |
| HIST_STATIC_D1 | HOLDOUT | VARIANT_A_HIST_5M_CONFIRM_5M_ENTRY | LONG | 1840 | 151 | -0.2862 | 0.3363 | 0.375 | HYPOTHESIS_GENERATING_NEGATIVE_OR_MIXED |
| HIST_STATIC_D1 | DISCOVERY | VARIANT_B_HIST_15M_CONFIRM_5M_ENTRY | LONG | 1342 | 218 | -0.162 | 0.497 | 0.4128 | HYPOTHESIS_GENERATING_NEGATIVE_OR_MIXED |
| HIST_STATIC_D1 | DISCOVERY | VARIANT_E_HIST_30M_CONTEXT_15M_SETUP_5M_ENTRY | LONG | 1316 | 218 | -0.1618 | 0.4933 | 0.4119 | HYPOTHESIS_GENERATING_NEGATIVE_OR_MIXED |
| HIST_STATIC_D1 | HOLDOUT | VARIANT_A_HIST_5M_CONFIRM_5M_ENTRY | SHORT | 1242 | 146 | 0.0518 | 1.1343 | 0.4895 | HYPOTHESIS_GENERATING_POSITIVE_HOLDOUT_REQUIRED |
| HIST_STATIC_D1 | DISCOVERY | VARIANT_B_HIST_15M_CONFIRM_5M_ENTRY | SHORT | 1083 | 189 | -0.1263 | 0.6464 | 0.4469 | HYPOTHESIS_GENERATING_NEGATIVE_OR_MIXED |
| HIST_STATIC_D1 | DISCOVERY | VARIANT_E_HIST_30M_CONTEXT_15M_SETUP_5M_ENTRY | SHORT | 1065 | 189 | -0.1215 | 0.6565 | 0.4479 | HYPOTHESIS_GENERATING_NEGATIVE_OR_MIXED |
| HIST_STATIC_D1 | HOLDOUT | VARIANT_B_HIST_15M_CONFIRM_5M_ENTRY | LONG | 954 | 144 | -0.2525 | 0.2343 | 0.3658 | HYPOTHESIS_GENERATING_NEGATIVE_OR_MIXED |
| HIST_STATIC_D1 | HOLDOUT | VARIANT_E_HIST_30M_CONTEXT_15M_SETUP_5M_ENTRY | LONG | 940 | 144 | -0.2516 | 0.2309 | 0.3649 | HYPOTHESIS_GENERATING_NEGATIVE_OR_MIXED |
| HIST_STATIC_D1 | HOLDOUT | VARIANT_B_HIST_15M_CONFIRM_5M_ENTRY | SHORT | 444 | 120 | 0.0486 | 1.1577 | 0.4842 | HYPOTHESIS_GENERATING_POSITIVE_HOLDOUT_REQUIRED |
| HIST_STATIC_D1 | HOLDOUT | VARIANT_E_HIST_30M_CONTEXT_15M_SETUP_5M_ENTRY | SHORT | 434 | 117 | 0.0463 | 1.1513 | 0.4839 | HYPOTHESIS_GENERATING_POSITIVE_HOLDOUT_REQUIRED |

| window_start | window_leg | N | unique_days | expectancy | PF | win_rate | positive_day_pct | day_block_ci_low | day_block_ci_high |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2024-06-01 | DISCOVERY_6M | 2488 | 126 | -0.1576 | 0.6103 | 0.4289 | 0.2937 | -4.0178 | -2.1857 |
| 2024-06-01 | HOLDOUT_3M | 1255 | 60 | -0.1389 | 0.6574 | 0.4263 | 0.2667 | -4.2442 | -1.3116 |
| 2024-09-01 | DISCOVERY_6M | 2435 | 123 | -0.1534 | 0.6246 | 0.4234 | 0.2927 | -3.4836 | -2.1454 |
| 2024-09-01 | HOLDOUT_3M | 1942 | 63 | -0.1556 | 0.6434 | 0.432 | 0.2857 | -6.2076 | -3.5439 |
| 2024-12-01 | DISCOVERY_6M | 3197 | 123 | -0.149 | 0.6487 | 0.4298 | 0.2764 | -5.4102 | -3.5239 |
| 2024-12-01 | HOLDOUT_3M | 1292 | 63 | -0.1377 | 0.6516 | 0.4296 | 0.2857 | -4.8157 | -2.287 |
| 2025-03-01 | DISCOVERY_6M | 3234 | 126 | -0.1484 | 0.6465 | 0.431 | 0.2857 | -4.2545 | -2.9164 |
| 2025-03-01 | HOLDOUT_3M | 1202 | 61 | -0.1758 | 0.5991 | 0.426 | 0.2459 | -4.8066 | -2.3541 |

## Forward-only items explicitly not reconstructed

- true intraday options-level persistence
- strengthening / weakening across live snapshots
- call-wall / put-wall migration
- gamma-flip migration
- dynamic intraday GEX change

These remain prospective-only in Phase 4B.2. Historical static-D1 results must not be merged into forward validation or used for automatic parameter promotion.

## Output files

- `phase4b2h_events.parquet`
- `phase4b2h_stop_comparison.csv`
- `phase4b2h_winner_mae.csv`
- `phase4b2h_stop_recovery.csv`
- `phase4b2h_giveback.csv`
- `phase4b2h_breakeven.csv`
- `phase4b2h_target_distribution.csv`
- `phase4b2h_holding_horizon.csv`
- `phase4b2h_structure_5m_vs_15m.csv`
- `phase4b2h_direction_classifier.csv`
- `phase4b2h_entry_comparison.csv`
- `phase4b2h_options_ablation.csv`
- `phase4b2h_loss_attribution.csv`
- `phase4b2h_counterfactual_rescue.csv`
- `phase4b2h_discovery_holdout.csv`
- `phase4b2h_walkforward.csv`
- `phase4b2h_management_simulation.csv`

## Decision note

No historical result in this report is `FORWARD_SUPPORTED`. Any useful branch remains hypothesis-generating until validated prospectively across independent RTH days.
