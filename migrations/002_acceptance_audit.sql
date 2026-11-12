CREATE TABLE IF NOT EXISTS audit_events (
  id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  timestamp_utc TEXT NOT NULL,
  severity TEXT NOT NULL,
  ticker TEXT,
  outcome TEXT NOT NULL,
  reasons_json TEXT NOT NULL,
  payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_events_time ON audit_events(timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_audit_events_outcome ON audit_events(outcome);

