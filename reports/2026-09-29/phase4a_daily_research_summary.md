# Phase 4A Multi-Timeframe Intraday Options-Level Edge Report

Generated: 2026-09-29T20:16:16.104234+00:00

Activation cutoff: 2026-09-23T02:03:17.850727+00:00

This report is research-only. Canonical paper behavior, thresholds, score weights, stop/TP logic, provider gates, watchlist, live-execution restrictions, and Portfolio OS isolation were not changed.

## Main questions

1. Does 15m confirmation outperform 5m confirmation? `False`
2. Do persistent/strengthening levels outperform raw/static levels? `False`
3. Does Variant D outperform A/B/C? `False`
4. Are LONG setups materially better than SHORT? `False`
5. Are reclaim setups better than rejection? `True`
6. Do breakout setups have a separate edge? `False`
7. Which options level type performs best? `GAMMA_FLIP`
8. Does options structure outperform matched ordinary price levels? `INSUFFICIENT_SAMPLE`
9. What is the natural holding horizon? `Tracked in branch holding_horizon_results_R; insufficient resolved sample for a stable horizon.`
10. Are current stops too tight for higher-timeframe setups? `Research stop variants recorded; no canonical stop change.`
11. Which management variant best preserves entry edge? `TM_V0_CURRENT`
12. Does any candidate survive multiple days and robustness tests? `INSUFFICIENT_DAYS`

## Progress

- Parent research events: 442
- Research branches: 3536
- Resolved/censored branches: 2166
- Active branches: 398
- Not-qualified branches: 184
- Unique trading days: 1
- Sample status: INSUFFICIENT_DAYS

## Primary variants A-G

| variant | N | days | expectancy | PF | win rate | status |
|---|---:|---:|---:|---:|---:|---|
| VARIANT_A_5M_BASELINE | 754 | 1 | -0.0209 | 0.9562 | 48.0% | INSUFFICIENT_DAYS |
| VARIANT_B_15M_CONFIRM_5M_ENTRY | 394 | 1 | -0.0458 | 0.9105 | 48.7% | INSUFFICIENT_DAYS |
| VARIANT_C_PERSISTENT_5M | 666 | 1 | -0.0248 | 0.9485 | 48.0% | INSUFFICIENT_DAYS |
| VARIANT_D_PERSISTENT_15M_5M | 352 | 1 | -0.0834 | 0.8436 | 47.2% | INSUFFICIENT_DAYS |
| VARIANT_E_30M_CONTEXT_15M_SETUP_5M_ENTRY | 0 | 0 | 0.0 | None | 0.0% | INSUFFICIENT_DAYS |
| VARIANT_F_15M_SETUP_1M_ENTRY | 0 | 0 | 0.0 | None | 0.0% | INSUFFICIENT_DAYS |
| VARIANT_G_5M_SETUP_1M_ENTRY | 0 | 0 | 0.0 | None | 0.0% | INSUFFICIENT_DAYS |

## Direction

| direction | N | days | expectancy | PF | win rate | status |
|---|---:|---:|---:|---:|---:|---|
| LONG | 1096 | 1 | -0.1969 | 0.6685 | 41.2% | INSUFFICIENT_DAYS |
| SHORT | 1070 | 1 | 0.1272 | 1.3246 | 54.9% | INSUFFICIENT_DAYS |

## Structural family

| family | N | days | expectancy | PF | win rate | status |
|---|---:|---:|---:|---:|---:|---|
| LEVEL_BREAKOUT | 466 | 1 | -0.3475 | 0.4464 | 36.9% | INSUFFICIENT_DAYS |
| RECLAIM | 668 | 1 | 0.2024 | 1.5308 | 61.7% | INSUFFICIENT_DAYS |
| REJECTION | 1032 | 1 | -0.0514 | 0.8987 | 44.2% | INSUFFICIENT_DAYS |

## Level type

| level type | N | days | expectancy | PF | win rate | status |
|---|---:|---:|---:|---:|---:|---|
| CALL_WALL | 174 | 1 | -0.1181 | 0.7524 | 39.1% | INSUFFICIENT_DAYS |
| GAMMA_FLIP | 154 | 1 | 0.0964 | 1.2614 | 57.1% | INSUFFICIENT_DAYS |
| GEX_NODE | 1738 | 1 | -0.0428 | 0.9155 | 48.1% | INSUFFICIENT_DAYS |
| PUT_WALL | 100 | 1 | 0.0048 | 1.0097 | 48.0% | INSUFFICIENT_DAYS |

## Matched controls

- Options-level branches: N=2166, expectancy=-0.0368, PF=0.9255
- Matched-control branches: N=0, expectancy=0.0, PF=None

## Files

- Events CSV: phase4a_intraday_options_edge_events.csv
- Branches CSV: phase4a_intraday_options_edge_branches.csv
