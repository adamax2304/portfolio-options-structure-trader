# Phase 2D.6 Forward Edge Validation

Generated: 2026-09-03T16:09:11.588595+00:00

This is a prospective holdout tracker. Phase 2D.5 remains discovery data; no old setup was retrospectively relabeled.

## Activation and guardrails

- Activated at: 2026-09-03T15:57:24.326125+00:00
- Discovery cutoff: 2026-09-03T15:57:24.326125+00:00
- Forward parent setups registered: 12
- Resolved forward parent setups: 0
- Strategy parameters changed: no
- Canonical paper behavior changed: no
- SHORT setups disabled: no
- Live trading enabled: no
- Portfolio OS integration changed: no

## Decision

No cohort is eligible for promotion until it satisfies the explicit forward thresholds:

- EXPLORATORY: N >= 20
- PRELIMINARY_EDGE: N >= 50, expectancy > 0, PF > 1, and not dominated by one symbol
- FORWARD_SUPPORTED: N >= 100, expectancy > 0, PF > 1, and positive after removing the best symbol, best day, and top five winners

## Canonical management cohorts

| cohort | management_version | parent_setup_count | N | expectancy | median_R | profit_factor | win_rate | avg_MFE | avg_MAE | prob_plus_0_5R_before_minus_1R | prob_plus_1R_before_minus_1R | max_drawdown | top_symbol | top_symbol_count_share | promotion_status | robustness_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A_ALL_LONG | TM_V0_CURRENT | 6 | 0 | 0.0 | 0.0 | None | 0.0 | 0.0 | 0.0 | None | None | 0.0 | None | 0.0 | INSUFFICIENT_FORWARD_SAMPLE | NOT_TESTABLE_UNTIL_N_100 |
| B_ALL_SHORT | TM_V0_CURRENT | 6 | 0 | 0.0 | 0.0 | None | 0.0 | 0.0 | 0.0 | None | None | 0.0 | None | 0.0 | INSUFFICIENT_FORWARD_SAMPLE | NOT_TESTABLE_UNTIL_N_100 |
| C_LONG_1130_1300 | TM_V0_CURRENT | 6 | 0 | 0.0 | 0.0 | None | 0.0 | 0.0 | 0.0 | None | None | 0.0 | None | 0.0 | INSUFFICIENT_FORWARD_SAMPLE | NOT_TESTABLE_UNTIL_N_100 |
| G_LONG_GEX_NODE | TM_V0_CURRENT | 5 | 0 | 0.0 | 0.0 | None | 0.0 | 0.0 | 0.0 | None | None | 0.0 | None | 0.0 | INSUFFICIENT_FORWARD_SAMPLE | NOT_TESTABLE_UNTIL_N_100 |
| H_LONG_GAMMA_FLIP | TM_V0_CURRENT | 1 | 0 | 0.0 | 0.0 | None | 0.0 | 0.0 | 0.0 | None | None | 0.0 | None | 0.0 | INSUFFICIENT_FORWARD_SAMPLE | NOT_TESTABLE_UNTIL_N_100 |

## TM_V3 research management cohorts

| cohort | management_version | parent_setup_count | N | expectancy | median_R | profit_factor | win_rate | avg_MFE | avg_MAE | prob_plus_0_5R_before_minus_1R | prob_plus_1R_before_minus_1R | max_drawdown | top_symbol | top_symbol_count_share | promotion_status | robustness_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A_ALL_LONG | TM_V3_TP1_PLUS_RUNNER | 6 | 0 | 0.0 | 0.0 | None | 0.0 | 0.0 | 0.0 | None | None | 0.0 | None | 0.0 | INSUFFICIENT_FORWARD_SAMPLE | NOT_TESTABLE_UNTIL_N_100 |
| B_ALL_SHORT | TM_V3_TP1_PLUS_RUNNER | 6 | 0 | 0.0 | 0.0 | None | 0.0 | 0.0 | 0.0 | None | None | 0.0 | None | 0.0 | INSUFFICIENT_FORWARD_SAMPLE | NOT_TESTABLE_UNTIL_N_100 |
| C_LONG_1130_1300 | TM_V3_TP1_PLUS_RUNNER | 6 | 0 | 0.0 | 0.0 | None | 0.0 | 0.0 | 0.0 | None | None | 0.0 | None | 0.0 | INSUFFICIENT_FORWARD_SAMPLE | NOT_TESTABLE_UNTIL_N_100 |
| G_LONG_GEX_NODE | TM_V3_TP1_PLUS_RUNNER | 5 | 0 | 0.0 | 0.0 | None | 0.0 | 0.0 | 0.0 | None | None | 0.0 | None | 0.0 | INSUFFICIENT_FORWARD_SAMPLE | NOT_TESTABLE_UNTIL_N_100 |
| H_LONG_GAMMA_FLIP | TM_V3_TP1_PLUS_RUNNER | 1 | 0 | 0.0 | 0.0 | None | 0.0 | 0.0 | 0.0 | None | None | 0.0 | None | 0.0 | INSUFFICIENT_FORWARD_SAMPLE | NOT_TESTABLE_UNTIL_N_100 |

## SHORT failure diagnostic

| parent_setup_id | symbol | timestamp | SPY_direction | QQQ_direction | gamma_regime | distance_to_gamma_flip_R | time_of_day | market_alignment | price_first_reached_plus_0_5R | later_reversed_to_stop | canonical_R |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| setup_f8bdd82b3c7e4859a9ccaf12fe2e2b17 | SOXX | 2026-09-03T16:05:00Z | NEUTRAL | BULLISH | NEGATIVE_GAMMA | nan | 11:30-13:00 | UNKNOWN | None | False | None |
| setup_d44aae7f01134e5886fe5d2180b4167e | ARKK | 2026-09-03T16:05:00Z | NEUTRAL | BULLISH | NEGATIVE_GAMMA | 0.5305 | 11:30-13:00 | UNKNOWN | None | False | None |
| setup_b2f0102a866a4164878a1197b5d2a097 | SMR | 2026-09-03T16:05:00Z | NEUTRAL | BULLISH | POSITIVE_GAMMA | 0.1984 | 11:30-13:00 | UNKNOWN | None | False | None |
| setup_877a03bd77eb4373acc6f98b21471192 | CRWV | 2026-09-03T16:05:00Z | NEUTRAL | BULLISH | NEGATIVE_GAMMA | nan | 11:30-13:00 | UNKNOWN | None | False | None |
| setup_e301f1904b39494bab84fe8a9ec7871c | CLSK | 2026-09-03T16:00:00Z | NEUTRAL | BULLISH | POSITIVE_GAMMA | 7.6279 | 11:30-13:00 | UNKNOWN | None | False | None |
| setup_c7c6da50158d47c2abaf2cd1e91af4cd | SNOW | 2026-09-03T16:00:00Z | NEUTRAL | BULLISH | POSITIVE_GAMMA | 12.0636 | 11:30-13:00 | UNKNOWN | None | False | None |

## LONG edge validation sample

| parent_setup_id | symbol | timestamp | time_bucket | reclaimed_level_type | gamma_regime | score_bucket | in_1130_1300_long | in_gex_node_long | in_gamma_flip_long | canonical_R | TM_V3_R |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| setup_0d3354846b4f48d68a36220581e5d968 | COIN | 2026-09-03T16:00:00Z | 11:30-13:00 | GEX_NODE | POSITIVE_GAMMA | 75-79 | True | True | False | None | 0.0 |
| setup_3796e98fbf744e0ba7e5aa58137b613e | CRWD | 2026-09-03T16:00:00Z | 11:30-13:00 | GEX_NODE | NEGATIVE_GAMMA | 55-59 | True | True | False | None | 0.0 |
| setup_6ae8b01c0b9b44f78a2e31ba46650bc3 | HOOD | 2026-09-03T16:00:00Z | 11:30-13:00 | GEX_NODE | POSITIVE_GAMMA | 55-59 | True | True | False | None | 0.0 |
| setup_9a327a7400314565b4b4ee1196983d3a | MSTR | 2026-09-03T16:00:00Z | 11:30-13:00 | GEX_NODE | POSITIVE_GAMMA | 55-59 | True | True | False | None | 0.0 |
| setup_b1d103ce72e74127b2144cae8e5858c7 | BE | 2026-09-03T16:00:00Z | 11:30-13:00 | GEX_NODE | POSITIVE_GAMMA | 55-59 | True | True | False | None | 0.0 |
| setup_b8d783f4c4da41db85d8ac286e92c27d | SOFI | 2026-09-03T16:00:00Z | 11:30-13:00 | GAMMA_FLIP | NEGATIVE_GAMMA | 75-79 | True | False | True | None | 0.0 |

## Output artifacts

- `PHASE_2D6_FORWARD_EDGE_VALIDATION.md`
- `forward_edge_cohorts.csv`
- `short_failure_analysis.csv`
- `long_edge_validation.csv`
