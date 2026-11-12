# Options Structure Trader

A standalone, deterministic options-structure research and paper-trading service. It builds level maps, detects 5-minute `LEVEL_RECLAIM_LONG` and `LEVEL_RECLAIM_SHORT` events, scores confluence, constructs structural underlying trades, and routes them to three isolated lanes: Shadow, Free Validation Paper, or Production Paper.

It never places a live order. No broker order API exists in this codebase.

## Run

From this folder:

```powershell
python -m pip install -e .
options-trader init
options-trader serve
options-trader daemon
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765). The dashboard starts with synthetic deterministic fixtures so every feature can be inspected without credentials. Fixture inputs are always blocked from Production Paper.

Useful commands:

```powershell
options-trader scan --tickers SPY NVDA OKLO
options-trader scan --tickers SPY --open-paper
options-trader scan --tickers SPY --demo
options-trader observe --mode free-validation --rth-only --symbols SPY,QQQ,IWM,NVDA,TSLA,PLTR,OKLO,AMD,HOOD --interval 5m --target-scans 50
options-trader phase2c-report
options-trader phase2d-report
options-trader daily-report
options-trader report
options-trader export
pytest
```

`scan` uses real providers by default; `--demo` is the explicit synthetic path and can only create Shadow Paper trades. The Phase 2C observer counts each ticker/completed-candle pair once and does not call providers outside RTH when `--rth-only` is set. Production Paper remains blocked unless every strict eligibility field is satisfied.

`daemon` is the Phase 2D always-on scheduler. It uses the XNYS exchange calendar, sleeps on weekends/holidays and outside RTH, honors early closes, rotates the configured watchlist tiers, applies provider budgets and symbol cooldowns, and automatically creates the post-close daily report. Windows login autostart is documented in [docs/AUTOSTART_WINDOWS.md](docs/AUTOSTART_WINDOWS.md).

No broker onboarding or paid feed is required for Free Validation. Fresh yfinance/Yahoo candles plus fresh AlgoX structure can qualify with limited-data labels and confidence penalties. Alpha Vantage and Finnhub keys, Alpaca IEX, GammaGrid, Unusual Whales, and Quant Data are optional. The current manual macro calendar defaults to unapproved until the operator verifies its required coverage.

## Safety and isolation

- Own config, migration, SQLite DB, journal, broker, API, dashboard, macro calendar, reports, and exports.
- No imports from or writes to Portfolio OS.
- Shadow, Free Validation, and Production performance are never mixed.
- Source timestamps are separate from ingestion timestamps.
- Replays reject levels first known after interaction.
- Macro blocks prevent Production while retaining Shadow research.
- Same-bar stop/target ambiguity resolves pessimistically.
- Live automatic execution is absent and reported as disabled by `/health`.

## API

Interactive documentation is at `/docs`. Scheduler surfaces include `/scheduler/status`, `/watchlist/status`, and `/reports/phase-2d` alongside the Phase 2C observation routes.

## Phase 2D scheduler rules

- The default 52-symbol watchlist lives in `config/watchlist.yaml`; tiers scan every 5, 10, or 15 minutes.
- A 10-minute opening warm-up and five-minute closing buffer are enforced against the actual exchange schedule.
- Disabled, cooling-down, macro-blocked, low-liquidity, stale, and unavailable symbols are labeled separately.
- Duplicate provider work is cached for 240 seconds and free providers have rolling request budgets.
- Each post-close report contains Markdown, JSON, trades CSV, scans CSV, and ablation summary CSV.
- Phase 2D empirical acceptance requires 500 unique Free Validation scans, 50 Tier 1 scans, and at least 20 symbols with valid scans.

## Phase 2C evidence rules

- A scan counts toward the 50-scan target only when it is Free-Validation-eligible and represents a unique ticker/completed-candle pair during RTH. Repeated, stale, after-hours, warm-up, or synthetic snapshots do not count.
- Paper trades are never forced to satisfy a quota. Only naturally detected `LEVEL_RECLAIM_LONG` and `LEVEL_RECLAIM_SHORT` setups count.
- Fresh AlgoX structure can support Free Validation even when OI and Greeks are unavailable; those fields stay null and lower confidence. AlgoX alone remains incomplete for Production.
- Ablation rows are observational. The system does not promote weights or variants, and the dashboard reports the optimization lock until the configured sample threshold is reached.

## Known limitations

- Synthetic data is deterministic QA material only and cannot enter Free Validation or Production Paper.
- Production Paper requires configured provider credentials/data stores plus an operator-approved macro calendar.
- Free/delayed feeds can be stale, partial, rate-limited, or lack authoritative bid/ask and OI updates. Fresh eligible inputs may enter Free Validation with explicit limitations; stale or incomplete core payloads remain Shadow.
- Live trading is not implemented: there is no broker order client or API route for real orders.
- Portfolio OS integration does not exist yet; this project owns its database, paper broker, signal pipeline, and alerts.

Review the four design documents in the project root before enabling credentialed sources. Provider data is informational and may be delayed, incomplete, licensed, or estimated.

## MVP acceptance

Run the repeatable acceptance gate with:

```powershell
python -m options_structure_trader.acceptance
```

It creates a fresh isolated acceptance database, runs standalone-boundary checks, synthetic/stale/incomplete gating, live-disable checks, complete long and short paper lifecycles, replay/ablation variants, macro-event blocking, and API/dashboard smoke tests. Results are written to:

- `acceptance/LATEST_MVP_ACCEPTANCE_REPORT.md`
- `acceptance/LATEST_ACCEPTANCE_EVIDENCE.json`

The machine-readable evidence contains full normalized input snapshots, signal snapshots, score breakdowns, paper orders, journal records, exits, route inventory, and isolation checks.
