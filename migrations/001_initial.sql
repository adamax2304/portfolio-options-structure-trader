PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
  version TEXT PRIMARY KEY, applied_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS options_raw_payloads (
  id TEXT PRIMARY KEY, source TEXT NOT NULL, ticker TEXT, payload_type TEXT NOT NULL,
  source_timestamp_utc TEXT, ingestion_timestamp_utc TEXT NOT NULL, payload_json TEXT NOT NULL,
  payload_sha256 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS options_chain_snapshots (
  id TEXT PRIMARY KEY, ticker TEXT NOT NULL, source TEXT NOT NULL, source_timestamp_utc TEXT NOT NULL,
  ingestion_timestamp_utc TEXT NOT NULL, expiration TEXT, strike REAL, normalized_json TEXT NOT NULL, raw_payload_id TEXT
);
CREATE TABLE IF NOT EXISTS options_gex_snapshots (
  id TEXT PRIMARY KEY, ticker TEXT NOT NULL, source TEXT NOT NULL, source_timestamp_utc TEXT NOT NULL,
  ingestion_timestamp_utc TEXT NOT NULL, spot REAL NOT NULL, normalized_json TEXT NOT NULL, raw_payload_id TEXT
);
CREATE TABLE IF NOT EXISTS options_oi_snapshots (
  id TEXT PRIMARY KEY, ticker TEXT NOT NULL, source TEXT NOT NULL, source_timestamp_utc TEXT NOT NULL,
  ingestion_timestamp_utc TEXT NOT NULL, strike REAL, expiration TEXT, normalized_json TEXT NOT NULL, raw_payload_id TEXT
);
CREATE TABLE IF NOT EXISTS options_flow_events (
  id TEXT PRIMARY KEY, ticker TEXT NOT NULL, source TEXT NOT NULL, source_timestamp_utc TEXT NOT NULL,
  ingestion_timestamp_utc TEXT NOT NULL, normalized_json TEXT NOT NULL, raw_payload_id TEXT
);
CREATE TABLE IF NOT EXISTS options_flow_aggregates (
  id TEXT PRIMARY KEY, ticker TEXT NOT NULL, window_minutes INTEGER NOT NULL, as_of_utc TEXT NOT NULL, normalized_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS big_trade_events (
  id TEXT PRIMARY KEY, ticker TEXT NOT NULL, source TEXT NOT NULL, source_timestamp_utc TEXT NOT NULL,
  ingestion_timestamp_utc TEXT NOT NULL, normalized_json TEXT NOT NULL, raw_payload_id TEXT
);
CREATE TABLE IF NOT EXISTS option_levels (
  id TEXT PRIMARY KEY, ticker TEXT NOT NULL, level_type TEXT NOT NULL, price REAL NOT NULL,
  zone_low REAL NOT NULL, zone_high REAL NOT NULL, known_at_utc TEXT NOT NULL, source TEXT NOT NULL,
  strength_score REAL NOT NULL, normalized_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS macro_events (
  id TEXT PRIMARY KEY, event_time_utc TEXT NOT NULL, importance TEXT NOT NULL, normalized_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS setup_events (
  id TEXT PRIMARY KEY, ticker TEXT NOT NULL, setup_type TEXT NOT NULL, side TEXT NOT NULL,
  mode TEXT NOT NULL, created_at_utc TEXT NOT NULL, score_total REAL NOT NULL, score_model_version TEXT NOT NULL,
  config_version TEXT NOT NULL, production_allowed INTEGER NOT NULL, blocking_reasons_json TEXT NOT NULL,
  normalized_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS signal_snapshots (
  id TEXT PRIMARY KEY, setup_event_id TEXT NOT NULL UNIQUE, created_at_utc TEXT NOT NULL,
  source_timestamp_utc TEXT, ingestion_timestamp_utc TEXT, feature_values_json TEXT NOT NULL,
  snapshot_json TEXT NOT NULL, FOREIGN KEY(setup_event_id) REFERENCES setup_events(id)
);
CREATE TABLE IF NOT EXISTS paper_trades (
  id TEXT PRIMARY KEY, setup_event_id TEXT NOT NULL, ticker TEXT NOT NULL, setup_type TEXT NOT NULL,
  side TEXT NOT NULL, mode TEXT NOT NULL, status TEXT NOT NULL, created_at_utc TEXT NOT NULL,
  realized_r REAL NOT NULL DEFAULT 0, score_total REAL NOT NULL, score_model_version TEXT NOT NULL,
  config_version TEXT NOT NULL, normalized_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_trade_variants (
  id TEXT PRIMARY KEY, parent_trade_id TEXT, setup_event_id TEXT NOT NULL, variant_type TEXT NOT NULL,
  variant_value TEXT NOT NULL, normalized_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS score_models (
  id TEXT PRIMARY KEY, version TEXT NOT NULL UNIQUE, weight_set_id TEXT NOT NULL, weights_json TEXT NOT NULL,
  config_version TEXT NOT NULL, created_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS score_results (
  id TEXT PRIMARY KEY, setup_event_id TEXT NOT NULL, score_total REAL NOT NULL, breakdown_json TEXT NOT NULL,
  raw_feature_values_json TEXT NOT NULL, score_model_version TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ablation_runs (
  id TEXT PRIMARY KEY, started_at_utc TEXT NOT NULL, completed_at_utc TEXT, status TEXT NOT NULL,
  config_json TEXT NOT NULL, results_json TEXT
);
CREATE TABLE IF NOT EXISTS performance_summaries (
  id TEXT PRIMARY KEY, generated_at_utc TEXT NOT NULL, mode TEXT NOT NULL, group_key TEXT NOT NULL,
  summary_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_levels_ticker_time ON option_levels(ticker, known_at_utc);
CREATE INDEX IF NOT EXISTS idx_setups_ticker_time ON setup_events(ticker, created_at_utc);
CREATE INDEX IF NOT EXISTS idx_trades_mode_status ON paper_trades(mode, status);

