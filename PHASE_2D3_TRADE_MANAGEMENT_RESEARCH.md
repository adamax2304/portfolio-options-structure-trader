# Phase 2D.3 Trade Management Research

Generated: 2026-09-02T16:36:28.239912+00:00

Counterfactual research only. Canonical paper trades were not overwritten and live Free Validation behavior remains unchanged.

## Sample

- Closed natural trades replayed: 105
- Actual canonical expectancy: -0.0276R
- Baseline replay expectancy: -0.0468
- Best replay variant by expectancy: TM_V3_TP1_PLUS_RUNNER at 0.0334R
- Baseline profit factor: 0.8288
- Best replay profit factor: 1.1197

## Variant results

| variant | N | expectancy | median R | profit factor | avg winner | avg loser | sample label |
|---|---:|---:|---:|---:|---:|---:|---|
| TM_V0_CURRENT | 105 | -0.0468 | 0.0815 | 0.8288 | 0.3884 | -0.8546 | usable_preliminary_evidence |
| TM_V1_SCALEOUT_33_33_34 | 105 | 0.0206 | 0.0756 | 1.0687 | 0.593 | -0.7267 | usable_preliminary_evidence |
| TM_V2_SCALEOUT_50_25_25 | 105 | 0.0133 | 0.1242 | 1.0486 | 0.5161 | -0.7982 | usable_preliminary_evidence |
| TM_V3_TP1_PLUS_RUNNER | 105 | 0.0334 | 0.1333 | 1.1197 | 0.512 | -0.9002 | usable_preliminary_evidence |
| TM_V4_FIXED_1_5R | 105 | 0.0247 | -0.0081 | 1.0811 | 0.7887 | -0.714 | usable_preliminary_evidence |
| TM_V4_FIXED_2R | 105 | 0.0219 | -0.0226 | 1.0724 | 0.8199 | -0.7008 | usable_preliminary_evidence |
| TM_V5_STRUCTURE_TARGETS_NO_BE | 105 | 0.0191 | 0.07 | 1.0621 | 0.6003 | -0.7267 | usable_preliminary_evidence |
| TM_V6_STRUCTURE_TARGETS_DELAYED_BE | 105 | 0.0206 | 0.0756 | 1.0687 | 0.593 | -0.7267 | usable_preliminary_evidence |

## MFE conditional analysis

- % reaching +0.25R: 79.0%
- % reaching +0.5R: 53.3%
- % reaching +0.75R: 37.1%
- % reaching +1R: 23.8%
- % reaching +1.5R: 10.5%
- % reaching +2R: 4.8%
- P(+1R reached | +0.5R reached): 44.6%
- P(+1.5R reached | +1R reached): 44.0%
- P(+2R reached | +1R reached): 20.0%

## Stop efficiency

- Losing stop-outs that went positive first: 24
- Stop-outs that reached +0.5R before stopping: 4
- Stop-outs that reached +1R before stopping: 0
- Stop-outs reclaiming entry within 30m: 2
- Average MAE of winners: 0.3815
- Average MAE of losers: 1.2803
- Median stop distance: 2.347
- Breakeven exit frequency: 43/105
- TP1-only exit frequency: 36/105

## Entry-edge summary

| horizon | N | avg forward return | avg MFE | avg MAE | P(+0.5R before -1R) | P(+1R before -1R) | P(+2R before -1R) |
|---|---:|---:|---:|---:|---:|---:|---:|
| 15m | 105 | -0.000705 | 0.4208 | 0.5079 | 34.3% | 13.3% | 0.9% |
| 30m | 105 | -0.000882 | 0.5619 | 0.7033 | 45.7% | 20.0% | 3.8% |
| 60m | 105 | -0.00011 | 0.7937 | 0.8598 | 58.1% | 30.5% | 7.6% |
| 120m | 105 | -0.001063 | 0.9433 | 1.0695 | 52.4% | 32.4% | 11.4% |
| end_of_rth | 105 | -0.001024 | 0.9564 | 1.0794 | 52.4% | 32.4% | 11.4% |

## Segment results excerpt

Full segmented output is in `trade_management_segment_summary.csv`.

| variant | segment | bucket | N | expectancy | profit factor | sample label |
|---|---|---|---:|---:|---:|---|
| TM_V0_CURRENT | direction | LONG | 62 | -0.1308 | 0.546 | usable_preliminary_evidence |
| TM_V0_CURRENT | direction | SHORT | 43 | 0.0744 | 1.2935 | exploratory |
| TM_V0_CURRENT | score_bucket | 50-59 | 50 | -0.0524 | 0.8073 | usable_preliminary_evidence |
| TM_V0_CURRENT | score_bucket | 60-69 | 24 | -0.0249 | 0.9139 | exploratory |
| TM_V0_CURRENT | score_bucket | 70-79 | 31 | -0.0547 | 0.7941 | exploratory |
| TM_V0_CURRENT | level_type | GEX_NODE | 102 | -0.0463 | 0.8293 | usable_preliminary_evidence |
| TM_V1_SCALEOUT_33_33_34 | direction | LONG | 62 | -0.0707 | 0.7681 | usable_preliminary_evidence |
| TM_V1_SCALEOUT_33_33_34 | direction | SHORT | 43 | 0.1522 | 1.5777 | exploratory |
| TM_V1_SCALEOUT_33_33_34 | score_bucket | 50-59 | 50 | -0.0093 | 0.9717 | usable_preliminary_evidence |
| TM_V1_SCALEOUT_33_33_34 | score_bucket | 60-69 | 24 | 0.0842 | 1.2573 | exploratory |
| TM_V1_SCALEOUT_33_33_34 | score_bucket | 70-79 | 31 | 0.0195 | 1.0669 | exploratory |
| TM_V1_SCALEOUT_33_33_34 | level_type | GEX_NODE | 102 | 0.017 | 1.0574 | usable_preliminary_evidence |
| TM_V2_SCALEOUT_50_25_25 | direction | LONG | 62 | -0.0758 | 0.7487 | usable_preliminary_evidence |
| TM_V2_SCALEOUT_50_25_25 | direction | SHORT | 43 | 0.1416 | 1.5486 | exploratory |
| TM_V2_SCALEOUT_50_25_25 | score_bucket | 50-59 | 50 | -0.0106 | 0.9631 | usable_preliminary_evidence |
| TM_V2_SCALEOUT_50_25_25 | score_bucket | 60-69 | 24 | 0.0668 | 1.2239 | exploratory |
| TM_V2_SCALEOUT_50_25_25 | score_bucket | 70-79 | 31 | 0.0103 | 1.0434 | exploratory |
| TM_V2_SCALEOUT_50_25_25 | level_type | GEX_NODE | 102 | 0.0106 | 1.0395 | usable_preliminary_evidence |
| TM_V3_TP1_PLUS_RUNNER | direction | LONG | 62 | -0.0525 | 0.8137 | usable_preliminary_evidence |
| TM_V3_TP1_PLUS_RUNNER | direction | SHORT | 43 | 0.1573 | 1.6225 | exploratory |
| TM_V3_TP1_PLUS_RUNNER | score_bucket | 50-59 | 50 | -0.0128 | 0.9474 | usable_preliminary_evidence |
| TM_V3_TP1_PLUS_RUNNER | score_bucket | 60-69 | 24 | 0.142 | 1.4985 | exploratory |
| TM_V3_TP1_PLUS_RUNNER | score_bucket | 70-79 | 31 | 0.0239 | 1.0959 | exploratory |
| TM_V3_TP1_PLUS_RUNNER | level_type | GEX_NODE | 102 | 0.031 | 1.1115 | usable_preliminary_evidence |
| TM_V4_FIXED_1_5R | direction | LONG | 62 | -0.047 | 0.8656 | usable_preliminary_evidence |
| TM_V4_FIXED_1_5R | direction | SHORT | 43 | 0.1282 | 1.4671 | exploratory |
| TM_V4_FIXED_1_5R | score_bucket | 50-59 | 50 | 0.0249 | 1.0838 | usable_preliminary_evidence |
| TM_V4_FIXED_1_5R | score_bucket | 60-69 | 24 | -0.0275 | 0.9321 | exploratory |
| TM_V4_FIXED_1_5R | score_bucket | 70-79 | 31 | 0.0649 | 1.2302 | exploratory |
| TM_V4_FIXED_1_5R | level_type | GEX_NODE | 102 | 0.0058 | 1.0221 | usable_preliminary_evidence |
| TM_V4_FIXED_2R | direction | LONG | 62 | -0.0832 | 0.7631 | usable_preliminary_evidence |
| TM_V4_FIXED_2R | direction | SHORT | 43 | 0.1733 | 1.6285 | exploratory |
| TM_V4_FIXED_2R | score_bucket | 50-59 | 50 | -0.0067 | 0.986 | usable_preliminary_evidence |
| TM_V4_FIXED_2R | score_bucket | 60-69 | 24 | 0.0524 | 1.1466 | exploratory |
| TM_V4_FIXED_2R | score_bucket | 70-79 | 31 | 0.0443 | 1.1547 | exploratory |
| TM_V4_FIXED_2R | level_type | GEX_NODE | 102 | 0.0135 | 1.0466 | usable_preliminary_evidence |
| TM_V5_STRUCTURE_TARGETS_NO_BE | direction | LONG | 62 | -0.0732 | 0.7578 | usable_preliminary_evidence |
| TM_V5_STRUCTURE_TARGETS_NO_BE | direction | SHORT | 43 | 0.1522 | 1.5777 | exploratory |
| TM_V5_STRUCTURE_TARGETS_NO_BE | score_bucket | 50-59 | 50 | -0.0123 | 0.9581 | usable_preliminary_evidence |
| TM_V5_STRUCTURE_TARGETS_NO_BE | score_bucket | 60-69 | 24 | 0.0842 | 1.2573 | exploratory |
| TM_V5_STRUCTURE_TARGETS_NO_BE | score_bucket | 70-79 | 31 | 0.0195 | 1.0669 | exploratory |
| TM_V5_STRUCTURE_TARGETS_NO_BE | level_type | GEX_NODE | 102 | 0.0156 | 1.0506 | usable_preliminary_evidence |
| TM_V6_STRUCTURE_TARGETS_DELAYED_BE | direction | LONG | 62 | -0.0707 | 0.7681 | usable_preliminary_evidence |
| TM_V6_STRUCTURE_TARGETS_DELAYED_BE | direction | SHORT | 43 | 0.1522 | 1.5777 | exploratory |
| TM_V6_STRUCTURE_TARGETS_DELAYED_BE | score_bucket | 50-59 | 50 | -0.0093 | 0.9717 | usable_preliminary_evidence |
| TM_V6_STRUCTURE_TARGETS_DELAYED_BE | score_bucket | 60-69 | 24 | 0.0842 | 1.2573 | exploratory |
| TM_V6_STRUCTURE_TARGETS_DELAYED_BE | score_bucket | 70-79 | 31 | 0.0195 | 1.0669 | exploratory |
| TM_V6_STRUCTURE_TARGETS_DELAYED_BE | level_type | GEX_NODE | 102 | 0.017 | 1.0574 | usable_preliminary_evidence |

## Free Validation routing watch

This replay does not loosen gates or retro-convert Shadow trades. Current top setup-level Free Validation blockers remain:

| blocker | count |
|---|---:|
| Directional flow or GEX/OI confirmation is insufficient | 130 |
| Options-structure data exceeds Free Validation freshness threshold | 117 |
| Critical market data is stale | 117 |
| Adjusted score 58 is below Free Validation threshold | 30 |
| Adjusted score 57 is below Free Validation threshold | 23 |
| Adjusted score 56 is below Free Validation threshold | 18 |
| Adjusted score 55 is below Free Validation threshold | 16 |
| Adjusted score 59 is below Free Validation threshold | 14 |

## Interpretation guardrail

Subgroups with N < 20 are labeled INSUFFICIENT_SAMPLE. No entry tuning, threshold tuning, target tuning, or production promotion should be made from tiny subgroup wins.

## Artifacts

- trade_management_replay.csv
- mfe_threshold_analysis.csv
- entry_edge_analysis.csv
- stop_efficiency_analysis.csv
- trade_management_segment_summary.csv
- counterfactual_exit_analysis.csv
