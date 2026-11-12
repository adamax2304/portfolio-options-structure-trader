# Historical 5m Source Validation

Generated: 2026-09-04T19:10:40.338644+00:00

Scope: Phase 3C.1 historical price-data validation only. No live daemon, live strategy, forward cohort, canonical management, Portfolio OS, or live-execution behavior was changed.

## Massive / Polygon Stocks Basic

```json
{
  "configured": false,
  "credential_state": "NOT_CONFIGURED",
  "provider": "MASSIVE_FORMERLY_POLYGON",
  "endpoint": "/v2/aggs/ticker/{ticker}/range/5/minute/{from}/{to}",
  "production_grade_for_this_project": false,
  "notes": [
    "Add MASSIVE_API_KEY to local .env to validate the free Stocks Basic entitlement."
  ],
  "usable": false,
  "status": "MASSIVE_API_KEY_NOT_CONFIGURED"
}
```

Current result: `MASSIVE_API_KEY_NOT_CONFIGURED`. If `MASSIVE_API_KEY_NOT_CONFIGURED`, the adapter is present but no authenticated entitlement test could be performed. Add a free Massive developer key to local `.env` as `MASSIVE_API_KEY=` to validate earliest accessible 5m depth.

## WRDS GitHub repository

```json
{
  "repo": "https://github.com/Aryan092/fds-indx-data",
  "status": "FILES_FOUND",
  "repo_status_code": 200,
  "description": "Index ETF (SPY, QQQ, IWM, DIA, IWB) 1-min and 5-min OHLCV data from WRDS TAQ, June 2024 - Dec 2025",
  "default_branch": "master",
  "license": null,
  "size_kb": 83561,
  "pushed_at": "2026-06-13T09:56:28Z",
  "tree_status_code": 200,
  "tree_truncated": false,
  "blob_count": 67,
  "target_5m_files": [
    {
      "path": "indx_data/IWM_5min.csv",
      "size": 1754811,
      "sha": "0f4ece43784ad6936cd7f79879bbf88d8e3e9127"
    },
    {
      "path": "indx_data/QQQ_5min.csv",
      "size": 1753401,
      "sha": "7b0010aef1c036ae684680e0d8bbfc0aad55d92e"
    },
    {
      "path": "indx_data/SPY_5min.csv",
      "size": 1763909,
      "sha": "fdbc9d97983701e12ab40ddb32b879e43aa11197"
    }
  ]
}
```

Repository license metadata is `None`. Because no explicit license file was found, the source is classified as `EXPLORATORY_RESEARCH`, not `SERIOUS_BACKTEST`, even though the files are technically usable for pipeline replay.

## Raw files downloaded

| symbol | url | path | size_bytes | sha256 | downloaded_at_utc |
| --- | --- | --- | --- | --- | --- |
| SPY | https://raw.githubusercontent.com/Aryan092/fds-indx-data/master/indx_data/SPY_5min.csv | C:\Users\adama\Documents\my ai projects\options-structure-trader\data\historical\phase3c1\raw\fds_indx_data\SPY_5min.csv | 1763909 | 789c248091040fcefca332967e0f191392679b9c831d3e060209306a90f47dfe | 2026-09-04T19:09:58.234315+00:00 |
| QQQ | https://raw.githubusercontent.com/Aryan092/fds-indx-data/master/indx_data/QQQ_5min.csv | C:\Users\adama\Documents\my ai projects\options-structure-trader\data\historical\phase3c1\raw\fds_indx_data\QQQ_5min.csv | 1753401 | 077b9ade0172166b82a111d3d161fa1af3cbc34fd21432a54020088742b9da33 | 2026-09-04T19:09:58.238318+00:00 |
| IWM | https://raw.githubusercontent.com/Aryan092/fds-indx-data/master/indx_data/IWM_5min.csv | C:\Users\adama\Documents\my ai projects\options-structure-trader\data\historical\phase3c1\raw\fds_indx_data\IWM_5min.csv | 1754811 | 13539dc9a3aa87a1532c50a26a031590324a45fe6e7db18d93380a959a1a5676 | 2026-09-04T19:09:58.242313+00:00 |

## WRDS 5m file audit

| symbol | rows | dates | range | bars/day | bad_ohlc | dup_ts | after_close_removed | missing_clean_rth | suitability |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SPY | 30966 | 397 | 2024-06-03 to 2025-12-31 | 78/78/78 | 0 | 0 | 216 | 0 | EXPLORATORY_RESEARCH |
| QQQ | 30966 | 397 | 2024-06-03 to 2025-12-31 | 78/78/78 | 0 | 0 | 216 | 0 | EXPLORATORY_RESEARCH |
| IWM | 30966 | 397 | 2024-06-03 to 2025-12-31 | 78/78/78 | 0 | 0 | 216 | 0 | EXPLORATORY_RESEARCH |

## Early-close handling

The raw files have 78 bars on early-close dates. Bars at or after the official early close were excluded from `historical_intraday_5m_v2.parquet`.

| symbol | date | session_close_et | raw_rows | rows_after_close_removed |
| --- | --- | --- | --- | --- |
| SPY | 2024-07-03 | 2024-07-03T13:00:00-04:00 | 78 | 36 |
| SPY | 2024-11-29 | 2024-11-29T13:00:00-05:00 | 78 | 36 |
| SPY | 2024-12-24 | 2024-12-24T13:00:00-05:00 | 78 | 36 |
| SPY | 2025-07-03 | 2025-07-03T13:00:00-04:00 | 78 | 36 |
| SPY | 2025-11-28 | 2025-11-28T13:00:00-05:00 | 78 | 36 |
| SPY | 2025-12-24 | 2025-12-24T13:00:00-05:00 | 78 | 36 |
| QQQ | 2024-07-03 | 2024-07-03T13:00:00-04:00 | 78 | 36 |
| QQQ | 2024-11-29 | 2024-11-29T13:00:00-05:00 | 78 | 36 |
| QQQ | 2024-12-24 | 2024-12-24T13:00:00-05:00 | 78 | 36 |
| QQQ | 2025-07-03 | 2025-07-03T13:00:00-04:00 | 78 | 36 |
| QQQ | 2025-11-28 | 2025-11-28T13:00:00-05:00 | 78 | 36 |
| QQQ | 2025-12-24 | 2025-12-24T13:00:00-05:00 | 78 | 36 |
| IWM | 2024-07-03 | 2024-07-03T13:00:00-04:00 | 78 | 36 |
| IWM | 2024-11-29 | 2024-11-29T13:00:00-05:00 | 78 | 36 |
| IWM | 2024-12-24 | 2024-12-24T13:00:00-05:00 | 78 | 36 |
| IWM | 2025-07-03 | 2025-07-03T13:00:00-04:00 | 78 | 36 |
| IWM | 2025-11-28 | 2025-11-28T13:00:00-05:00 | 78 | 36 |
| IWM | 2025-12-24 | 2025-12-24T13:00:00-05:00 | 78 | 36 |

## Cross-check status

Massive-vs-WRDS bar-level comparison was not run because no Massive key is configured. Fallback validation compared WRDS RTH daily rollups against the Phase 3C daily underlying files.

| symbol | status | overlap_days | close_median_bps | close_p95_bps | open_median_bps | high_p95_bps | low_p95_bps | volume_median_deviation_pct | assessment |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| IWM | DAILY_ROLLUP_CROSSCHECK_COMPLETE | 385 | 4.4559 | 12.9579 | 0.0 | 612.0878 | 687.8672 | 9.7511 | CLOSES_USABLE_HIGH_LOW_VOLUME_REQUIRE_CAUTION |
| QQQ | DAILY_ROLLUP_CROSSCHECK_COMPLETE | 386 | 4.2781 | 13.6623 | 0.0 | 436.5609 | 834.8591 | 11.1882 | CLOSES_USABLE_HIGH_LOW_VOLUME_REQUIRE_CAUTION |
| SPY | DAILY_ROLLUP_CROSSCHECK_COMPLETE | 385 | 4.0555 | 13.705 | 0.0 | 192.1951 | 924.8352 | 16.075 | CLOSES_USABLE_HIGH_LOW_VOLUME_REQUIRE_CAUTION |

Worst close deviations:

| symbol | trade_date | close_deviation_bps | open_deviation_bps | high_deviation_bps | low_deviation_bps | volume_deviation_pct |
| --- | --- | --- | --- | --- | --- | --- |
| SPY | 2025-04-09 | 91.68459042688879 | 0.0 | 41.558820312784306 | 84.87982963188323 | 17.543371930652373 |
| QQQ | 2024-12-18 | 31.366778322071067 | 0.0 | 0.0018626139658962449 | 0.0 | 17.368202985732726 |
| IWM | 2025-04-08 | 30.88891431186318 | 0.0 | 829.9268502581759 | 0.0 | 7.685002899629854 |
| IWM | 2025-05-30 | 29.258302043204484 | 0.0 | 33.21292637397281 | 0.49130392060483963 | 13.816030534533047 |
| SPY | 2024-12-18 | 27.972982192808665 | 0.0 | 12.120612461968712 | 0.0 | 28.130787567953803 |
| QQQ | 2024-10-31 | 24.387723468015913 | 0.20309517039666325 | 75.75696038015568 | 0.0 | 12.513887660464546 |
| QQQ | 2025-04-04 | 22.724394918020863 | 0.0 | 937.2800145332328 | 8.990465374878639 | 14.25281424662576 |
| IWM | 2024-08-08 | 22.475711730870273 | 0.0 | 858.4541062801937 | 64.00059063838131 | 13.901807025913934 |
| QQQ | 2025-05-06 | 22.226376685153884 | 0.0 | 39.9958767137408 | 0.2091218971536608 | 13.92638573843778 |
| IWM | 2025-10-29 | 21.471398476746117 | 0.4018646519848459 | 0.0 | 0.20434018554070263 | 5.690921980251036 |

## Verdict

- WRDS GitHub 5m files are technically usable for an exploratory Level 2 replay.
- Price closes agree closely enough with daily references for pipeline testing.
- High/low and volume deviations require caution; no serious edge conclusion should rely on this source alone.
- Massive remains the preferred authenticated cross-check once a free key is provided.
