# Phase 2C Free Validation Report

Generated: 2026-09-02T11:33:44.910229+00:00

**Acceptance status: EMPIRICAL_ACCEPTANCE_PENDING**

The empirical gate requires 50 unique, completed-candle Free Validation scans during US RTH. Current progress is **0/50**. Repeated polls of the same ticker/candle count once.

## Provider status

- demo_fixture: ready; Free Validation=no; Production=no
- algox: ready; Free Validation=yes; Production=no
- alpaca: not configured; Free Validation=yes; Production=yes
- yfinance: ready; Free Validation=yes; Production=no
- alpha_vantage: not configured; Free Validation=yes; Production=no
- finnhub: not configured; Free Validation=yes; Production=no
- gammagrid: not configured; Free Validation=yes; Production=yes
- manual_macro_yaml: ready; Free Validation=no; Production=no
- unusual_whales: not configured; Free Validation=no; Production=no
- quantdata: not configured; Free Validation=no; Production=no

- Macro calendar approved: False
- Provider failures: 0

## Lane totals

- Free Validation valid scans: 0
- Free Validation trades: 0
- Synthetic trades in Free Validation: 0
- Shadow observations: 14
- Rejected observations: 0
- Stale/incomplete observations: 2
- Macro guard blocks: 0

## Scans by ticker

| Ticker | Unique valid scans |
|---|---:|
| — | 0 |

## Score and missing-data distribution

- Average score: N/A
- Score distribution: {}

- None

## Reason distribution

- No option level was known before the latest completed 5m bar; warming up: 14
- US regular session is closed: 14
- bid: 2
- ask: 2
- authoritative_feed_latency: 2
- open_interest: 2
- greeks: 2
- Price provider yfinance is not Production-eligible: 2
- Macro calendar is not approved for Production Paper: 2
- Price/candle data exceeds freshness threshold: 2
- Structure provider algox is not Production-eligible: 1

## Valid but no-trade examples

- No Free-Validation-valid no-trade scan has been collected yet.

## Rejected examples

- No rejected example has been recorded yet.

## Detailed scan lifecycle

- Pending: no Free-Validation-valid detailed scan exists yet.

## Current blockers for Production Paper

- Macro calendar is not approved for Production Paper
- Manual macro calendar is not approved
- No configured Production-eligible candle provider
- No configured complete Production-eligible options-structure provider
- Price provider yfinance is not Production-eligible
- Structure provider algox is not Production-eligible

## Safety and interpretation

- Live trading remains structurally disabled.
- Free Validation is limited-data research paper trading and cannot be promoted to real execution.
- Production Paper gates remain unchanged and strict.
- No score weights, thresholds, stops, targets, or sizing parameters were optimized.
