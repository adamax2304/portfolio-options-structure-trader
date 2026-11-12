CREATE TABLE IF NOT EXISTS phase4a_activation (
  id TEXT PRIMARY KEY,
  activated_at_utc TEXT NOT NULL,
  discovery_cutoff_utc TEXT NOT NULL,
  normalized_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS intraday_options_edge_events (
  id TEXT PRIMARY KEY,
  parent_event_id TEXT NOT NULL UNIQUE,
  ticker TEXT NOT NULL,
  trade_date TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  level_cluster_id TEXT NOT NULL,
  direction TEXT NOT NULL,
  structural_family TEXT NOT NULL,
  level_tier TEXT NOT NULL,
  level_type TEXT NOT NULL,
  interaction_episode TEXT NOT NULL,
  source_setup_id TEXT,
  source_observation_id TEXT,
  normalized_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_intraday_edge_events_ticker_date
  ON intraday_options_edge_events(ticker, trade_date);

CREATE INDEX IF NOT EXISTS idx_intraday_edge_events_variant_dims
  ON intraday_options_edge_events(direction, structural_family, level_tier, level_type);

CREATE TABLE IF NOT EXISTS intraday_options_edge_branches (
  id TEXT PRIMARY KEY,
  parent_event_id TEXT NOT NULL,
  strategy_variant TEXT NOT NULL,
  timeframe_context TEXT NOT NULL,
  confirmation_tf TEXT NOT NULL,
  execution_tf TEXT NOT NULL,
  entry_variant TEXT NOT NULL,
  management_variant TEXT NOT NULL,
  stop_variant TEXT NOT NULL,
  ticker TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL,
  result_R REAL,
  MFE REAL,
  MAE REAL,
  holding_time_minutes REAL,
  exit_reason TEXT,
  normalized_json TEXT NOT NULL,
  UNIQUE(parent_event_id, strategy_variant, entry_variant, management_variant, stop_variant)
);

CREATE INDEX IF NOT EXISTS idx_intraday_edge_branches_parent
  ON intraday_options_edge_branches(parent_event_id);

CREATE INDEX IF NOT EXISTS idx_intraday_edge_branches_ticker_status
  ON intraday_options_edge_branches(ticker, status);

CREATE INDEX IF NOT EXISTS idx_intraday_edge_branches_variant
  ON intraday_options_edge_branches(strategy_variant, management_variant, stop_variant);
