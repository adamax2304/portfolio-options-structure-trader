# Phase 4A Multi-Timeframe Intraday Options-Level Edge Report

Generated: 2026-09-25T20:15:31.135912+00:00

Activation cutoff: 2026-09-23T02:03:17.850727+00:00

This report is research-only. Canonical paper behavior, thresholds, score weights, stop/TP logic, provider gates, watchlist, live-execution restrictions, and Portfolio OS isolation were not changed.

## Main questions

1. Does 15m confirmation outperform 5m confirmation? `False`
2. Do persistent/strengthening levels outperform raw/static levels? `False`
3. Does Variant D outperform A/B/C? `False`
4. Are LONG setups materially better than SHORT? `True`
5. Are reclaim setups better than rejection? `False`
6. Do breakout setups have a separate edge? `False`
7. Which options level type performs best? `PUT_WALL`
8. Does options structure outperform matched ordinary price levels? `INSUFFICIENT_SAMPLE`
9. What is the natural holding horizon? `Tracked in branch holding_horizon_results_R; insufficient resolved sample for a stable horizon.`
10. Are current stops too tight for higher-timeframe setups? `Research stop variants recorded; no canonical stop change.`
11. Which management variant best preserves entry edge? `TM_V3_TP1_PLUS_RUNNER`
12. Does any candidate survive multiple days and robustness tests? `INSUFFICIENT_DAYS`

## Progress

- Parent research events: 434
- Research branches: 3472
- Resolved/censored branches: 1334
- Active branches: 1104
- Not-qualified branches: 284
- Unique trading days: 1
- Sample status: INSUFFICIENT_DAYS

## Primary variants A-G

| variant | N | days | expectancy | PF | win rate | status |
|---|---:|---:|---:|---:|---:|---|
| VARIANT_A_5M_BASELINE | 508 | 1 | -0.1045 | 0.79 | 43.3% | INSUFFICIENT_DAYS |
| VARIANT_B_15M_CONFIRM_5M_ENTRY | 212 | 1 | -0.1848 | 0.6599 | 40.6% | INSUFFICIENT_DAYS |
| VARIANT_C_PERSISTENT_5M | 430 | 1 | -0.1298 | 0.7519 | 41.9% | INSUFFICIENT_DAYS |
| VARIANT_D_PERSISTENT_15M_5M | 184 | 1 | -0.16 | 0.6922 | 40.2% | INSUFFICIENT_DAYS |
| VARIANT_E_30M_CONTEXT_15M_SETUP_5M_ENTRY | 0 | 0 | 0.0 | None | 0.0% | INSUFFICIENT_DAYS |
| VARIANT_F_15M_SETUP_1M_ENTRY | 0 | 0 | 0.0 | None | 0.0% | INSUFFICIENT_DAYS |
| VARIANT_G_5M_SETUP_1M_ENTRY | 0 | 0 | 0.0 | None | 0.0% | INSUFFICIENT_DAYS |

## Direction

| direction | N | days | expectancy | PF | win rate | status |
|---|---:|---:|---:|---:|---:|---|
| LONG | 612 | 1 | -0.0812 | 0.8353 | 43.1% | INSUFFICIENT_DAYS |
| SHORT | 722 | 1 | -0.1771 | 0.6697 | 41.0% | INSUFFICIENT_DAYS |

## Structural family

| family | N | days | expectancy | PF | win rate | status |
|---|---:|---:|---:|---:|---:|---|
| LEVEL_BREAKOUT | 228 | 1 | -0.3328 | 0.4659 | 30.7% | INSUFFICIENT_DAYS |
| RECLAIM | 444 | 1 | -0.3224 | 0.4546 | 34.2% | INSUFFICIENT_DAYS |
| REJECTION | 662 | 1 | 0.0626 | 1.1458 | 51.1% | INSUFFICIENT_DAYS |

## Level type

| level type | N | days | expectancy | PF | win rate | status |
|---|---:|---:|---:|---:|---:|---|
| CALL_WALL | 228 | 1 | -0.2279 | 0.5789 | 35.1% | INSUFFICIENT_DAYS |
| GAMMA_FLIP | 132 | 1 | -0.2531 | 0.5593 | 37.9% | INSUFFICIENT_DAYS |
| GEX_NODE | 844 | 1 | -0.1182 | 0.7728 | 43.4% | INSUFFICIENT_DAYS |
| PUT_WALL | 130 | 1 | 0.0585 | 1.1505 | 49.2% | INSUFFICIENT_DAYS |

## Matched controls

- Options-level branches: N=1334, expectancy=-0.1331, PF=0.7422
- Matched-control branches: N=0, expectancy=0.0, PF=None

## Files

- Events CSV: phase4a_intraday_options_edge_events.csv
- Branches CSV: phase4a_intraday_options_edge_branches.csv
