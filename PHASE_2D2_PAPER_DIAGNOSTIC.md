# Phase 2D.2 Paper Lane + Expectancy Diagnostic

Generated: 2026-09-02T16:18:40.004337+00:00

## Current natural paper sample

- Synthetic/test paper records excluded: 0
- Unique Free Validation RTH scans: 132
- Tier 1 scans: 50
- Natural reclaim setup detections: 175
- Unique reclaim events: 171
- Duplicate reclaim detections: 4 (2.3%)
- Paper entries opened: 134
- Closed natural trades: 101
- Free Validation Paper trades: 1
- Shadow Paper trades: 174
- Production Paper trades: 0

## Lane diagnosis

The earlier pasted snapshot said all natural paper trades were Shadow. The live journal now contains one natural Free Validation Paper trade; all remaining natural trades are Shadow. This is mostly intended lane behavior, not retroactive trade promotion material: scan eligibility is less strict than trade eligibility. A scan can be Free-Validation-valid while the detected setup is still downgraded because trade-level requirements fail.

There is one prospective hygiene issue: repeated observation can re-detect the same completed-candle reclaim. The system now records a stable reclaim_event_key and suppresses future duplicate natural setup/trade creation for the same symbol, side, level, and completed candle.

| reason | setups | trades | % |
|---|---:|---:|---:|
| Directional flow or GEX/OI confirmation is insufficient | 123 | 123 | 70.3% |
| Options-structure data exceeds Free Validation freshness threshold | 110 | 110 | 62.9% |
| Critical market data is stale | 110 | 110 | 62.9% |
| Adjusted score 58 is below Free Validation threshold | 29 | 29 | 16.6% |
| Adjusted score 57 is below Free Validation threshold | 20 | 20 | 11.4% |
| Adjusted score 56 is below Free Validation threshold | 18 | 18 | 10.3% |
| Adjusted score 59 is below Free Validation threshold | 14 | 14 | 8.0% |
| Adjusted score 55 is below Free Validation threshold | 14 | 14 | 8.0% |
| Primary R:R 0.31 is below minimum | 5 | 5 | 2.9% |
| Primary R:R 0.22 is below minimum | 5 | 5 | 2.9% |
| Primary R:R 0.11 is below minimum | 5 | 5 | 2.9% |
| Stop distance exceeds configured ATR limit | 5 | 5 | 2.9% |

## Expectancy summary

- Total closed-trade R: -1.2858
- Average / expectancy R: -0.0127
- Median R: 0.1003
- Profit factor: 0.9342
- Winners / losers / breakevens: 62 / 24 / 15
- Average winner R: 0.3759
- Average loser R: -1.0396
- Average MFE / MAE: 0.7233 / 0.6079
- Max drawdown in R: -7.9129

## TP1 behavior

TP1 is implemented as a partial exit using the first configured target partial. The broker then moves the stop to breakeven when `targets.breakeven_default` is `after_TP1`. The current broker only checks TP1 in live paper simulation; TP2/TP3 are recorded in the plan but are not yet executed as independent scale-out events. This can make a trade count as a winner after a small TP1 partial while the remaining runner later exits at breakeven or loss, which explains how the win count can exceed the loss count while average R remains flat-to-negative.

## Score discrimination

| score bucket | N | win rate | average R | median R | profit factor | avg MFE | avg MAE |
|---|---:|---:|---:|---:|---:|---:|---:|
| 50-59 | 49 | 59.2% | -0.0345 | 0.1003 | 0.8471 | 0.6772 | 0.6508 |
| 60-69 | 22 | 63.6% | 0.0439 | 0.0824 | 1.1662 | 0.9049 | 0.5679 |
| 70-79 | 30 | 63.3% | -0.0187 | 0.1837 | 0.9169 | 0.6655 | 0.5674 |

## Open trade sanity

- Active natural paper trades: 42
- Total concurrent initial risk: 41.8487R-equivalent
- Positions by symbol: [('OKLO', 5), ('COIN', 3), ('VRT', 3), ('INTC', 2), ('DDOG', 2), ('AMZN', 2), ('META', 2), ('AAPL', 2), ('PLTR', 2), ('BE', 2), ('MU', 1), ('SNOW', 1), ('NET', 1), ('CRWD', 1), ('AVGO', 1), ('MSFT', 1), ('HOOD', 1), ('AMD', 1), ('XBI', 1), ('XLI', 1), ('XLK', 1), ('CEG', 1), ('ETN', 1), ('CLSK', 1), ('RIOT', 1), ('SOFI', 1), ('RKLB', 1)]
- Duplicate positions per identical setup event: 0

Shadow Paper currently does not enforce the same max-open/max-same-symbol limits that Free Validation and Production Paper enforce. That allows broad research capture, but it can create unrealistic portfolio exposure in Shadow statistics. I did not change this behavior because the phase asks for diagnosis, not strategy or risk-rule changes.

## Artifact files

- paper_lane_downgrades.csv
- setup_deduplication_report.csv
- paper_expectancy_analysis.csv
- mfe_mae_analysis.csv

## No parameter changes

Confluence weights, score thresholds, stop logic, target logic, breakeven logic, setup definitions, Production gates, no-live-trading structure, and Portfolio OS isolation were left unchanged.
