# Phase 4B.3 Forward Validation Plan

Generated: 2026-09-07 04:35 UTC

Scope: freeze historical findings and validate the forward experiment setup. This is not a strategy change.

Canonical strategy, score thresholds, stop rules, target rules, management rules, watchlist, provider gates, macro guard, live-execution settings, and Portfolio OS boundaries remain unchanged.

## Frozen forward hypotheses

### H1: Stop and invalidation

Hypothesis: the current stop may sit inside normal adverse excursion for otherwise valid options-level interactions.

Prospective branches:

- `S0_CANONICAL_STOP`
- `S1_FULL_OPTIONS_LEVEL_ZONE_INVALIDATION`
- `S2_15M_STRUCTURAL_INVALIDATION`
- `S3_LAST_CONFIRMED_HL_LH_INVALIDATION`

Primary measurements:

- N
- independent RTH days
- expectancy
- profit factor
- MAE
- stop frequency
- stop-then-recovery
- stopped trades later reaching +0.5R
- stopped trades later reaching +1R

No stop branch may be promoted before forward evidence.

### H2: Timeframe

Hypothesis: 15m confirmation may reduce 5m noise.

Prospective comparison:

- 5m confirmation / 5m execution
- 15m confirmation / 5m execution

Primary measurements:

- N
- independent RTH days
- expectancy
- profit factor
- directional hit rate
- MFE
- MAE
- entry delay
- missed moves after waiting for confirmation

No timeframe rule may be promoted before forward evidence.

### H3: Profit protection

Hypothesis: current management may give back meaningful favorable excursion.

Prospective branches:

- `M0_CURRENT_MANAGEMENT`
- `M1_HALF_0_5R_RUNNER`
- `M2_HALF_0_7R_RUNNER`
- `M3_PROTECT_AFTER_1R_NO_PARTIAL`
- `M4_STRUCTURE_TRAIL_NO_IMMEDIATE_BE`

Primary measurements:

- trades reaching +0.5R then finishing negative
- trades reaching +0.7R then finishing negative
- trades reaching +1R then finishing negative
- capture efficiency
- giveback R
- expectancy
- profit factor
- drawdown

No management branch may be promoted before forward evidence.

## Options-value experiment remains active

The existing Phase 4B.2 P0-P4 experiment stays active and frozen.

Primary question:

Does `OPTIONS + STRUCTURE` outperform `STRUCTURE ONLY`?

Branches:

- `P0`: price structure only
- `P1`: price structure plus strong options level
- `P2`: price structure plus strong persistent/strengthening options level
- `P3`: price structure plus options level plus direction classifier
- `P4`: price structure plus options level plus direction classifier plus 15m confirmation

Historical static-D1 data could not test true P2 persistence honestly. P2 remains forward-only.

## Pre-RTH verification

Verification date: 2026-09-07.

US session context: 2026-09-07 is a US market holiday. No RTH scans are expected today.

Daemon and automation:

- Windows Task Scheduler entry: `OptionsStructureTraderDaemon`
- Task state: `Running`
- Trigger type: enabled logon trigger
- Restart-on-failure: enabled, restart count 99, restart interval 1 minute
- Daemon process: running
- PID: 7520
- Daemon session state: `CLOSED_WEEKEND_OR_HOLIDAY`
- Next RTH open: 2026-09-08 13:30 UTC
- Next scan: 2026-09-08 13:40 UTC
- Last daemon error: null
- Live trading disabled: true

SQLite:

- Database size: 729,518,080 bytes
- Read-only quick check: ok
- Quick check elapsed time: 50.13 seconds
- No database records were rewritten.

Branch definitions:

- Phase 4B.2 branch matrix is loaded in code.
- Stop branches S0-S3 are present.
- Profit-protection branches M0-M4 are present.
- Options-value branches P0-P4 are present.
- 5m and 15m confirmation fields are present.
- Parent event fields and one-parent/many-branch design are present.
- Stop-recovery tracking fields are present in branch payloads.
- Giveback tracking fields are present in branch payloads.
- 5m/15m structure fields are present in event payloads.
- P0-P4 pairing is present in branch generation logic.
- Deduplication logic uses one parent event identity before branch generation.

Current forward data state:

- `phase4b2_research_branches.csv`: empty before the next RTH event.
- `phase4b2_stop_experiment.csv`: empty before the next RTH event.
- `phase4b2_profit_protection.csv`: empty before the next RTH event.
- `phase4b2_options_value.csv`: empty before the next RTH event.

This is expected because no new RTH session has run since activation.

Safety:

- No live execution route was enabled.
- No canonical parameters were changed.
- No provider gates were changed.
- No Portfolio OS integration was added.
- Existing safety tests passed for Phase 4B.1, Phase 4B.2, and multi-timeframe research: 9 passed.

## First RTH instrumentation audit

During the first completed RTH session after this freeze, perform instrumentation audit only.

Check:

- parent events are created once per economic setup
- each parent has expected H1/H2/H3/P0-P4 branches
- stop-recovery fields populate
- giveback fields populate
- 5m/15m structure fields populate
- P0-P4 remain paired and comparable
- synthetic/test rows are excluded
- canonical paper behavior remains unchanged
- no live execution path appears
- no Portfolio OS writes occur

Do not rank or promote branches after the first session.

## Milestone reports

Milestone 1: 5 independent RTH days.

Output: exploratory report.

Status labels allowed:

- `INSUFFICIENT_SAMPLE`
- `EXPLORATORY`
- `FRAGILE`
- `REJECTED`

Milestone 2: 10 independent RTH days.

Output: preliminary report.

Status labels allowed:

- `INSUFFICIENT_SAMPLE`
- `EXPLORATORY`
- `PRELIMINARY_EDGE`
- `FRAGILE`
- `REJECTED`

Milestone 3: 20 independent RTH days.

Output: primary decision report.

Status labels allowed:

- `INSUFFICIENT_SAMPLE`
- `EXPLORATORY`
- `PRELIMINARY_EDGE`
- `FORWARD_SUPPORTED`
- `FRAGILE`
- `REJECTED`

No branch can be promoted unless forward evidence meets the required sample size, independent-day coverage, robustness, and non-concentration checks.

## Reporting requirements

Each milestone report must keep results separated by:

- source: forward only
- hypothesis: H1, H2, H3, P0-P4
- direction: long vs short
- symbol
- independent trading day
- level type
- level strength
- market structure
- time bucket
- data quality

Required metrics:

- N
- independent RTH days
- expectancy
- profit factor
- win rate
- median R
- average winner
- average loser
- MFE
- MAE
- max drawdown
- stop-then-recovery
- giveback R
- capture efficiency
- P0 vs P4 expectancy delta
- best-symbol contribution
- best-day contribution
- remove-best-symbol result
- remove-best-day result

Historical results remain hypothesis-generating only.

## Automation

A Codex heartbeat check is active for post-RTH milestone review. It should only produce a report when the first-session audit or 5/10/20-day milestone is reached. Otherwise it should return a concise status update.

