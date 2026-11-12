-- Keep clean-forward status/report queries bounded to the prospective cohort.
-- These indexes do not alter strategy behavior or research records.

CREATE INDEX IF NOT EXISTS idx_intraday_edge_events_created_at
  ON intraday_options_edge_events(created_at_utc);

CREATE INDEX IF NOT EXISTS idx_intraday_edge_branches_created_at
  ON intraday_options_edge_branches(created_at_utc);

CREATE INDEX IF NOT EXISTS idx_intraday_edge_branches_ticker_exit_reason
  ON intraday_options_edge_branches(ticker, exit_reason);
