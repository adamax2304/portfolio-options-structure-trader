# Phase 2D Daemon and Watchlist Report

Generated: 2026-09-02T12:23:54.708147+00:00

**Acceptance status: EMPIRICAL_ACCEPTANCE_PENDING**

## Empirical progress

- Free Validation scans: **0/500**
- Tier 1 Free Validation scans: **0/50**
- Symbols with valid scans: **0/20**
- Synthetic Free Validation scans: **0**
- Configured watchlist symbols: **52**

## Daemon

- Status: SLEEPING
- Current session state: CLOSED
- Next RTH open: 2026-09-02T13:30:00+00:00
- Next RTH close: 2026-09-02T20:00:00+00:00
- Last scan: 2026-09-01T21:54:24.111733+00:00
- Next scan: 2026-09-02T13:40:00+00:00
- Daily report status: generated
- Last error: None

## Provider readiness

- demo_fixture: configured; Free Validation=no
- algox: configured; Free Validation=yes
- alpaca: not configured; Free Validation=yes
- yfinance: configured; Free Validation=yes
- alpha_vantage: not configured; Free Validation=yes
- finnhub: not configured; Free Validation=yes
- gammagrid: not configured; Free Validation=yes
- manual_macro_yaml: configured; Free Validation=no
- unusual_whales: not configured; Free Validation=no
- quantdata: not configured; Free Validation=no

## Safety

- Live trading remains structurally disabled.
- No broker order submission route exists.
- The daemon uses this project's standalone database, broker, journal, logs, and reports.
- No Portfolio OS integration or writes are present.
- No score, setup, stop, target, sizing, or Production eligibility logic was changed.

The empirical gate remains pending until all scan-count and symbol-coverage targets are met naturally during valid RTH windows.
