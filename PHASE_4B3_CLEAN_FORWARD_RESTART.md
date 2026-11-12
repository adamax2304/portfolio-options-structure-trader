# Phase 4B.3 — Clean Forward Validation Restart

Generated: 2026-09-23  
Clean forward cutoff: `2026-09-23T02:03:17.850727+00:00`

## Outcome

The prospective research pipeline is ready for a new, clean RTH sample. Canonical paper behavior was not changed. Live trading remains structurally disabled and Portfolio OS remains isolated.

No edge conclusion is made in this report. All Phase 4A/4B results collected before the clean cutoff remain available for audit, but they are excluded from forward promotion statistics.

## Why a clean restart was required

The pre-fix research dataset contained two instrumentation defects:

1. Some unfilled research orders were expired using a planned entry as though it were a real fill, creating fabricated research P/L.
2. Scan observations repeatedly embedded full monitored research-branch payloads, causing multi-gigabyte database growth.

The prior broad forward matrix also produced far more counterfactual rows than were needed for the frozen hypotheses.

The canonical paper-trade table was not rewritten. A forensic database copy and full pre-compaction scan archive were preserved under `data/forensics/`.

## Integrity repairs

- `14,963` historical no-fill branches were quarantined as `ACCOUNTING_INVALID_PRE_FIX` during the first reconciliation. They retain their original values in audit metadata and cannot enter forward statistics.
- No remaining no-fill branch carries realized R, MFE, or MAE.
- An unfilled order now ends as `CENSORED_NO_ENTRY`, with null P/L and no fabricated `EXIT` event.
- Research monitoring stored in scan observations is now a compact receipt, not a copy of all branches.
- Forward status/report queries now filter by the clean cutoff inside SQLite and use dedicated timestamp indexes, so the 530k-row legacy research table is not loaded into memory on every dashboard request.
- The active SQLite database was compacted without changing canonical paper records.
- Full scan payloads were archived in Parquet with a checksum and manifest.
- SQLite `PRAGMA quick_check` returned `ok` after the final clean activation.

## Forward event semantics

One economic price × options-zone interaction creates one parent event:

`symbol + trade date + economic cluster + direction + interaction family + episode`

Clustering-width experiments are metadata/branch settings, not separate empirical parents. Repeated oscillation inside one episode is suppressed until the deterministic reset condition is met.

Research branches have explicit lifecycle states:

- `REGISTERED_AWAITING_CONFIRMATION`
- `NOT_QUALIFIED`
- `PENDING_ENTRY`
- `ACTIVE`
- `RESOLVED`
- `CENSORED_NO_ENTRY`
- `CENSORED_NOT_QUALIFIED`

Only qualified and actually filled branches can contribute P/L statistics.

## Focused matrix: 22 branches per parent

The forward matrix is intentionally small:

- Phase 4A A/B/C/D × TM_V0/TM_V3: 8 branches
- H1 stop/invalidation S0/S1/S2/S3: 4 branches
- H3 profit protection M0/M1/M2/M3/M4: 5 branches
- P0/P1/P2/P3/P4 options-value decomposition: 5 branches

Historical replay grids remain separate and do not inflate prospective N.

## Direction and timeframe logic

Level names are not treated as directional commands.

`Call Wall != automatic SHORT`  
`Put Wall != automatic LONG`  
`Gamma Flip / GEX node = reaction zone first`

The forward research sequence is:

1. identify one economic options zone;
2. observe approach and classify reclaim/rejection/breakout/breakdown;
3. calculate deterministic price structure;
4. require real snapshot persistence/strengthening where the branch needs it;
5. classify the zone's current directional role;
6. for B/D/P4, wait for a fully completed exchange-aligned 15-minute confirmation;
7. evaluate the 5-minute execution only after confirmation is known.

Partial 15-minute candles are never used. If confirmation arrives later, the branch transitions from registered to pending and can enter only on the next 5-minute bar. If the next completed 15-minute bar does not confirm the same family and direction, the branch is censored as not qualified.

## Honest persistence and structural invalidation

Persistence now uses separate 5m, 15m, and 30m historical snapshot comparisons. Missing horizons remain null and C/D/P2 are not qualified.

H1 stops are now structurally distinct:

- S0: canonical stop
- S1: full options-zone invalidation
- S2: last confirmed 15m structural swing invalidation
- S3: last confirmed 5m higher-low/lower-high invalidation

S2/S3 no longer use fixed ATR offsets as proxies. If the required confirmed pivot does not exist before the event, that branch is `NOT_QUALIFIED` with an exact reason.

## P0–P4 interpretation

P0–P4 share a stable parent key. P0/P1 use the same planned entry, initial stop, direction, management, and subsequent market path.

P0 masks options identity and qualification on the same zone. Therefore P0–P4 measures the incremental value of options metadata, level strength, persistence, direction classification, and 15m confirmation on an identical zone/path.

This pair alone does **not** prove that an options-selected price location beats an independently selected non-options location. That broader location question still requires matched ordinary-zone controls. The reports now state this limitation explicitly and use common resolved parent pairs for P0-vs-P4 statistics.

## Frozen prospective hypotheses

### H1 — Stop / invalidation

Question: is `BAD_STOP` causal, or only associated with losing trades?

Compare S0/S1/S2/S3 on the same entry and direction. Track expectancy, PF, drawdown, winner preservation, stop frequency, and post-stop recovery to +0.5R/+1R.

### H2 — Timeframe

Question: does completed 15m confirmation reduce 5m noise enough to offset later/missed entries?

Compare A vs B and C vs D on common eligible parent events. Track delayed confirmation, missed moves, MFE/MAE, expectancy, and PF.

### H3 — Profit protection

Question: is favorable excursion systematically given back?

Compare M0–M4 on the same entry and initial stop. Track +0.5R/+0.7R/+1R givebacks, capture efficiency, runner contribution, PF, expectancy, and drawdown.

### Options value — P0 to P4

Question: does adding strong/current options information improve the same price-structure event?

Primary paired comparison: P4 vs P0 using only parents resolved in both branches. P1/P2/P3 isolate level strength, persistence, and direction-classifier contributions.

## Sequential evidence plan

1. **First clean RTH day:** instrumentation audit only. Verify counts, lifecycle transitions, dedup, persistence completeness, 15m timing, S2/S3 sources, fills, and P0–P4 pairing. No edge interpretation.
2. **5 independent RTH days:** exploratory report. Identify only operational failures or large mechanistic differences. No promotion.
3. **10 independent RTH days:** preliminary report. Require meaningful resolved N and inspect symbol/day concentration.
4. **20 independent RTH days:** primary decision report. A candidate still needs sufficient paired N, positive expectancy, PF > 1, acceptable drawdown, and robustness to removing the best day, best symbol, and top five winners.

The existing Phase 4A standard remains binding: trade count alone is insufficient. A serious candidate should normally have at least 20 independent RTH days and approximately 150 resolved observations; rarer paired comparisons must be labeled insufficient rather than relaxed.

## Acceptance checks completed

- focused branch matrix: 22 branches per parent
- no-fill P/L fabrication removed
- same-zone P0/P1 pairing verified
- completed-bar 15m wait/qualification/next-bar entry verified
- persistence horizons verified independently
- S2/S3 confirmed-structure source verified
- canonical paper table unchanged
- full tests: `90 passed`
- active database quick check: `ok`
- Task Scheduler: enabled, restart-on-failure retained
- daemon stop/start: passed
- daemon state after restart: sleeping outside RTH, no error
- live trading: disabled
- Portfolio OS: isolated

## Next automatic checkpoint

The daemon will wake for the next US RTH. The next report is an instrumentation-only audit after the first completed clean session. Edge evaluation starts only after the 5-day milestone and cannot be promoted before the 20-day decision point.
