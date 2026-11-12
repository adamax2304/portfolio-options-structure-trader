# Future Integration Contract

Integration is read-only and may begin only after an out-of-sample validation review approves a setup family. Portfolio OS consumes finalized signal copies by HTTP, signed webhook, or versioned JSONL/Parquet export. It never reads this database and never mutates a signal.

## Stable signal object (v1)

```json
{
  "schema_version": "options_structure_signal.v1",
  "signal_id": "uuid",
  "signal_family": "OPTIONS_STRUCTURE",
  "strategy_module": "options_structure_trader",
  "source_service": "options_structure_trader",
  "ticker": "OKLO",
  "setup_family": "LEVEL_RECLAIM_LONG",
  "direction": "LONG",
  "score": 82,
  "score_model_version": "score_v0_baseline_manual",
  "config_version": "sha256:...",
  "entry_zone": [40.05, 40.25],
  "stop": 39.55,
  "targets": [41.0, 42.0, 45.0],
  "invalidation_logic": "5m close below the reclaimed zone",
  "mode": "paper_validated",
  "created_at_utc": "2026-01-01T15:00:00Z",
  "data_freshness": {"gex_seconds": 120, "price_seconds": 2},
  "blocking_reasons": []
}
```

Consumers must treat `signal_id` as an idempotency key. Contract additions are backward-compatible; breaking changes require a new schema version. A webhook should include timestamp, event ID, and HMAC signature headers. File exports are append-only and include checksums.

## Promotion gate

Before integration: adequate sample size, positive out-of-sample expectancy, documented drawdown and failure modes, deterministic replay, no-lookahead audit, data-license review, and explicit human approval. Integration does not authorize live execution. Portfolio OS owns any later manual-confirmation or broker workflow.

