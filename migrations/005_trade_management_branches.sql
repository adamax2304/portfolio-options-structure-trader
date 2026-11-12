CREATE TABLE IF NOT EXISTS trade_management_branches (
  id TEXT PRIMARY KEY,
  parent_setup_id TEXT NOT NULL,
  branch TEXT NOT NULL,
  management_version TEXT NOT NULL,
  ticker TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL,
  normalized_json TEXT NOT NULL,
  UNIQUE(parent_setup_id, branch)
);

CREATE INDEX IF NOT EXISTS idx_tm_branches_ticker_status
  ON trade_management_branches(ticker, status);

CREATE INDEX IF NOT EXISTS idx_tm_branches_parent
  ON trade_management_branches(parent_setup_id);
