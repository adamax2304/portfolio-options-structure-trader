# Phase 4A Multi-Timeframe Intraday Options-Level Edge Report

Generated: 2026-10-05T20:17:22.607184+00:00

Activation cutoff: 2026-09-23T02:03:17.850727+00:00

This report is research-only. Canonical paper behavior, thresholds, score weights, stop/TP logic, provider gates, watchlist, live-execution restrictions, and Portfolio OS isolation were not changed.

## Main questions

1. Does 15m confirmation outperform 5m confirmation? `True`
2. Do persistent/strengthening levels outperform raw/static levels? `False`
3. Does Variant D outperform A/B/C? `True`
4. Are LONG setups materially better than SHORT? `True`
5. Are reclaim setups better than rejection? `False`
6. Do breakout setups have a separate edge? `False`
7. Which options level type performs best? `GEX_NODE`
8. Does options structure outperform matched ordinary price levels? `INSUFFICIENT_SAMPLE`
9. What is the natural holding horizon? `Tracked in branch holding_horizon_results_R; insufficient resolved sample for a stable horizon.`
10. Are current stops too tight for higher-timeframe setups? `Research stop variants recorded; no canonical stop change.`
11. Which management variant best preserves entry edge? `TM_V3_TP1_PLUS_RUNNER`
12. Does any candidate survive multiple days and robustness tests? `INSUFFICIENT_DAYS`

## Progress

- Parent research events: 464
- Research branches: 3712
- Resolved/censored branches: 1770
- Active branches: 796
- Not-qualified branches: 304
- Unique trading days: 1
- Sample status: INSUFFICIENT_DAYS

## Primary variants A-G

| variant | N | days | expectancy | PF | win rate | status |
|---|---:|---:|---:|---:|---:|---|
| VARIANT_A_5M_BASELINE | 660 | 1 | -0.1039 | 0.8011 | 43.9% | INSUFFICIENT_DAYS |
| VARIANT_B_15M_CONFIRM_5M_ENTRY | 302 | 1 | 0.0638 | 1.1464 | 51.7% | INSUFFICIENT_DAYS |
| VARIANT_C_PERSISTENT_5M | 544 | 1 | -0.1145 | 0.7812 | 44.1% | INSUFFICIENT_DAYS |
| VARIANT_D_PERSISTENT_15M_5M | 264 | 1 | 0.0706 | 1.1615 | 51.5% | INSUFFICIENT_DAYS |
| VARIANT_E_30M_CONTEXT_15M_SETUP_5M_ENTRY | 0 | 0 | 0.0 | None | 0.0% | INSUFFICIENT_DAYS |
| VARIANT_F_15M_SETUP_1M_ENTRY | 0 | 0 | 0.0 | None | 0.0% | INSUFFICIENT_DAYS |
| VARIANT_G_5M_SETUP_1M_ENTRY | 0 | 0 | 0.0 | None | 0.0% | INSUFFICIENT_DAYS |

## Direction

| direction | N | days | expectancy | PF | win rate | status |
|---|---:|---:|---:|---:|---:|---|
| LONG | 924 | 1 | 0.2991 | 1.8372 | 61.5% | INSUFFICIENT_DAYS |
| SHORT | 846 | 1 | -0.4365 | 0.3244 | 30.0% | INSUFFICIENT_DAYS |

## Structural family

| family | N | days | expectancy | PF | win rate | status |
|---|---:|---:|---:|---:|---:|---|
| LEVEL_BREAKOUT | 428 | 1 | -0.1672 | 0.7049 | 42.1% | INSUFFICIENT_DAYS |
| RECLAIM | 482 | 1 | -0.1768 | 0.6945 | 38.6% | INSUFFICIENT_DAYS |
| REJECTION | 860 | 1 | 0.0742 | 1.1796 | 53.0% | INSUFFICIENT_DAYS |

## Level type

| level type | N | days | expectancy | PF | win rate | status |
|---|---:|---:|---:|---:|---:|---|
| CALL_WALL | 200 | 1 | -0.1943 | 0.6939 | 38.0% | INSUFFICIENT_DAYS |
| GAMMA_FLIP | 142 | 1 | -0.1049 | 0.8059 | 42.2% | INSUFFICIENT_DAYS |
| GEX_NODE | 1366 | 1 | 0.0027 | 1.006 | 49.5% | INSUFFICIENT_DAYS |
| PUT_WALL | 62 | 1 | -0.6917 | 0.1457 | 16.1% | INSUFFICIENT_DAYS |

## Matched controls

- Options-level branches: N=1770, expectancy=-0.0525, PF=0.894
- Matched-control branches: N=0, expectancy=0.0, PF=None

## Files

- Events CSV: phase4a_intraday_options_edge_events.csv
- Branches CSV: phase4a_intraday_options_edge_branches.csv
