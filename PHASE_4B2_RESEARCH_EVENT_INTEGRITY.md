# Phase 4B.2-QA — Research Event Integrity

Generated: 2026-09-09T02:21:38.022191+00:00

RTH date: 2026-09-08

Scope: research instrumentation only. Canonical strategy logic, thresholds, weights, stops, targets, provider gates, watchlist, live-execution settings, and Portfolio OS boundaries were not changed.

## Top-line answers

1. Why did 18 scans produce 3,901 parent events? Pre-fix code multiplied each scan across all cluster widths and treated price already above/below many levels as `LEVEL_BREAKOUT`.
2. Was research event/branch inflation present? Yes. The pre-fix ratios were `216.7222` parents/scan and `17984.1667` branches/scan.
3. Were all 3,901 parents valid economic interactions? No. They are marked `QA_PRE_FIX` and excluded from future edge statistics.
4. Was 99% breakout suspicious? Yes. The sampled pre-fix breakout rows lacked strict sequence metadata in `100` / 100 sampled rows.
5. Were persistence fields reliable enough for C/D/P2? Not as top-level trusted fields in pre-fix rows. Post-fix rows now expose required persistence fields and gate missing persistence.
6. Were branches actual setups? No. Registered combinations must be read through `lifecycle_state`; only `PENDING_ENTRY` / `ACTIVE` / `RESOLVED` qualified branches count.

## Multiplication waterfall

- Market scans: 18
- Natural canonical setup events: 5
- Pre-fix research parent events: 3901
- Pre-fix research branches: 323715
- Parents per scan: 216.7222
- Average branches per parent: 82.9826
- Median branches per parent: 83

## Events by symbol

| ticker | parent_events |
| --- | --- |
| QQQ | 620 |
| SPY | 512 |
| META | 315 |
| IWM | 280 |
| AMD | 278 |
| MSFT | 224 |
| AVGO | 220 |
| TSLA | 215 |
| HOOD | 179 |
| AAPL | 168 |
| GOOGL | 148 |
| AMZN | 136 |
| OKLO | 127 |
| SMCI | 126 |
| NVDA | 124 |
| PLTR | 116 |
| MSTR | 78 |
| COIN | 35 |

## Events by structural family

| structural_family | parent_events |
| --- | --- |
| LEVEL_BREAKOUT | 3870 |
| REJECTION | 27 |
| RECLAIM | 4 |

## Events by level type

| level_type | parent_events |
| --- | --- |
| GEX_NODE | 3721 |
| PUT_WALL | 63 |
| CALL_WALL | 62 |
| GAMMA_FLIP | 55 |

## Highest parent counts by scan

| source_observation_id | ticker | parent_events |
| --- | --- | --- |
| obs_c4b38fcce75b4214a353ef3035b96029 | QQQ | 620 |
| obs_6e3191ec6f2e4974bb49ac2c83ca21c4 | SPY | 512 |
| obs_151e306bf6f74fb49fec9abc100ef298 | META | 315 |
| obs_745dc6b18d7d48b0a89cd6f2a0eae4cb | IWM | 280 |
| obs_6efb437ae643477cbd4fa5ad21ca18d7 | AMD | 278 |
| obs_b9d682fd09ed4ec685c139f013f40a2b | MSFT | 224 |
| obs_ced85423b96d482b936f2a3332998f26 | AVGO | 220 |
| obs_e70f387f4b4a45ca88fa3ae4a8fec9fe | TSLA | 215 |
| obs_5e07e9a2b62146e896890224fd901179 | HOOD | 179 |
| obs_cc51f59ce688400ebc49466937a0b4d4 | AAPL | 168 |
| obs_4afd08192d104c3e894cffe57725432d | GOOGL | 148 |
| obs_3bdc93b2d9a44390a0e560746ca69f79 | AMZN | 136 |
| obs_9f2626153f4642ee8b7f0590e476ead2 | OKLO | 127 |
| obs_987273e53b2148769e2c5b1e2d230347 | SMCI | 126 |
| obs_1855ad82f8be4bc4af63730c683e59b0 | NVDA | 124 |
| obs_54003c50567c4dfd933a4e2b2f181454 | PLTR | 116 |
| obs_b2871189de614ca9b78bb6ee649575a3 | MSTR | 78 |
| obs_0eea0deff24b40e1a6934eea3b3401f2 | COIN | 35 |

## Branch lifecycle/status before QA marking

| status | branches |
| --- | --- |
| not_qualified | 188287 |
| pending | 135428 |

## Breakout audit sample

- Sampled breakout parents: 100
- Missing strict sequence metadata: 100
- Post-fix sequence metadata present: 0
- Randomized follow-up sample: 100 / 100 pre-fix breakout parents also lacked `interaction_type`, `approach_direction`, and `confirmation_state`; sampled rows were marked `QA_PRE_FIX`.

## QA reconciliation

- Events marked `QA_PRE_FIX`: 3901
- Branches marked `QA_PRE_FIX`: 323715
- Canonical setup history changed: no
- Canonical paper trade history changed: no

## Post-fix acceptance state

- Only the default ATR width creates economic parent zones; alternate widths are metadata.
- Breakout/breakdown requires zone interaction plus close/acceptance beyond the zone.
- Episode identity persists until price has reset away from the zone for the configured reset bars.
- C/D/P2 require complete persistence fields or become NOT_QUALIFIED_MISSING_PERSISTENCE.
- S2/S3/P3/P4 require their structure/classifier prerequisites before becoming pending.
- Branches carry lifecycle_state separate from raw DB status.
- Pre-fix records are marked QA_PRE_FIX and excluded from future research status/report statistics.
