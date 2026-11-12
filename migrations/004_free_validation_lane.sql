ALTER TABLE scan_observations ADD COLUMN free_validation_eligible INTEGER NOT NULL DEFAULT 0;
ALTER TABLE scan_observations ADD COLUMN lane TEXT NOT NULL DEFAULT 'shadow_paper';
ALTER TABLE scan_observations ADD COLUMN candle_end_utc TEXT;
ALTER TABLE scan_observations ADD COLUMN data_quality_json TEXT NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_observations_lane_time ON scan_observations(lane, observed_at_utc);
CREATE INDEX IF NOT EXISTS idx_observations_candle ON scan_observations(ticker, candle_end_utc);
