# Phase 4A Multi-Timeframe Intraday Options-Level Edge Report

Generated: 2026-09-24T20:15:34.481923+00:00

Activation cutoff: 2026-09-23T02:03:17.850727+00:00

This report is research-only. Canonical paper behavior, thresholds, score weights, stop/TP logic, provider gates, watchlist, live-execution restrictions, and Portfolio OS isolation were not changed.

## Main questions

1. Does 15m confirmation outperform 5m confirmation? `True`
2. Do persistent/strengthening levels outperform raw/static levels? `False`
3. Does Variant D outperform A/B/C? `False`
4. Are LONG setups materially better than SHORT? `True`
5. Are reclaim setups better than rejection? `False`
6. Do breakout setups have a separate edge? `False`
7. Which options level type performs best? `GAMMA_FLIP`
8. Does options structure outperform matched ordinary price levels? `INSUFFICIENT_SAMPLE`
9. What is the natural holding horizon? `Tracked in branch holding_horizon_results_R; insufficient resolved sample for a stable horizon.`
10. Are current stops too tight for higher-timeframe setups? `Research stop variants recorded; no canonical stop change.`
11. Which management variant best preserves entry edge? `TM_V3_TP1_PLUS_RUNNER`
12. Does any candidate survive multiple days and robustness tests? `INSUFFICIENT_DAYS`

## Progress

- Parent research events: 367
- Research branches: 2936
- Resolved/censored branches: 1346
- Active branches: 648
- Not-qualified branches: 384
- Unique trading days: 1
- Sample status: INSUFFICIENT_DAYS

## Primary variants A-G

| variant | N | days | expectancy | PF | win rate | status |
|---|---:|---:|---:|---:|---:|---|
| VARIANT_A_5M_BASELINE | 536 | 1 | 0.0586 | 1.124 | 50.0% | INSUFFICIENT_DAYS |
| VARIANT_B_15M_CONFIRM_5M_ENTRY | 264 | 1 | 0.1339 | 1.2863 | 56.1% | INSUFFICIENT_DAYS |
| VARIANT_C_PERSISTENT_5M | 366 | 1 | -0.0293 | 0.9404 | 47.5% | INSUFFICIENT_DAYS |
| VARIANT_D_PERSISTENT_15M_5M | 180 | 1 | -0.0443 | 0.9167 | 50.0% | INSUFFICIENT_DAYS |
| VARIANT_E_30M_CONTEXT_15M_SETUP_5M_ENTRY | 0 | 0 | 0.0 | None | 0.0% | INSUFFICIENT_DAYS |
| VARIANT_F_15M_SETUP_1M_ENTRY | 0 | 0 | 0.0 | None | 0.0% | INSUFFICIENT_DAYS |
| VARIANT_G_5M_SETUP_1M_ENTRY | 0 | 0 | 0.0 | None | 0.0% | INSUFFICIENT_DAYS |

## Direction

| direction | N | days | expectancy | PF | win rate | status |
|---|---:|---:|---:|---:|---:|---|
| LONG | 792 | 1 | 0.1892 | 1.4553 | 55.0% | INSUFFICIENT_DAYS |
| SHORT | 554 | 1 | -0.1837 | 0.6856 | 44.0% | INSUFFICIENT_DAYS |

## Structural family

| family | N | days | expectancy | PF | win rate | status |
|---|---:|---:|---:|---:|---:|---|
| LEVEL_BREAKOUT | 260 | 1 | -0.1678 | 0.7024 | 40.0% | INSUFFICIENT_DAYS |
| RECLAIM | 450 | 1 | 0.067 | 1.1474 | 55.6% | INSUFFICIENT_DAYS |
| REJECTION | 636 | 1 | 0.0967 | 1.2039 | 51.3% | INSUFFICIENT_DAYS |

## Level type

| level type | N | days | expectancy | PF | win rate | status |
|---|---:|---:|---:|---:|---:|---|
| CALL_WALL | 138 | 1 | -0.3897 | 0.3845 | 34.8% | INSUFFICIENT_DAYS |
| GAMMA_FLIP | 28 | 1 | 0.5304 | 2.2178 | 64.3% | INSUFFICIENT_DAYS |
| GEX_NODE | 1104 | 1 | 0.0961 | 1.211 | 52.5% | INSUFFICIENT_DAYS |
| PUT_WALL | 76 | 1 | -0.2508 | 0.6238 | 44.7% | INSUFFICIENT_DAYS |

## Matched controls

- Options-level branches: N=1346, expectancy=0.0357, PF=1.0736
- Matched-control branches: N=0, expectancy=0.0, PF=None

## Files

- Events CSV: phase4a_intraday_options_edge_events.csv
- Branches CSV: phase4a_intraday_options_edge_branches.csv
