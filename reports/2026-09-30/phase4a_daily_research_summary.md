# Phase 4A Multi-Timeframe Intraday Options-Level Edge Report

Generated: 2026-09-30T20:16:21.293376+00:00

Activation cutoff: 2026-09-23T02:03:17.850727+00:00

This report is research-only. Canonical paper behavior, thresholds, score weights, stop/TP logic, provider gates, watchlist, live-execution restrictions, and Portfolio OS isolation were not changed.

## Main questions

1. Does 15m confirmation outperform 5m confirmation? `False`
2. Do persistent/strengthening levels outperform raw/static levels? `True`
3. Does Variant D outperform A/B/C? `False`
4. Are LONG setups materially better than SHORT? `False`
5. Are reclaim setups better than rejection? `False`
6. Do breakout setups have a separate edge? `False`
7. Which options level type performs best? `CALL_WALL`
8. Does options structure outperform matched ordinary price levels? `INSUFFICIENT_SAMPLE`
9. What is the natural holding horizon? `Tracked in branch holding_horizon_results_R; insufficient resolved sample for a stable horizon.`
10. Are current stops too tight for higher-timeframe setups? `Research stop variants recorded; no canonical stop change.`
11. Which management variant best preserves entry edge? `TM_V3_TP1_PLUS_RUNNER`
12. Does any candidate survive multiple days and robustness tests? `INSUFFICIENT_DAYS`

## Progress

- Parent research events: 381
- Research branches: 3048
- Resolved/censored branches: 1578
- Active branches: 484
- Not-qualified branches: 192
- Unique trading days: 1
- Sample status: INSUFFICIENT_DAYS

## Primary variants A-G

| variant | N | days | expectancy | PF | win rate | status |
|---|---:|---:|---:|---:|---:|---|
| VARIANT_A_5M_BASELINE | 582 | 1 | -0.1813 | 0.6877 | 41.6% | INSUFFICIENT_DAYS |
| VARIANT_B_15M_CONFIRM_5M_ENTRY | 256 | 1 | -0.2866 | 0.5502 | 38.3% | INSUFFICIENT_DAYS |
| VARIANT_C_PERSISTENT_5M | 514 | 1 | -0.1787 | 0.693 | 41.2% | INSUFFICIENT_DAYS |
| VARIANT_D_PERSISTENT_15M_5M | 226 | 1 | -0.2745 | 0.5655 | 38.9% | INSUFFICIENT_DAYS |
| VARIANT_E_30M_CONTEXT_15M_SETUP_5M_ENTRY | 0 | 0 | 0.0 | None | 0.0% | INSUFFICIENT_DAYS |
| VARIANT_F_15M_SETUP_1M_ENTRY | 0 | 0 | 0.0 | None | 0.0% | INSUFFICIENT_DAYS |
| VARIANT_G_5M_SETUP_1M_ENTRY | 0 | 0 | 0.0 | None | 0.0% | INSUFFICIENT_DAYS |

## Direction

| direction | N | days | expectancy | PF | win rate | status |
|---|---:|---:|---:|---:|---:|---|
| LONG | 890 | 1 | -0.4747 | 0.336 | 29.2% | INSUFFICIENT_DAYS |
| SHORT | 688 | 1 | 0.1304 | 1.2927 | 55.2% | INSUFFICIENT_DAYS |

## Structural family

| family | N | days | expectancy | PF | win rate | status |
|---|---:|---:|---:|---:|---:|---|
| LEVEL_BREAKOUT | 316 | 1 | -0.0982 | 0.8234 | 43.7% | INSUFFICIENT_DAYS |
| RECLAIM | 420 | 1 | -0.3385 | 0.5248 | 38.6% | INSUFFICIENT_DAYS |
| REJECTION | 842 | 1 | -0.1895 | 0.6592 | 40.4% | INSUFFICIENT_DAYS |

## Level type

| level type | N | days | expectancy | PF | win rate | status |
|---|---:|---:|---:|---:|---:|---|
| CALL_WALL | 92 | 1 | 0.2995 | 1.6535 | 60.9% | INSUFFICIENT_DAYS |
| GAMMA_FLIP | 50 | 1 | -0.618 | 0.3091 | 32.0% | INSUFFICIENT_DAYS |
| GEX_NODE | 1356 | 1 | -0.2553 | 0.5817 | 39.2% | INSUFFICIENT_DAYS |
| PUT_WALL | 80 | 1 | 0.2094 | 1.5883 | 45.0% | INSUFFICIENT_DAYS |

## Matched controls

- Options-level branches: N=1578, expectancy=-0.2109, PF=0.6471
- Matched-control branches: N=0, expectancy=0.0, PF=None

## Files

- Events CSV: phase4a_intraday_options_edge_events.csv
- Branches CSV: phase4a_intraday_options_edge_branches.csv
