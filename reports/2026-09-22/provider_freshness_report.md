# Provider Freshness Report - 2026-09-22

Generated: 2026-09-23T00:53:22.073295+00:00

This report measures free candle-data usability only. It does not change strategy logic, gates, weights, stops, targets, sizing, or lane rules.

## Summary

- Valid scans by candle provider: {}
- Average candle publication lag: 0 seconds
- Median/P95/max lag: 0 / 0 / 0 seconds
- Fallback success rate: 0
- Cross-provider conflicts: 0

## Symbol Reliability

| symbol | tier | valid_scans | stale_scans | primary_provider | fallback_success | avg_lag | p95_lag | reliability |
|---|---|---:|---:|---|---:|---:|---:|---:|
| - | - | 0 | 0 | - | 0 | 0 | 0 | 0 |

## Recommendation

Keep Yahoo as the bulk OHLCV source, Finnhub as quote freshness confirmation, and Alpha Vantage as a Tier 1 fallback only until a larger real-time sample proves a better free priority order.
