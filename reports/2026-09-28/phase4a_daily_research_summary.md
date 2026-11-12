# Phase 4A Multi-Timeframe Intraday Options-Level Edge Report

Generated: 2026-09-28T20:25:45.480067+00:00

Activation cutoff: 2026-09-23T02:03:17.850727+00:00

This report is research-only. Canonical paper behavior, thresholds, score weights, stop/TP logic, provider gates, watchlist, live-execution restrictions, and Portfolio OS isolation were not changed.

## Main questions

1. Does 15m confirmation outperform 5m confirmation? `False`
2. Do persistent/strengthening levels outperform raw/static levels? `False`
3. Does Variant D outperform A/B/C? `False`
4. Are LONG setups materially better than SHORT? `False`
5. Are reclaim setups better than rejection? `False`
6. Do breakout setups have a separate edge? `False`
7. Which options level type performs best? `GEX_NODE`
8. Does options structure outperform matched ordinary price levels? `INSUFFICIENT_SAMPLE`
9. What is the natural holding horizon? `Tracked in branch holding_horizon_results_R; insufficient resolved sample for a stable horizon.`
10. Are current stops too tight for higher-timeframe setups? `Research stop variants recorded; no canonical stop change.`
11. Which management variant best preserves entry edge? `TM_V0_CURRENT`
12. Does any candidate survive multiple days and robustness tests? `INSUFFICIENT_DAYS`

## Progress

- Parent research events: 317
- Research branches: 2536
- Resolved/censored branches: 1238
- Active branches: 730
- Not-qualified branches: 88
- Unique trading days: 1
- Sample status: INSUFFICIENT_DAYS

## Primary variants A-G

| variant | N | days | expectancy | PF | win rate | status |
|---|---:|---:|---:|---:|---:|---|
| VARIANT_A_5M_BASELINE | 412 | 1 | -0.057 | 0.893 | 45.6% | INSUFFICIENT_DAYS |
| VARIANT_B_15M_CONFIRM_5M_ENTRY | 228 | 1 | -0.2019 | 0.7049 | 42.1% | INSUFFICIENT_DAYS |
| VARIANT_C_PERSISTENT_5M | 386 | 1 | -0.0819 | 0.8498 | 45.1% | INSUFFICIENT_DAYS |
| VARIANT_D_PERSISTENT_15M_5M | 212 | 1 | -0.2679 | 0.6256 | 40.6% | INSUFFICIENT_DAYS |
| VARIANT_E_30M_CONTEXT_15M_SETUP_5M_ENTRY | 0 | 0 | 0.0 | None | 0.0% | INSUFFICIENT_DAYS |
| VARIANT_F_15M_SETUP_1M_ENTRY | 0 | 0 | 0.0 | None | 0.0% | INSUFFICIENT_DAYS |
| VARIANT_G_5M_SETUP_1M_ENTRY | 0 | 0 | 0.0 | None | 0.0% | INSUFFICIENT_DAYS |

## Direction

| direction | N | days | expectancy | PF | win rate | status |
|---|---:|---:|---:|---:|---:|---|
| LONG | 732 | 1 | -0.1586 | 0.7407 | 44.0% | INSUFFICIENT_DAYS |
| SHORT | 506 | 1 | -0.0827 | 0.8558 | 43.9% | INSUFFICIENT_DAYS |

## Structural family

| family | N | days | expectancy | PF | win rate | status |
|---|---:|---:|---:|---:|---:|---|
| LEVEL_BREAKOUT | 286 | 1 | -0.1052 | 0.8136 | 40.6% | INSUFFICIENT_DAYS |
| RECLAIM | 426 | 1 | -0.1736 | 0.7016 | 43.7% | INSUFFICIENT_DAYS |
| REJECTION | 526 | 1 | -0.1026 | 0.8359 | 46.0% | INSUFFICIENT_DAYS |

## Level type

| level type | N | days | expectancy | PF | win rate | status |
|---|---:|---:|---:|---:|---:|---|
| CALL_WALL | 24 | 1 | -0.2406 | 0.5793 | 50.0% | INSUFFICIENT_DAYS |
| GAMMA_FLIP | 46 | 1 | -0.5563 | 0.2109 | 13.0% | INSUFFICIENT_DAYS |
| GEX_NODE | 966 | 1 | -0.0674 | 0.8801 | 44.9% | INSUFFICIENT_DAYS |
| PUT_WALL | 202 | 1 | -0.3045 | 0.587 | 45.5% | INSUFFICIENT_DAYS |

## Matched controls

- Options-level branches: N=1238, expectancy=-0.1276, PF=0.786
- Matched-control branches: N=0, expectancy=0.0, PF=None

## Files

- Events CSV: phase4a_intraday_options_edge_events.csv
- Branches CSV: phase4a_intraday_options_edge_branches.csv
