CREATE TABLE IF NOT EXISTS edge_candidates (
  edge_id TEXT PRIMARY KEY,
  description TEXT NOT NULL,
  discovered_at TEXT NOT NULL,
  sample_n INTEGER NOT NULL,
  expectancy REAL NOT NULL,
  PF TEXT NOT NULL,
  MFE REAL,
  MAE REAL,
  bootstrap_CI TEXT NOT NULL,
  discovery_result TEXT NOT NULL,
  holdout_result TEXT NOT NULL,
  status TEXT NOT NULL,
  normalized_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_edge_candidates_status
  ON edge_candidates(status);
