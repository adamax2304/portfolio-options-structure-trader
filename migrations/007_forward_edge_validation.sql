CREATE TABLE IF NOT EXISTS forward_edge_activation (
    id TEXT PRIMARY KEY,
    activated_at_utc TEXT NOT NULL,
    discovery_cutoff_utc TEXT NOT NULL,
    normalized_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS forward_edge_memberships (
    id TEXT PRIMARY KEY,
    parent_setup_id TEXT NOT NULL,
    cohort TEXT NOT NULL,
    management_version TEXT NOT NULL,
    ticker TEXT NOT NULL,
    side TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    normalized_json TEXT NOT NULL,
    UNIQUE(parent_setup_id, cohort, management_version)
);

CREATE INDEX IF NOT EXISTS idx_forward_edge_memberships_parent
    ON forward_edge_memberships(parent_setup_id);

CREATE INDEX IF NOT EXISTS idx_forward_edge_memberships_cohort_version
    ON forward_edge_memberships(cohort, management_version);

CREATE TABLE IF NOT EXISTS short_failure_analysis (
    id TEXT PRIMARY KEY,
    parent_setup_id TEXT NOT NULL UNIQUE,
    ticker TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    normalized_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_short_failure_analysis_ticker
    ON short_failure_analysis(ticker);
