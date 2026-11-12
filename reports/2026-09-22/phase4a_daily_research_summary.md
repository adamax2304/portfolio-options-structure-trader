# Phase 4A Multi-Timeframe Intraday Options-Level Edge Report

Generated: 2026-09-23T00:54:22.385167+00:00

Activation cutoff: 2026-09-04T21:00:43.783454+00:00

This report is research-only. Canonical paper behavior, thresholds, score weights, stop/TP logic, provider gates, watchlist, live-execution restrictions, and Portfolio OS isolation were not changed.

## Main questions

1. Does 15m confirmation outperform 5m confirmation? `INSUFFICIENT_SAMPLE`
2. Do persistent/strengthening levels outperform raw/static levels? `INSUFFICIENT_SAMPLE`
3. Does Variant D outperform A/B/C? `INSUFFICIENT_SAMPLE`
4. Are LONG setups materially better than SHORT? `INSUFFICIENT_SAMPLE`
5. Are reclaim setups better than rejection? `INSUFFICIENT_SAMPLE`
6. Do breakout setups have a separate edge? `INSUFFICIENT_SAMPLE`
7. Which options level type performs best? `INSUFFICIENT_SAMPLE`
8. Does options structure outperform matched ordinary price levels? `INSUFFICIENT_SAMPLE`
9. What is the natural holding horizon? `Tracked in branch holding_horizon_results_R; insufficient resolved sample for a stable horizon.`
10. Are current stops too tight for higher-timeframe setups? `Research stop variants recorded; no canonical stop change.`
11. Which management variant best preserves entry edge? `INSUFFICIENT_SAMPLE`
12. Does any candidate survive multiple days and robustness tests? `INSUFFICIENT_DAYS`

## Progress

- Parent research events: 0
- Research branches: 0
- Resolved/censored branches: 0
- Active branches: 0
- Not-qualified branches: 0
- Unique trading days: 0
- Sample status: INSUFFICIENT_DAYS

## Primary variants A-G

| variant | N | days | expectancy | PF | win rate | status |
|---|---:|---:|---:|---:|---:|---|
| VARIANT_A_5M_BASELINE | 0 | 0 | 0.0 | None | 0.0% | INSUFFICIENT_DAYS |
| VARIANT_B_15M_CONFIRM_5M_ENTRY | 0 | 0 | 0.0 | None | 0.0% | INSUFFICIENT_DAYS |
| VARIANT_C_PERSISTENT_5M | 0 | 0 | 0.0 | None | 0.0% | INSUFFICIENT_DAYS |
| VARIANT_D_PERSISTENT_15M_5M | 0 | 0 | 0.0 | None | 0.0% | INSUFFICIENT_DAYS |
| VARIANT_E_30M_CONTEXT_15M_SETUP_5M_ENTRY | 0 | 0 | 0.0 | None | 0.0% | INSUFFICIENT_DAYS |
| VARIANT_F_15M_SETUP_1M_ENTRY | 0 | 0 | 0.0 | None | 0.0% | INSUFFICIENT_DAYS |
| VARIANT_G_5M_SETUP_1M_ENTRY | 0 | 0 | 0.0 | None | 0.0% | INSUFFICIENT_DAYS |

## Direction

| direction | N | days | expectancy | PF | win rate | status |
|---|---:|---:|---:|---:|---:|---|
| - | 0 | 0 | 0 | 0 | 0 | 0 |


## Structural family

| family | N | days | expectancy | PF | win rate | status |
|---|---:|---:|---:|---:|---:|---|
| - | 0 | 0 | 0 | 0 | 0 | 0 |


## Level type

| level type | N | days | expectancy | PF | win rate | status |
|---|---:|---:|---:|---:|---:|---|
| - | 0 | 0 | 0 | 0 | 0 | 0 |


## Matched controls

- Options-level branches: N=0, expectancy=0.0, PF=None
- Matched-control branches: N=0, expectancy=0.0, PF=None

## Files

- Events CSV: phase4a_intraday_options_edge_events.csv
- Branches CSV: phase4a_intraday_options_edge_branches.csv
