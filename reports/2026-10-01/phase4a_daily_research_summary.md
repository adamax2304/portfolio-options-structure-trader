# Phase 4A Multi-Timeframe Intraday Options-Level Edge Report

Generated: 2026-10-01T21:14:40.273098+00:00

Activation cutoff: 2026-09-23T02:03:17.850727+00:00

This report is research-only. Canonical paper behavior, thresholds, score weights, stop/TP logic, provider gates, watchlist, live-execution restrictions, and Portfolio OS isolation were not changed.

## Main questions

1. Does 15m confirmation outperform 5m confirmation? `False`
2. Do persistent/strengthening levels outperform raw/static levels? `False`
3. Does Variant D outperform A/B/C? `False`
4. Are LONG setups materially better than SHORT? `True`
5. Are reclaim setups better than rejection? `True`
6. Do breakout setups have a separate edge? `False`
7. Which options level type performs best? `GAMMA_FLIP`
8. Does options structure outperform matched ordinary price levels? `INSUFFICIENT_SAMPLE`
9. What is the natural holding horizon? `Tracked in branch holding_horizon_results_R; insufficient resolved sample for a stable horizon.`
10. Are current stops too tight for higher-timeframe setups? `Research stop variants recorded; no canonical stop change.`
11. Which management variant best preserves entry edge? `TM_V0_CURRENT`
12. Does any candidate survive multiple days and robustness tests? `INSUFFICIENT_DAYS`

## Progress

- Parent research events: 378
- Research branches: 3024
- Resolved/censored branches: 1300
- Active branches: 676
- Not-qualified branches: 208
- Unique trading days: 1
- Sample status: INSUFFICIENT_DAYS

## Primary variants A-G

| variant | N | days | expectancy | PF | win rate | status |
|---|---:|---:|---:|---:|---:|---|
| VARIANT_A_5M_BASELINE | 512 | 1 | -0.1709 | 0.6822 | 38.3% | INSUFFICIENT_DAYS |
| VARIANT_B_15M_CONFIRM_5M_ENTRY | 182 | 1 | -0.2543 | 0.5677 | 38.5% | INSUFFICIENT_DAYS |
| VARIANT_C_PERSISTENT_5M | 442 | 1 | -0.202 | 0.6342 | 36.6% | INSUFFICIENT_DAYS |
| VARIANT_D_PERSISTENT_15M_5M | 164 | 1 | -0.3653 | 0.4318 | 32.9% | INSUFFICIENT_DAYS |
| VARIANT_E_30M_CONTEXT_15M_SETUP_5M_ENTRY | 0 | 0 | 0.0 | None | 0.0% | INSUFFICIENT_DAYS |
| VARIANT_F_15M_SETUP_1M_ENTRY | 0 | 0 | 0.0 | None | 0.0% | INSUFFICIENT_DAYS |
| VARIANT_G_5M_SETUP_1M_ENTRY | 0 | 0 | 0.0 | None | 0.0% | INSUFFICIENT_DAYS |

## Direction

| direction | N | days | expectancy | PF | win rate | status |
|---|---:|---:|---:|---:|---:|---|
| LONG | 588 | 1 | 0.0092 | 1.0202 | 42.9% | INSUFFICIENT_DAYS |
| SHORT | 712 | 1 | -0.405 | 0.3789 | 32.3% | INSUFFICIENT_DAYS |

## Structural family

| family | N | days | expectancy | PF | win rate | status |
|---|---:|---:|---:|---:|---:|---|
| LEVEL_BREAKOUT | 228 | 1 | -0.235 | 0.5749 | 33.3% | INSUFFICIENT_DAYS |
| RECLAIM | 442 | 1 | -0.1691 | 0.6619 | 37.6% | INSUFFICIENT_DAYS |
| REJECTION | 630 | 1 | -0.2455 | 0.5981 | 38.1% | INSUFFICIENT_DAYS |

## Level type

| level type | N | days | expectancy | PF | win rate | status |
|---|---:|---:|---:|---:|---:|---|
| CALL_WALL | 52 | 1 | -0.2928 | 0.551 | 30.8% | INSUFFICIENT_DAYS |
| GAMMA_FLIP | 48 | 1 | 0.0322 | 1.0911 | 33.3% | INSUFFICIENT_DAYS |
| GEX_NODE | 1054 | 1 | -0.2146 | 0.618 | 38.1% | INSUFFICIENT_DAYS |
| PUT_WALL | 146 | 1 | -0.2952 | 0.5157 | 32.9% | INSUFFICIENT_DAYS |

## Matched controls

- Options-level branches: N=1300, expectancy=-0.2177, PF=0.6134
- Matched-control branches: N=0, expectancy=0.0, PF=None

## Files

- Events CSV: phase4a_intraday_options_edge_events.csv
- Branches CSV: phase4a_intraday_options_edge_branches.csv
