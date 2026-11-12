CREATE TABLE IF NOT EXISTS market_bars (
  id TEXT PRIMARY KEY, ticker TEXT NOT NULL, timeframe TEXT NOT NULL,
  source TEXT NOT NULL, source_timestamp_utc TEXT NOT NULL,
  ingestion_timestamp_utc TEXT NOT NULL, raw_payload_id TEXT,
  normalized_json TEXT NOT NULL,
  UNIQUE(ticker, timeframe, source, source_timestamp_utc)
);
CREATE TABLE IF NOT EXISTS ticker_states (
  id TEXT PRIMARY KEY, ticker TEXT NOT NULL, source TEXT NOT NULL,
  source_timestamp_utc TEXT NOT NULL, ingestion_timestamp_utc TEXT NOT NULL,
  raw_payload_id TEXT, normalized_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scan_observations (
  id TEXT PRIMARY KEY, run_id TEXT NOT NULL, ticker TEXT NOT NULL,
  observed_at_utc TEXT NOT NULL, data_mode TEXT NOT NULL, outcome TEXT NOT NULL,
  production_eligible INTEGER NOT NULL, setup_event_id TEXT,
  reasons_json TEXT NOT NULL, providers_json TEXT NOT NULL,
  score_total REAL, normalized_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS provider_failures (
  id TEXT PRIMARY KEY, run_id TEXT, ticker TEXT, provider TEXT NOT NULL,
  occurred_at_utc TEXT NOT NULL, error_type TEXT NOT NULL,
  error_message TEXT NOT NULL, retryable INTEGER NOT NULL,
  normalized_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS real_ablation_results (
  id TEXT PRIMARY KEY, run_id TEXT NOT NULL, observation_id TEXT NOT NULL,
  ticker TEXT NOT NULL, created_at_utc TEXT NOT NULL, model_name TEXT NOT NULL,
  score_total REAL, variant_type TEXT, variant_value TEXT,
  normalized_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS daily_reports (
  id TEXT PRIMARY KEY, report_date TEXT NOT NULL UNIQUE,
  generated_at_utc TEXT NOT NULL, report_path TEXT NOT NULL,
  normalized_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_market_bars_ticker_time ON market_bars(ticker, source_timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_observations_time ON scan_observations(observed_at_utc);
CREATE INDEX IF NOT EXISTS idx_observations_ticker ON scan_observations(ticker, observed_at_utc);
CREATE INDEX IF NOT EXISTS idx_provider_failures_time ON provider_failures(occurred_at_utc);

