# Phase 2B — Real-data Production Paper validation

## Scope

Only `LEVEL_RECLAIM_LONG` and `LEVEL_RECLAIM_SHORT` are enabled. This phase collects data-quality and paper-observation evidence; it does not fit parameters or change production weights.

## Implemented provider boundaries

- AlgoX: real GEX map, flip, call/put walls, max pain, expected move, ATM IV, strike profile, 15-minute cache, source/ingestion timestamps, confidence, and raw payload reference. It is explicitly incomplete without OI and Greeks.
- GammaGrid v0.4+: read-only Postgres access to the freshest source-scoped `option_snapshots` chain. The adapter normalizes OI, IV, seven Greeks, GEX by strike, gamma flip, walls, max pain, OI nodes, expected move, field coverage, confidence, freshness, and missing fields. Legacy SQLite is a read-only compatibility boundary.
- Alpaca Market Data: historical 5-minute bars plus latest quote; only completed candles are normalized. The adapter contains no trading client or order endpoint.
- yfinance: real-data collection/Shadow fallback only. Its missing authoritative latency and bid/ask contract makes it ineligible for Production Paper.
- Unusual Whales and Quant Data remain optional adapters behind boundaries and are not required by either reclaim setup.

Every raw provider response is stored separately from its normalized model. Normalized bars, ticker state, options structure, observations, failures, and ablations retain provider, source timestamp, ingestion timestamp, freshness, confidence, and raw payload ID.

## Production Paper gate

A detected reclaim can enter Production Paper only when all of these are true:

- real, non-synthetic input;
- supported ticker;
- authoritative regular-session state;
- macro guard evaluated with an operator-approved calendar;
- complete normalized price and options fields;
- Production-approved price and structure adapters;
- candle and options freshness within configured thresholds;
- no provider-reported missing fields or conflicts;
- score and R:R gates pass.

Any detected setup that fails those gates remains Shadow Paper with stored reasons. Invalid normalized payloads and provider failures are rejected and journaled. No rule can promote synthetic data.

## Observation and reports

Use:

```powershell
options-trader observe --cycles 1 --interval-seconds 0
options-trader daily-report
```

The observation status API counts only `production_eligible=true` observations toward the 50-scan target. Repeated, warm-up, stale, incomplete, after-hours, or synthetic observations do not count. Trades are never forced to meet the 10–20 target.

Daily reports include scans by ticker, valid scans, Production/Shadow trades, rejected and stale/incomplete cases, macro blocks, scores, R/MFE/MAE, time to TP/exit, best/worst ticker, provider failures, and real-sample ablations. Ablation covers baseline, equal weight, no-flow, no-GEX, no-OI, no-macro-filter, price-only, options-only, stop buffers, TP logic, and breakeven variants without changing production parameters.

## Initial live observation — 2026-09-01 UTC

- 14 real observations stored across the 11-symbol watchlist (SPY was checked four times, including the dashboard control test).
- 0 Production-valid scans and 0 paper trades.
- The watchlist pass completed without a provider request failure.
- These observations do not count toward the 50-scan target: the market was closed, completed candles were stale, yfinance is a Shadow-only price source, AlgoX lacked required OI/Greeks, and the manual macro calendar is not Production-approved.
- The stricter behavior is intentional. No repeated or invalid observation was relabeled as valid to satisfy the quota.

Current report: `reports/2026-09-01/daily_report.md`.

## Activation prerequisites

1. Supply `ALPACA_API_KEY` and `ALPACA_API_SECRET`, enable Alpaca, and confirm the selected feed entitlement is appropriate for the paper-validation requirement.
2. Supply `GAMMAGRID_DATABASE_URL`, enable GammaGrid, and run its collector often enough to remain inside the configured freshness threshold.
3. Replace/verify the macro calendar for CPI, FOMC, and NFP, then explicitly mark it Production-approved.
4. Run observation during the US regular session until at least 50 genuinely valid scans and 10–20 naturally triggered paper trades exist.
5. Keep optimization locked until at least 100–200 real paper trades or another statistically meaningful sample is reached.

## Known limitations

- Synthetic data is useful only for deterministic QA.
- Production Paper requires external provider credentials/data stores and a verified macro calendar.
- Free and delayed sources can be stale, partial, or temporarily unavailable and remain Shadow/collection sources by default.
- No live trading or broker execution path exists.
- No Portfolio OS integration exists yet.
