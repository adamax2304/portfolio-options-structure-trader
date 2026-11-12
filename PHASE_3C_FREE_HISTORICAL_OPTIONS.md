# Phase 3C Free Historical EOD Option-Chain Reconstruction

Generated: 2026-09-04T17:43:02.155196+00:00

Status: **PARTIAL SUCCESS / PIPELINE READY FOR OPTION LEVELS; INTRADAY REPLAY BLOCKED**

No live daemon, canonical strategy, forward cohort, threshold, score-weight, stop/target, provider-gate, Portfolio OS, or live-execution behavior was changed.

## First-gate answer before any huge download

- Primary 104-symbol `SaidBahaDev/options-data` README is reachable, but its Cloudflare R2 SPY test URLs returned HTTP 404.
- `SaidBahaDev/options-dataset-hist` SPY/QQQ/IWM files are reachable via `media.githubusercontent.com` and are real Parquet.
- lambdaclass `data-v1` release files are reachable and remote-queryable.
- Actual pilot schema contains OI, IV, gamma, delta/theta/vega/rho, bid/ask, volume, expiration, strike, and type.
- Pilot option rows downloaded: 10,907,852.
- Pilot option date range: 2024-01-02 through 2025-12-15 depending symbol.
- Pilot raw download size: 374,394,210 bytes.
- D-1 → D GEX/OI level snapshots can be constructed for SPY/QQQ/IWM with explicit `lookahead_safe=true` where `source_chain_date < trade_date`.
- Full LEVEL_RECLAIM historical replay cannot honestly run yet because no validated free 2024-2025 5-minute OHLCV source for SPY/QQQ/IWM is available locally.

## Pilot option-chain validation

| symbol | rows | unique dates | date range | median contracts/day | median expirations/day | median strikes/day | OI/IV/gamma missing |
|---|---:|---:|---|---:|---:|---:|---|
| SPY | 4,612,996 | 491 | 2024-01-02 to 2025-12-12 | 9370 | 35 | 356 | 0.0% / 0.0% / 0.0% |
| QQQ | 3,959,760 | 491 | 2024-01-02 to 2025-12-15 | 8154 | 32 | 391 | 0.0% / 0.0% / 0.0% |
| IWM | 2,335,096 | 490 | 2024-01-02 to 2025-12-15 | 4742 | 32 | 176 | 0.0% / 0.0% / 0.0% |

## Historical level snapshots

| symbol | level rows | trading days | source chain dates | H2 rows | H3 rows | lookahead-safe rows |
|---|---:|---:|---:|---:|---:|---:|
| IWM | 1467 | 489 | 489 | 1467 | 0 | 1467 |
| QQQ | 1470 | 490 | 490 | 1470 | 0 | 1470 |
| SPY | 1467 | 489 | 489 | 1467 | 0 | 1467 |

Generated model variants:

- `GEX_MODEL_A_CALL_POSITIVE_PUT_NEGATIVE`
- `GEX_MODEL_B_CALL_NEGATIVE_PUT_POSITIVE`
- `GEX_MODEL_C_ABSOLUTE_GAMMA_CONCENTRATION`

## Intraday 5m blocker

The option side is usable for an honest D-1 EOD level reconstruction. The backtest side is blocked because LEVEL_RECLAIM requires completed 5-minute candles. Current findings:

- Stooq direct CSV probe returned browser verification HTML, not downloadable 5m CSV.
- `piekstra/market-data` is a real 5m Parquet store but currently has no committed SPY/QQQ/IWM files.
- yfinance/Yahoo 5m is not suitable for 2024-2025 history; the existing local Phase 3B yfinance cache is recent-window only and does not overlap the EOD options pilot.
- The bundled underlying files are daily OHLCV only.

## Replay / controls status

Replay and controls are intentionally written as blocked/empty artifacts. I did not fabricate intraday candles, did not use same-day EOD option chains for same-day intraday decisions, and did not run random/control tests without 5m bars.

## Acceptance classification

Phase 3C is currently **partial success**:

- Real free EOD option-chain/OI/IV/Greeks data has been verified and downloaded for SPY/QQQ/IWM.
- D-1 → D GEX/OI level snapshots have been generated with explicit model versions and lookahead flags.
- Provenance is not authoritative; reliability is `EXPLORATORY_RESEARCH`, not `SERIOUS_BACKTEST`.
- Full Level 2 historical replay is blocked pending a validated free 5-minute intraday OHLCV source for the same dates/symbols.
