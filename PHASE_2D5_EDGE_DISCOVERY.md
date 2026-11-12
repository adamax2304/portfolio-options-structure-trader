# Phase 2D.5 Edge Discovery & Loss Attribution

Generated: 2026-09-03T20:24:51.278989+00:00

Diagnosis only. No setup definitions, thresholds, confluence weights, stops, targets, trade management, watchlist, macro guard, provider gates, live-trading safeguards, or Portfolio OS isolation were changed.

## Plain-English answers

1. **Where did most losses come from?** The largest cumulative loss contributors are shown in the Worst 10 table below. Worst-two-symbol loss concentration is 8.2% of gross losses.
2. **Are losses concentrated or broad-based?** Broad enough that the current evidence does not blame only one or two symbols.
3. **Do LONG and SHORT behave differently?** LONG expectancy is 0.019R; SHORT expectancy is -0.2215R.
4. **Do SPY/QQQ/IWM behave better than individual stocks?** INDEX_ETF expectancy is -0.1016R; single-stock expectancy is -0.0801R.
5. **Which options level type performs best?** Best current level bucket: GEX_NODE with expectancy -0.0733R. Worst: GAMMA_FLIP.
6. **Does confluence score predict outcomes?** Losses are not explained solely by low-score buckets (-0.2463R low-score vs -44.0912R outside low-score).
7. **Does data quality predict outcome?** Best data-quality bucket: FREE_LIMITED; worst: FREE_LIMITED.
8. **Which time of day is best/worst?** Best time bucket: 11:30-13:00; worst time bucket: 14:30-15:30.
9. **Does any subset show positive entry edge before trade-management effects?** Overall filled-entry path shows P(+0.5R before -1R)=61.8%; P(+1R before -1R)=51.4%. Segment-level probabilities are in `edge_entry_excursion.csv` and `edge_interactions.csv`.
10. **Does any candidate survive holdout/robustness tests?** 1 candidate bucket(s) currently survive the holdout screen with N >= 20, expectancy > 0, and PF > 1; robustness details are in `edge_robustness.csv`.
11. **What should be tested prospectively next?** Keep collection unchanged and register only the candidate buckets below as hypotheses. No parameter change is supported until a candidate survives prospective forward validation.

## Overall canonical forward sample

- Unique natural setup rows: 619
- Resolved canonical rows used for expectancy: 565
- Expectancy: -0.0785R
- Profit factor: 0.7162
- Win rate: 43.0%
- Median R: 0.0R
- Avg MFE / MAE: 0.8119R / 0.6364R
- Max drawdown: 45.1976R

## Worst 10 symbols by total R

| bucket | N | total_R | expectancy | profit_factor | win_rate | avg_MFE | avg_MAE | max_drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NET | 17 | -6.7372 | -0.3963 | 0.0734 | 0.2941 | 0.2489 | 0.8879 | 6.8439 |
| META | 16 | -6.1398 | -0.3837 | 0.1811 | 0.4375 | 0.8046 | 1.3889 | 6.5933 |
| COIN | 14 | -5.5888 | -0.3992 | 0.1002 | 0.2857 | 0.4647 | 1.6305 | 5.5888 |
| MU | 31 | -4.3324 | -0.1398 | 0.1798 | 0.4194 | 0.3684 | 0.3961 | 4.9672 |
| NVDA | 15 | -3.8405 | -0.256 | 0.3997 | 0.4 | 0.5993 | 0.8638 | 4.2323 |
| INTC | 21 | -3.2548 | -0.155 | 0.4825 | 0.3333 | 0.5162 | 0.4499 | 5.2539 |
| ETN | 7 | -2.9104 | -0.4158 | 0.0832 | 0.1429 | 0.2898 | 0.7762 | 3.1745 |
| ARM | 14 | -2.6259 | -0.1876 | 0.1553 | 0.2143 | 0.2874 | 0.3527 | 3.1085 |
| SMCI | 16 | -2.5548 | -0.1597 | 0.5891 | 0.4375 | 0.7528 | 0.891 | 2.7046 |
| AVGO | 15 | -2.3729 | -0.1582 | 0.5503 | 0.2667 | 0.5579 | 0.5018 | 3.0926 |

## Best 10 symbols by total R

| bucket | N | total_R | expectancy | profit_factor | win_rate | avg_MFE | avg_MAE | max_drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| OKLO | 36 | 9.186 | 0.2552 | 1.7398 | 0.5833 | 1.0345 | 0.6625 | 3.0583 |
| RIOT | 7 | 6.5064 | 0.9295 | 7.3432 | 0.2857 | 1.7014 | 0.4555 | 1.0257 |
| TSLA | 29 | 2.1632 | 0.0746 | 1.347 | 0.6207 | 1.7049 | 0.5128 | 2.6233 |
| XLK | 3 | 0.829 | 0.2763 | infinite | 0.6667 | 0.9475 | 0.2163 | 0.0 |
| MSTR | 20 | 0.6941 | 0.0347 | 1.3383 | 0.45 | 0.4954 | 0.2938 | 1.747 |
| SOXX | 5 | 0.5512 | 0.1102 | infinite | 0.4 | 0.3946 | 0.148 | 0.0 |
| CLSK | 5 | 0.3815 | 0.0763 | 1.3703 | 0.2 | 0.6905 | 0.3975 | 1.0303 |
| XBI | 2 | 0.3412 | 0.1706 | infinite | 0.5 | 0.6449 | 0.2313 | 0.0 |
| IONQ | 9 | 0.3204 | 0.0356 | 1.1549 | 0.2222 | 0.5621 | 0.3918 | 1.0412 |
| QQQ | 7 | 0.1708 | 0.0244 | 8.0208 | 0.7143 | 0.2506 | 0.4429 | 0.0243 |

## Symbols with N < 5

| bucket | N | total_R | expectancy | sample_label |
| --- | --- | --- | --- | --- |
| ARKK | 4 | -1.0707 | -0.2677 | INSUFFICIENT_SAMPLE |
| GOOGL | 2 | -2.1195 | -1.0598 | INSUFFICIENT_SAMPLE |
| KRE | 2 | -1.0726 | -0.5363 | INSUFFICIENT_SAMPLE |
| MARA | 2 | -2.0668 | -1.0334 | INSUFFICIENT_SAMPLE |
| NNE | 2 | 0.0 | 0.0 | INSUFFICIENT_SAMPLE |
| QBTS | 1 | 0.0 | 0.0 | INSUFFICIENT_SAMPLE |
| RGTI | 1 | -1.048 | -1.048 | INSUFFICIENT_SAMPLE |
| RIVN | 1 | -1.0352 | -1.0352 | INSUFFICIENT_SAMPLE |
| XBI | 2 | 0.3412 | 0.1706 | INSUFFICIENT_SAMPLE |
| XLI | 2 | 0.0 | 0.0 | INSUFFICIENT_SAMPLE |
| XLK | 3 | 0.829 | 0.2763 | INSUFFICIENT_SAMPLE |
| XLU | 0 | 0.0 | 0.0 | INSUFFICIENT_SAMPLE |
| XLV | 1 | 0.0629 | 0.0629 | INSUFFICIENT_SAMPLE |

## Direction

| bucket | N | expectancy | profit_factor | win_rate | median_R | avg_MFE | avg_MAE |
| --- | --- | --- | --- | --- | --- | --- | --- |
| LONG | 336 | 0.019 | 1.0922 | 0.4821 | 0.0 | 1.0269 | 0.4441 |
| SHORT | 229 | -0.2215 | 0.4157 | 0.3537 | 0.0 | 0.4965 | 0.9185 |

## Asset class

| bucket | N | expectancy | profit_factor | win_rate | median_R | avg_MFE | avg_MAE |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CRYPTO_RELATED | 48 | -0.0015 | 0.994 | 0.3333 | 0.0 | 0.6754 | 0.763 |
| CYBERSECURITY | 47 | -0.1459 | 0.5355 | 0.3617 | 0.0 | 0.4424 | 0.6884 |
| HIGH_BETA_GROWTH | 17 | -0.1815 | 0.266 | 0.2941 | 0.0 | 0.266 | 0.5536 |
| INDEX_ETF | 12 | -0.1016 | 0.4553 | 0.6667 | 0.0062 | 0.3462 | 0.5673 |
| MEGA_CAP | 69 | -0.1632 | 0.5188 | 0.4928 | 0.0 | 1.0725 | 0.7914 |
| NUCLEAR_ENERGY | 66 | 0.1094 | 1.4641 | 0.4545 | 0.0 | 0.6684 | 0.5444 |
| SECTOR_ETF | 19 | -0.0189 | 0.8325 | 0.3158 | 0.0 | 0.3525 | 0.2406 |
| SEMICONDUCTOR | 144 | -0.1572 | 0.4332 | 0.4236 | 0.0 | 0.5377 | 0.5474 |
| SINGLE_STOCK | 89 | -0.0217 | 0.9227 | 0.5393 | 0.0136 | 1.7627 | 0.7728 |
| SMALL_CAP_SPECULATIVE | 54 | -0.0764 | 0.7517 | 0.3333 | 0.0 | 0.6989 | 0.5864 |

## Score discrimination

| bucket | N | expectancy | profit_factor | win_rate | prob_plus_0_5R_before_minus_1R | prob_plus_1R_before_minus_1R |
| --- | --- | --- | --- | --- | --- | --- |
| 50-54 | 13 | 0.1979 | 3.4706 | 0.6923 | 0.7273 | 0.6 |
| 55-59 | 258 | -0.0109 | 0.9589 | 0.4109 | 0.616 | 0.5152 |
| 60-64 | 84 | -0.2158 | 0.3557 | 0.3452 | 0.5783 | 0.4744 |
| 65-69 | 36 | 0.0285 | 1.1218 | 0.5 | 0.5833 | 0.5429 |
| 70-74 | 154 | -0.1463 | 0.4957 | 0.4805 | 0.6149 | 0.4925 |
| 75-79 | 20 | -0.2229 | 0.1774 | 0.35 | 0.5882 | 0.5333 |

## Confidence and data quality

| bucket | N | expectancy | profit_factor | win_rate | avg_MFE | avg_MAE |
| --- | --- | --- | --- | --- | --- | --- |
| LOW | 565 | -0.0785 | 0.7162 | 0.4301 | 0.8119 | 0.6364 |

| dimension | bucket | N | expectancy | profit_factor | win_rate | avg_MFE | avg_MAE |
| --- | --- | --- | --- | --- | --- | --- | --- |
| data_quality_tier | FREE_LIMITED | 565 | -0.0785 | 0.7162 | 0.4301 | 0.8119 | 0.6364 |
| candle_provider | YFINANCE | 565 | -0.0785 | 0.7162 | 0.4301 | 0.8119 | 0.6364 |
| options_provider | ALGOX | 565 | -0.0785 | 0.7162 | 0.4301 | 0.8119 | 0.6364 |

## Candidate edge registry generated this run

| edge_id | description | sample_n | expectancy | PF | status |
| --- | --- | --- | --- | --- | --- |
| EDGE_2F6F3DDD23 | asset_class_x_direction = CRYPTO_RELATED × LONG | 29 | 0.3218 | 5.4912 | FRAGILE |
| EDGE_F02E0FD12E | symbol = OKLO | 36 | 0.2552 | 1.7398 | FRAGILE |
| EDGE_0A488D96E5 | rr_bucket = 1.5-2 | 46 | 0.2148 | 1.7177 | FRAGILE |
| EDGE_20A4979493 | time_bucket_x_direction = 11:30-13:00 × LONG | 61 | 0.1734 | 1.7211 | FRAGILE |
| EDGE_F644E4D052 | asset_class_x_direction = SMALL_CAP_SPECULATIVE × LONG | 39 | 0.1594 | 1.9908 | FRAGILE |
| EDGE_8872706E94 | asset_class_x_direction = NUCLEAR_ENERGY × LONG | 33 | 0.1507 | 1.6903 | FRAGILE |
| EDGE_72CA2F74C2 | score_bucket_x_direction = 55-59 × LONG | 148 | 0.1455 | 1.8609 | PRELIMINARY_EDGE |
| EDGE_253ED7496A | asset_class = NUCLEAR_ENERGY | 66 | 0.1094 | 1.4641 | FRAGILE |
| EDGE_60C95889DC | symbol = TSLA | 29 | 0.0746 | 1.347 | FRAGILE |
| EDGE_F453D7F2AF | asset_class_x_direction = NUCLEAR_ENERGY × SHORT | 33 | 0.0681 | 1.269 | FRAGILE |
| EDGE_8D62B53B87 | asset_class_x_direction = SINGLE_STOCK × LONG | 44 | 0.0642 | 1.3397 | FRAGILE |
| EDGE_EB14E2ACA0 | direction_x_market_trend = LONG × UNKNOWN | 153 | 0.0616 | 1.2546 | FRAGILE |
| EDGE_476DA1ACB9 | direction_x_gamma_regime = LONG × NEGATIVE_GAMMA | 210 | 0.0555 | 1.2789 | FRAGILE |
| EDGE_82CCA69901 | direction_x_market_trend = LONG × COUNTER_TREND | 28 | 0.0541 | 1.4794 | FRAGILE |
| EDGE_A221B29458 | time_bucket = 11:30-13:00 | 108 | 0.0538 | 1.1847 | FRAGILE |
| EDGE_8B2012BEB9 | symbol = MSTR | 20 | 0.0347 | 1.3383 | FRAGILE |
| EDGE_34D7D8EE77 | score_bucket = 65-69 | 36 | 0.0285 | 1.1218 | FRAGILE |
| EDGE_E3D8305114 | score_bucket_x_level_type = 65-69 × GEX_NODE | 36 | 0.0285 | 1.1218 | FRAGILE |
| EDGE_BD68995843 | level_type_x_direction = GEX_NODE × LONG | 309 | 0.0267 | 1.1264 | FRAGILE |
| EDGE_FEF0464B5D | gamma_distance_bucket = UNKNOWN | 119 | 0.0254 | 1.0908 | FRAGILE |
| EDGE_C2BF2F3981 | direction = LONG | 336 | 0.019 | 1.0922 | FRAGILE |
| EDGE_CBCDF70CF4 | time_bucket_x_direction = 14:30-15:30 × LONG | 22 | 0.012 | 1.0491 | FRAGILE |


## A/B management status

- Paired completed/censored: 433 / 100
- Branch A expectancy/PF: 0.0626 / 1.263
- Branch B expectancy/PF: 0.0281 / 1.1163
- B minus A expectancy/PF: -0.0345 / -0.1467
- Decision: do not promote B yet; keep paired forward collection unchanged.

## Output artifacts

- `edge_master_dataset.parquet`
- `edge_master_dataset.csv`
- `edge_by_symbol.csv`
- `edge_by_direction.csv`
- `edge_by_asset_class.csv`
- `edge_by_time.csv`
- `edge_by_time_of_day.csv`
- `edge_by_score.csv`
- `edge_by_confidence.csv`
- `edge_by_level_type.csv`
- `edge_by_gamma_regime.csv`
- `edge_by_market_alignment.csv`
- `edge_by_data_quality.csv`
- `edge_by_rr.csv`
- `edge_by_candle_provider.csv`
- `edge_by_gamma_distance.csv`
- `edge_entry_excursion.csv`
- `edge_interactions.csv`
- `edge_bootstrap.csv`
- `edge_robustness.csv`
- `edge_holdout.csv`
- `PHASE_2D5_EDGE_DISCOVERY.md`
