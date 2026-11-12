# Phase 3B Historical Options Reconstruction

Generated: 2026-09-04T00:00:51.611601+00:00

Status: **PARTIAL_SUCCESS**

No live/paper strategy behavior was changed. The live daemon, forward cohorts, Production gates, no-live-trading rule, and Portfolio OS isolation remain separate from this historical research pipeline.

## Data quality tiers

- `TIER_H1_FULL_INTRADAY`: Timestamped historical option-chain snapshots with intraday OI/Greeks/IV where available, plus underlying intraday OHLCV.
- `TIER_H2_DAILY_CHAIN`: One option chain/OI snapshot per day. Levels are static for the next session and must be known before the tested intraday decision.
- `TIER_H3_PARTIAL_CHAIN`: Incomplete chain or structure snapshot. Missing OI/Greeks/expiries are explicit; usable only for exploratory reconstruction.
- `TIER_H4_PRICE_ONLY_CONTROL`: Underlying-only control with no option-derived structure.

## Data collected

- Symbols requested: SPY, QQQ, IWM, NVDA, AMD, TSLA, AAPL, MSFT, META, AMZN, PLTR, HOOD
- Historical option-chain rows: 0
- Historical GEX/level rows: 95068
- Historical underlying 5m rows: 18720
- Underlying symbols represented: 12
- Underlying calendar days represented: 20
- Options-structure replay rows: 3648
- Price-control replay rows: 9256

## Default evaluation slice

Default slice: `TM_V0_CURRENT`, `SLIPPAGE_3BP`.

Options-structure reconstruction stats:

```json
{
  "N": 152,
  "unique_days": 2,
  "expectancy": 0.0729,
  "profit_factor": 1.3701,
  "win_rate": 0.7566,
  "median_R": 0.0648,
  "average_winner": 0.3566,
  "average_loser": -0.8553,
  "MFE": 0.9275,
  "MAE": 0.6771,
  "max_drawdown": 9.1209,
  "positive_day_pct": 0.5,
  "best_day": "2026-09-02",
  "best_day_R": 11.2291,
  "best_day_contribution": 1.0136,
  "worst_day": "2026-09-03",
  "worst_day_R": -0.1511,
  "remove_best_day_expectancy": -0.0018,
  "bootstrap_ci_low": -0.0018,
  "bootstrap_ci_high": 0.1651
}
```

Price-control stats:

```json
{
  "N": 1157,
  "unique_days": 19,
  "expectancy": -0.0863,
  "profit_factor": 0.813,
  "win_rate": 0.4831,
  "median_R": 0.0,
  "average_winner": 0.7764,
  "average_loser": -0.9301,
  "MFE": 1.2776,
  "MAE": 0.9371,
  "max_drawdown": 127.2855,
  "positive_day_pct": 0.2632,
  "best_day": "2026-08-26",
  "best_day_R": 21.4341,
  "best_day_contribution": 0.2147,
  "worst_day": "2026-08-24",
  "worst_day_R": -24.5698,
  "remove_best_day_expectancy": -0.1106,
  "bootstrap_ci_low": -0.1729,
  "bootstrap_ci_high": 0.0152
}
```

## Live-record validation

```json
{
  "live_setup_count": 621,
  "matched_setups": 135,
  "setup_match_rate": 0.2174,
  "level_deviation_median": 0.8538,
  "entry_timing_deviation_median_minutes": 5.0,
  "trust_assessment": "LOCAL_ARCHIVE_VALIDATION_ONLY"
}
```

Interpretation: if local reconstruction does not match the daemon's live records well, older reconstructed backtest results should not be trusted. At this stage the reliable historical structure source is only the local live archive, so the result is partial by design.

## Source probe conclusion

- yfinance/Yahoo: recent 5m underlying candles and current option chains only; no historical chain snapshots.
- Alpha Vantage: `HISTORICAL_OPTIONS` endpoint exists in docs, but configured free key did not return chain rows.
- Finnhub: configured key did not authorize option-chain endpoint in probe.
- Cboe/OCC/NYSE public pages provide useful volume/OI context but not free full historical chain snapshots with bid/ask, IV, OI, and Greeks.

## Controls

Controls are written to `historical_control_comparison.csv` and use no option-derived levels:

- price-only prior range midpoint
- random nearby price level
- previous-day high
- previous-day low

These controls are H4 and are not mixed with option-derived H3 results.

## Limitations

- No free/no-signup source returned timestamp-correct historical US option-chain snapshots.
- Alpha Vantage HISTORICAL_OPTIONS was probed with the configured key and did not return chain rows.
- Finnhub option-chain endpoint returned auth/entitlement failure for the configured key.
- Yahoo/yfinance is usable for recent underlying 5m candles and current chains, not historical chain snapshots.
- Local live archive covers only dates already collected by the daemon and is not a full historical OPRA replay.

## Artifacts

- `historical_option_chains.parquet`: 0 rows, sha256 `b48a5cff2a931b1bf2a68c2dec80ce7bf07cca7ec0e107ea2e17d372a24eaf81`
- `historical_gex_levels.parquet`: 95068 rows, sha256 `24d5fcae4e9af29f64b23e4f58df06907f43d22dddd7f62c2a0af65a91d5de3a`
- `historical_underlying_5m.parquet`: 18720 rows, sha256 `e9b889a22715d63a1be85d4d2a4aacf1e3985f557d76623ca47f5387ab9a7135`
- `historical_replay_trades.parquet`: 12904 rows, sha256 `cef762ea142bcf421e32edbafa3ef5d5a45f1e1994494ec9b45289248dae9ef2`
- `historical_results_by_day.csv`: 19 rows, sha256 `a3c5f0c7c86a96e49ec5048de6edee37191526bdaa8e46065f60a3421659bd6a`
- `historical_results_by_symbol.csv`: 12 rows, sha256 `3ef3bef857f76746e62eadf73fd3b994dc861e56688fb7852f6af8cdf0ee1a3a`
- `historical_results_by_direction.csv`: 2 rows, sha256 `08443de6e49905eb77462b4950b01767c6d1893231ac351d0f6d92075309c3ea`
- `historical_results_by_level_type.csv`: 4 rows, sha256 `1a59bf6812ad09015a33a540354b65ebfe4c3511b9e22d48cbf6e313ce672b17`
- `historical_management_comparison.csv`: 6 rows, sha256 `b4fb9e7c98a62abc248ad9ec2c080557ae79b7997f656e8cdaa277c0b6f4e02b`
- `historical_holdout_results.csv`: 2 rows, sha256 `845c2bdf9942becd7949382ab084775889c4f4c18da75304d6978a865b71056e`
- `historical_control_comparison.csv`: 5 rows, sha256 `a2b55222133e73e32c5d0186490a10b213fc8fc2c69da9528ad1475428715978`

## Acceptance classification

Phase 3B is currently **PARTIAL_SUCCESS**:

- Best case is not met because no configured free source returned 20+ trading days of historical option-chain/OI data.
- Partial success is met if generated H4 controls, local H3 archive levels, manifest, source matrix, and replay outputs exist.
- Failure would be declared only if no usable underlying/control/local archive data could be produced.
