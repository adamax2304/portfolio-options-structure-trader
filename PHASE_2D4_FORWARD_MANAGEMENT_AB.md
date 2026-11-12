# Phase 2D.4 Forward Management A/B

Generated: 2026-09-03T12:45:13.990379+00:00

Forward paired paper-management experiment. One natural setup event creates two research branches only:

- Branch A: TM_V0_CURRENT
- Branch B: TM_V3_TP1_PLUS_RUNNER

Canonical paper trades, entry logic, score weights, thresholds, GEX logic, macro guard, stop construction, provider gates, live-trading structure, and Portfolio OS isolation remain unchanged.

## Progress

- Paired parent setups: 66
- Paired completed or censored: 66 / 100
- Remaining to acceptance target: 34
- Open research branches: 0

## A/B comparison

| branch | version | N | expectancy | median R | profit factor | win rate | avg winner | avg loser | max drawdown | TP1 freq | runner contribution | BE freq |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A | TM_V0_CURRENT | 66 | 0.0804 | 0.0 | 1.3452 | 27.3% | 1.1417 | -0.7639 | 12.8785 | 19.7% | 12.9505 | 4.5% |
| B | TM_V3_TP1_PLUS_RUNNER | 66 | 0.0727 | 0.0 | 1.311 | 27.3% | 1.1127 | -0.7639 | 12.816 | 19.7% | 9.6869 | 4.5% |

## Decision rule

TM_V3_TP1_PLUS_RUNNER is not eligible for promotion until N >= 100 paired setups and Branch B keeps positive expectancy improvement, improves profit factor, does not materially worsen drawdown, and is not driven by one or two symbols.

Current promotion-eligible: False
