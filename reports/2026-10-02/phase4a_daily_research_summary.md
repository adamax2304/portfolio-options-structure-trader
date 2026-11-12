# Phase 4A Multi-Timeframe Intraday Options-Level Edge Report

Generated: 2026-10-02T20:17:25.441108+00:00

Activation cutoff: 2026-09-23T02:03:17.850727+00:00

This report is research-only. Canonical paper behavior, thresholds, score weights, stop/TP logic, provider gates, watchlist, live-execution restrictions, and Portfolio OS isolation were not changed.

## Main questions

1. Does 15m confirmation outperform 5m confirmation? `False`
2. Do persistent/strengthening levels outperform raw/static levels? `False`
3. Does Variant D outperform A/B/C? `False`
4. Are LONG setups materially better than SHORT? `False`
5. Are reclaim setups better than rejection? `True`
6. Do breakout setups have a separate edge? `False`
7. Which options level type performs best? `PUT_WALL`
8. Does options structure outperform matched ordinary price levels? `INSUFFICIENT_SAMPLE`
9. What is the natural holding horizon? `Tracked in branch holding_horizon_results_R; insufficient resolved sample for a stable horizon.`
10. Are current stops too tight for higher-timeframe setups? `Research stop variants recorded; no canonical stop change.`
11. Which management variant best preserves entry edge? `TM_V3_TP1_PLUS_RUNNER`
12. Does any candidate survive multiple days and robustness tests? `INSUFFICIENT_DAYS`

## Progress

- Parent research events: 674
- Research branches: 5392
- Resolved/censored branches: 2622
- Active branches: 1130
- Not-qualified branches: 448
- Unique trading days: 1
- Sample status: INSUFFICIENT_DAYS

## Primary variants A-G

| variant | N | days | expectancy | PF | win rate | status |
|---|---:|---:|---:|---:|---:|---|
| VARIANT_A_5M_BASELINE | 946 | 1 | -0.1427 | 0.7359 | 43.5% | INSUFFICIENT_DAYS |
| VARIANT_B_15M_CONFIRM_5M_ENTRY | 458 | 1 | -0.2208 | 0.6346 | 42.4% | INSUFFICIENT_DAYS |
| VARIANT_C_PERSISTENT_5M | 824 | 1 | -0.1671 | 0.6992 | 43.0% | INSUFFICIENT_DAYS |
| VARIANT_D_PERSISTENT_15M_5M | 394 | 1 | -0.2397 | 0.6111 | 42.1% | INSUFFICIENT_DAYS |
| VARIANT_E_30M_CONTEXT_15M_SETUP_5M_ENTRY | 0 | 0 | 0.0 | None | 0.0% | INSUFFICIENT_DAYS |
| VARIANT_F_15M_SETUP_1M_ENTRY | 0 | 0 | 0.0 | None | 0.0% | INSUFFICIENT_DAYS |
| VARIANT_G_5M_SETUP_1M_ENTRY | 0 | 0 | 0.0 | None | 0.0% | INSUFFICIENT_DAYS |

## Direction

| direction | N | days | expectancy | PF | win rate | status |
|---|---:|---:|---:|---:|---:|---|
| LONG | 1248 | 1 | -0.4854 | 0.3085 | 31.1% | INSUFFICIENT_DAYS |
| SHORT | 1374 | 1 | 0.1001 | 1.2246 | 53.7% | INSUFFICIENT_DAYS |

## Structural family

| family | N | days | expectancy | PF | win rate | status |
|---|---:|---:|---:|---:|---:|---|
| LEVEL_BREAKOUT | 498 | 1 | -0.1522 | 0.7314 | 41.4% | INSUFFICIENT_DAYS |
| RECLAIM | 830 | 1 | -0.1738 | 0.695 | 44.3% | INSUFFICIENT_DAYS |
| REJECTION | 1294 | 1 | -0.1918 | 0.6616 | 42.7% | INSUFFICIENT_DAYS |

## Level type

| level type | N | days | expectancy | PF | win rate | status |
|---|---:|---:|---:|---:|---:|---|
| CALL_WALL | 446 | 1 | -0.2707 | 0.5507 | 36.8% | INSUFFICIENT_DAYS |
| GAMMA_FLIP | 312 | 1 | -0.3229 | 0.496 | 34.0% | INSUFFICIENT_DAYS |
| GEX_NODE | 1688 | 1 | -0.179 | 0.6854 | 44.1% | INSUFFICIENT_DAYS |
| PUT_WALL | 176 | 1 | 0.3147 | 1.9338 | 63.6% | INSUFFICIENT_DAYS |

## Matched controls

- Options-level branches: N=2622, expectancy=-0.1786, PF=0.6854
- Matched-control branches: N=0, expectancy=0.0, PF=None

## Files

- Events CSV: phase4a_intraday_options_edge_events.csv
- Branches CSV: phase4a_intraday_options_edge_branches.csv
