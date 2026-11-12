# Phase 4B.1 Full Edge Decomposition

Generated: 2026-09-05T13:21:05.028232+00:00

Research-only diagnostic. Canonical strategy behavior, paper gates, watchlist, macro guard, live-trading disabled state, and Portfolio OS isolation were not changed.

## Top questions

1. Raw options-level interactions show mean MFE of `1.9098` R before exits. This is directional excursion, not tradable edge by itself.
2. Direction classifier accuracy proxy: `0.4626`. Best direction proxy in this pass: `PRICE_ACTION_ONLY` at `0.505`.
3. Structure-confirmed canonical expectancy: `-0.201` R versus overall canonical `-0.1505` R.
4. Entry timing is classified from stored delay/distance fields; current artifacts are strongest for historical Phase 4A-H and limited for live DB records.
5. Losers reaching +0.5R/+0.7R/+1R before final loss: `0.3698` / `0.2859` / `0.1948`.
6. Median MFE: `0.3696` R. Median time-to-MFE: `80.0` minutes where available.
7. Canonical stop efficiency is weak/unknown, because post-stop continuation is not fully stored. Winner MAE percentiles are exported in `phase4b1_stop_efficiency.csv`.
8. Stop preservation thresholds are in `phase4b1_stop_efficiency.csv`; they are diagnostic thresholds, not recommendations.
9. Stop-then-recovery is only a candidate label until lower-timeframe/post-stop continuation is captured prospectively.
10. Target ambition is evaluated with the target-reach ladder in `phase4b1_target_efficiency.csv`.
11. Natural MFE distribution and horizons are exported in `phase4b1_raw_excursion.csv` and `phase4b1_holding_horizon.csv`.
12. Breakeven leakage is not fully measurable from current artifacts; the report marks post-BE path tracking unavailable.
13. TM_V0 expectancy `-0.1778` / PF `0.5713`; TM_V3 expectancy `-0.1472` / PF `0.6038`.
14. Management capture is exported in `phase4b1_management_capture.csv`.
15. Level roles with directional value are summarized in `phase4b1_level_role_analysis.csv`.
16. 15m-vs-5m structure comparison remains Phase 4A/4A-H context; this layer decomposes why branches win/lose.
17. Largest associated loss source: `BAD_STOP`.
18. Single largest avoidable-loss candidate is the largest loss-attribution bucket; it must become a prospective branch before any canonical change.

## Dataset reconciliation

- Master parent events: `8975`
- Counterfactual/research branches: `336065`
- Live setup rows read-only inspected: `872`
- Live paper trade rows read-only inspected: `861`
- Historical Phase 4A-H source: `8356` parent events
- Live natural paper source: `619` parent events
- Synthetic/test rows are excluded from the live-derived natural diagnostic set.
- Branches are not counted as independent empirical setup events.

## Canonical and control baseline

- Canonical/options branches: N `37924`, expectancy `-0.1505` R, PF `0.6036`, win rate `0.3876`, max DD `-5727.335` R.
- Matched/ordinary controls: N `41748`, expectancy `-0.1328` R, PF `0.6511`, win rate `0.4345`, max DD `-5584.1638` R.

## Edge funnel

| layer | N | unique_days | MFE | MAE | directional_success_0_5R | P_0_7R_before_minus_1R | P_1R_before_minus_1R | expectancy | PF |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| LAYER_0_ALL_VALID_OPTIONS_LEVEL_INTERACTIONS | 37924 | 386 | 1.69 | 2.0551 | 0.2867 | 0.1024 | 0.0845 | -0.1505 | 0.6036 |
| LAYER_1_STRONG_OPTIONS_LEVEL | 37262 | 386 | 1.7091 | 2.0879 | 0.2853 | 0.0999 | 0.0826 | -0.1532 | 0.5986 |
| LAYER_2_CORRECT_DIRECTION_CLASSIFICATION | 35447 | 386 | 1.7012 | 2.0787 | 0.2881 | 0.1027 | 0.0846 | -0.1571 | 0.5903 |
| LAYER_3_MARKET_STRUCTURE_CONFIRMATION | 18623 | 372 | 1.7718 | 2.2136 | 0.3321 | 0.1093 | 0.0906 | -0.201 | 0.5441 |
| LAYER_4_TIMEFRAME_CONFIRMATION_15M | 7578 | 384 | 1.1566 | 1.5741 | 0.1442 | 0.056 | 0.0462 | -0.1494 | 0.5485 |
| LAYER_5_ENTRY_TIMING_ON_TIME | 16932 | 386 | 1.5375 | 1.9083 | 0.2726 | 0.1041 | 0.0855 | -0.1442 | 0.6085 |
| LAYER_6_STOP_INVALIDATION_DIAGNOSTIC | 32037 | 386 | 1.4712 | 1.5761 | 0.2087 | 0.1136 | 0.0937 | 0.0056 | 1.021 |
| LAYER_7_TARGET_MANAGEMENT_DIAGNOSTIC | 37924 | 386 | 1.69 | 2.0551 | 0.2867 | 0.1024 | 0.0845 | -0.1505 | 0.6036 |

## Information contribution test

| component_set | N | unique_days | directional_hit_0_5R | P_1R_before_minus_1R | MFE_MAE_ratio | expectancy | PF |
| --- | --- | --- | --- | --- | --- | --- | --- |
| BASE_PRICE_INTERACTION_ONLY | 41748 | 384 | 0.4691 | 0.1376 | 2.3796 | -0.1328 | 0.6511 |
| PLUS_OPTIONS_LEVEL | 37924 | 386 | 0.2867 | 0.0845 | 2.2553 | -0.1505 | 0.6036 |
| PLUS_LEVEL_STRENGTH | 37262 | 386 | 0.2853 | 0.0826 | 2.2102 | -0.1532 | 0.5986 |
| PLUS_LEVEL_DIRECTION | 35447 | 386 | 0.2881 | 0.0846 | 2.1964 | -0.1571 | 0.5903 |
| PLUS_MARKET_STRUCTURE | 18623 | 372 | 0.3321 | 0.0906 | 2.0695 | -0.201 | 0.5441 |
| PLUS_MARKET_ALIGNMENT | 12065 | 338 | 0.3593 | 0.0947 | 2.0792 | -0.2153 | 0.5376 |
| PLUS_LEVEL_PERSISTENCE | 0 | 0 |  |  |  |  |  |

## Loss attribution

| primary_loss_reason | loss_reason_certainty | N | negative_R | avg_MFE | avg_MAE | share_of_negative_R |
| --- | --- | --- | --- | --- | --- | --- |
| BAD_STOP | ASSOCIATED | 35558 | -35555.5239 | 3.1241 | 4.8555 | 0.3837 |
| NO_LEVEL_EDGE | ASSOCIATED | 45875 | -30965.3355 | 0.0838 | 2.5326 | 0.3342 |
| UNKNOWN | UNKNOWN | 38701 | -15554.7675 | 0.2044 | 1.4488 | 0.1679 |
| STRUCTURE_MISREAD | ASSOCIATED | 7531 | -5390.962 | 2.5663 | 2.687 | 0.0582 |
| WRONG_DIRECTION | ASSOCIATED | 6552 | -4563.194 | 1.9615 | 2.8598 | 0.0492 |

Use `ATTRIBUTABLE` only for data invalidity. Other rows are association tags, not causal proof.

## Component scorecard

- OPTIONS_LEVEL_SELECTION: `FAIL` — N=37262; expectancy=-0.1532; base_expectancy=-0.1505.
- DIRECTION_CLASSIFICATION: `FAIL` — N=35447; expectancy=-0.1571; base_expectancy=-0.1505.
- MARKET_STRUCTURE: `FAIL` — N=18623; expectancy=-0.201; base_expectancy=-0.1505.
- ENTRY_TIMING: `WEAK` — N=16932; expectancy=-0.1442; base_expectancy=-0.1505.
- STOP_LOGIC: `WEAK` — Stop variants are diagnostic only; stopped-trade recovery requires lower-timeframe/post-stop tracking.
- TARGET_LOGIC: `WEAK` — MFE reach rates exceed realized capture in several loss/giveback buckets.
- BREAKEVEN_LOGIC: `UNKNOWN` — Current artifacts do not reliably store post-BE path continuation.
- MANAGEMENT: `WEAK` — Canonical diagnostic expectancy -0.1505.
- DATA_QUALITY: `PASS` — 59730 branches have usable diagnostic data-quality labels.

## Next prospective experiments, ranked

1. Direction/structure confirmation branch: freeze the Phase 4B.1 direction classifier plus deterministic 15m structure confirmation; require at least 100 parent events and 10+ independent trading days.
2. Stop/invalidation branch: if prospective stop-then-recovery remains high, test structure/zone invalidation stops as a separate research branch; fail if max drawdown worsens materially.
3. Target/capture branch: if raw MFE remains positive while capture stays weak, test fixed 0.7R/1R and runner variants separately for LONG and SHORT; fail if PF does not improve in forward holdout.

No canonical promotion is justified from this retrospective diagnostic alone.

## Output files

- `phase4b1_breakeven_analysis.csv`
- `phase4b1_counterfactual_rescue.csv`
- `phase4b1_direction_classifier.csv`
- `phase4b1_entry_analysis.csv`
- `phase4b1_giveback_analysis.csv`
- `phase4b1_holding_horizon.csv`
- `phase4b1_level_role_analysis.csv`
- `phase4b1_loss_attribution.csv`
- `phase4b1_management_capture.csv`
- `phase4b1_manual_audit_best_trades.csv`
- `phase4b1_manual_audit_large_giveback.csv`
- `phase4b1_manual_audit_stop_then_recovery.csv`
- `phase4b1_manual_audit_structure_misread.csv`
- `phase4b1_manual_audit_worst_trades.csv`
- `phase4b1_manual_audit_wrong_direction.csv`
- `phase4b1_options_level_validation_sample.csv`
- `phase4b1_raw_excursion.csv`
- `phase4b1_score_audit.csv`
- `phase4b1_stop_efficiency.csv`
- `phase4b1_stop_recovery.csv`
- `phase4b1_structure_analysis.csv`
- `phase4b1_structure_label_validation_sample.csv`
- `phase4b1_target_efficiency.csv`
- `phase4b1_winner_analysis.csv`
