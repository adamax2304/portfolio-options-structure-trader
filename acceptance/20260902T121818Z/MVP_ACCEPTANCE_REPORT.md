# MVP Acceptance Report

Generated: 2026-09-02T12:18:18.256551+00:00

Overall result: **FAIL**. Full machine-readable evidence is in `acceptance_evidence.json`.

## Acceptance checks

| Check | Result |
|---|---|
| Standalone Imports | FAIL |
| Portfolio Database Unchanged | PASS |
| Standalone Paper Broker | PASS |
| Standalone Alerting | PASS |
| Synthetic Shadow Only | PASS |
| Synthetic Production Rejected | PASS |
| Stale Shadow Only | PASS |
| Stale Production Rejected | PASS |
| Incomplete Rejection Audited | PASS |
| Live Execution Absent | PASS |
| Live Flags Inert | PASS |
| Live Mode Rejected | PASS |
| Long End To End | PASS |
| Short End To End | PASS |
| Replay Ablation Complete | PASS |
| Variants Complete | PASS |
| Macro Guard Complete | PASS |
| Api Dashboard Complete | PASS |

## 1. Standalone isolation

- Python imports inspected: 133.
- Forbidden Portfolio/Master Orchestrator imports: 0.
- Portfolio DB files changed during the run: 0.
- Acceptance DB: `C:\Users\adama\Documents\my ai projects\options-structure-trader\acceptance\20260902T121818Z\acceptance.db` (inside this standalone project).
- Paper broker class: `options_structure_trader.broker.StandalonePaperBroker`.
- Alert dispatcher: `options_structure_trader.alerts.AlertDispatcher`; standalone Telegram disabled by default.

## 2. Synthetic, stale, and incomplete-data gating

- Synthetic scan produced `shadow_paper` with blockers: Production Paper requires real normalized data, Synthetic data cannot enter Production Paper, Macro calendar is not approved for Production Paper, Price provider demo_fixture is not Production-eligible, Structure provider demo_fixture is not Production-eligible, Data confidence is below the Production Paper floor, Primary R:R 1.59 is below minimum, Synthetic fixture data cannot enter Production Paper.
- Forced Production acceptance returned: `Blocked setup cannot enter Production Paper`.
- Stale normalized data blockers: Required normalized fields are incomplete, Price/candle data exceeds freshness threshold, Data confidence is below the Production Paper floor, Critical market data is stale.
- Forced stale Production acceptance returned: `Blocked setup cannot enter Production Paper`.
- Incomplete payload status: `rejected`; audit event `audit_339fc06fc49d4ec79b9a397a23aef46f`.
- Audit journal records generated: 9.

## 3. Live trading structural disablement

- Live execution tokens found in Python source: [].
- Health remains `live_auto_enabled=false` even with env/config attempts: False / False.
- `live_assisted` broker acceptance: `Only standalone paper modes are executable`.
- Real-order API routes: [].

## 4. Full LEVEL_RECLAIM_LONG example

- Snapshot: ACCLONG at 2026-08-03T15:00:00Z; 5m bar closed = True.
- Detected level: GAMMA_FLIP 99.90-100.10, known at 2026-08-03T14:00:00Z.
- Reclaim: sweep 99.00; confirmation close 100.50.
- Confluence: 92.75/100 using `score_v0_baseline_manual`.
- Entry: 100.50-100.54; structural stop 98.85.
- Targets: 105.00, 108.00, 112.00; primary R:R 2.727 (gate passed).
- Paper order: `production_paper` / `market_sim`; fill 100.5101; 151 shares.
- Journal result: `closed` via `breakeven_stop`; realized 0.9011R; MFE 2.7649R; MAE 0.0663R.

## 5. Full LEVEL_RECLAIM_SHORT example

- Snapshot: ACCSHORT at 2026-08-03T16:00:00Z; 5m bar closed = True.
- Detected level: GAMMA_FLIP 99.90-100.10, known at 2026-08-03T15:00:00Z.
- Reclaim: sweep 101.00; confirmation close 99.50.
- Confluence: 92.75/100 using `score_v0_baseline_manual`.
- Entry: 99.46-99.50; structural stop 101.15.
- Targets: 95.00, 92.00, 88.00; primary R:R 2.727 (gate passed).
- Paper order: `production_paper` / `market_sim`; fill 99.4900; 151 shares.
- Journal result: `closed` via `breakeven_stop`; realized 0.9011R; MFE 2.7652R; MAE 0.0662R.

## 6. Replay and ablation

- Replay snapshots: 2; setups detected: 2; lookahead rejections: 0.
- Determinism hash: `0f2c8f20f17363191e65c05f07f339d7a548fe86c7837ddd654570c6af453bf6`.

| Score model | Score |
|---|---:|
| baseline_manual | 92.75 |
| equal_weight | 92.14 |
| no_flow | 93.44 |
| no_gex | 92.00 |
| no_oi | 93.06 |
| price_action_only | 100.00 |
| options_only | 91.67 |

- Stop variants: 0.15, 0.3, 0.5, 0.75.
- TP variants: next_gex_node, fixed_R_1_2_3, partials_next_nodes, dynamic_flow_exit.
- Breakeven variants: none, after_1R, after_TP1, after_TP1_plus_retest.

## 7. Macro Event Guard

Outside-event scan: blocked = False, Production eligible = True.

| Event | Guard blocked | Production allowed | Recorded mode |
|---|---:|---:|---|
| CPI | True | False | shadow_paper |
| FOMC | True | False | shadow_paper |
| NFP | True | False | shadow_paper |

Each blocked setup is journaled with `macro_event_proximity_flag=true` and recorded only in Shadow Paper.

## 8. API and dashboard

- Health: `ok`; live auto = False.
- Dashboard HTTP status: 200; title present = True.
- Latest scans: 8.
- Journal events: 9.
- Open paper trades: 5.
- Closed paper trades: 2.
- Ablation weight sets: baseline_full, baseline_manual, equal_weight, free_gex_price_macro, free_gex_price_only, no_dark_pool, no_flow, no_gex, no_macro_filter, no_oi, no_oi_no_greeks, options_only, price_action_only, price_only_shadow.
- Config status: version `sha256:c35dca864f3d5248`, DB `C:\Users\adama\Documents\my ai projects\options-structure-trader\acceptance\20260902T121818Z\acceptance.db`.

## 9. Known Limitations

- Synthetic inputs exercise deterministic behavior only; they do not establish trading edge and are never Production-eligible.
- Fresh provider credentials and applicable market-data entitlements are required before Production Paper can use real feeds.
- Free/delayed GEX, options, FINRA, and off-exchange data can be incomplete or stale; delayed dark-pool context is not an intraday trigger.
- Live trading is unavailable. There is no real broker-order execution path.
- Portfolio OS integration has not been enabled; the standalone read-only contract remains a future boundary after validation.
- Sample replay validates mechanics and determinism, not statistical expectancy. Promotion still requires adequate out-of-sample data.
