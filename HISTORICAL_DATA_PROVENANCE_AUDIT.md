# Historical Data Provenance Audit

Generated: 2026-09-04T17:43:02.155196+00:00

Scope: Phase 3C historical EOD options reconstruction only. This does not change live daemon behavior, live/paper strategy parameters, provider gates, Portfolio OS isolation, or live execution settings.

## Source verdict table

| repository/source | dataset host | license / terms observed | actual test result | reliability classification |
|---|---|---|---|---|
| SaidBahaDev/options-data | GitHub + Cloudflare R2 | MIT repo; dataset terms educational/research | 404 for SPY options/underlying Cloudflare URLs | NOT_TRUSTED_FOR_DOWNLOAD |
| SaidBahaDev/options-dataset-hist | GitHub media LFS | MIT | Downloaded/tested SPY/QQQ/IWM 2024-2025 | EXPLORATORY_RESEARCH |
| lambdaclass/options_portfolio_backtester data-v1 | GitHub release | MIT code; data notice says research reproducibility | Remote-read tested; mirrors same upstream | PIPELINE_TEST / EXPLORATORY_RESEARCH |
| Kaggle SPY EOD 2010-2023 | Kaggle | Dataset-specific Kaggle terms | Documented only; no credentials/download | NOT_TESTED |
| Stooq 5m | Stooq web | Public web terms | Direct endpoint returned JS/browser verification | NOT_USABLE_AUTOMATED_HERE |
| piekstra/market-data | GitHub | MIT | Tree tested; no SPY/QQQ/IWM committed files | NOT_USABLE_FOR_PILOT_SYMBOLS |

## Downloaded pilot files

| source | symbol | dataset | size bytes | sha256 |
|---|---|---|---:|---|
| SaidBahaDev/options-dataset-hist | SPY | SPY_underlying.parquet | 252066 | `847e60a441eb10969d87cd4a6da604257b782d9076168f68d5730b84096c79db` |
| SaidBahaDev/options-dataset-hist | SPY | options_2024.parquet | 56948550 | `d9bf7c14b5bfb01cf03bc413773d30eee14026afc377e2daf3d0691a92a0b38d` |
| SaidBahaDev/options-dataset-hist | SPY | options_2025.parquet | 58216546 | `77def9302fec018a926b270841a6507bfd69a5e46b3680fbb78267f73efb611e` |
| SaidBahaDev/options-dataset-hist | QQQ | QQQ_underlying.parquet | 332454 | `78c015fd7fa9d493cd798d5ae81b3c2ae6dc3b8176e25e7bb90cd4114b103351` |
| SaidBahaDev/options-dataset-hist | QQQ | options_2024.parquet | 82434832 | `50083a030d573088d91939d996b5290f54c22d65ca6e567af9e06bf760ad535b` |
| SaidBahaDev/options-dataset-hist | QQQ | options_2025.parquet | 85765453 | `5fdda2f2814c2a9282c67bcad8a1c67a14e2173735c4833c547e43ef10f52291` |
| SaidBahaDev/options-dataset-hist | IWM | IWM_underlying.parquet | 257707 | `e980f50473a8c346ba9ac8b05dcf3da691581dae742f649cb3608d0efe2ef940` |
| SaidBahaDev/options-dataset-hist | IWM | options_2024.parquet | 46366769 | `6cdafbac916d827e6cbb813d1f72d8b646f8e9c2d802fbf819a01d97ea892f3c` |
| SaidBahaDev/options-dataset-hist | IWM | options_2025.parquet | 43819833 | `f3ecb3e6fef169168cf05943d451f3ad47d163c6558449a00099c2b9384a054e` |

## Data content audit

| symbol | rows | dates | range | OI missing | IV missing | gamma missing | bid missing | ask missing | duplicate keys | bad rows |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---|
| SPY | 4612996 | 491 | 2024-01-02 to 2025-12-12 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0 | bid>ask=0; neg_gamma=0; implausible_iv=0 |
| QQQ | 3959760 | 491 | 2024-01-02 to 2025-12-15 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0 | bid>ask=54; neg_gamma=0; implausible_iv=0 |
| IWM | 2335096 | 490 | 2024-01-02 to 2025-12-15 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0 | bid>ask=93; neg_gamma=0; implausible_iv=0 |

## Suspicious anomalies

| symbol | anomaly | date | rows | expirations | strikes | total_oi |
| --- | --- | --- | --- | --- | --- | --- |
| SPY | THIN_OR_HOLIDAY_CHAIN_DATE | 2024-01-15 | 2 | 1 | 1 | 8000.0 |

## Cross-source validation

The lambdaclass release files match the 2024 GitHub-media per-year files on contract/date keys and bid/ask/OI for SPY, QQQ, and IWM. IV/gamma differences are only float precision differences from Parquet typing. This is a mirror validation, not independent exchange-source validation.

```json
{
  "SPY": {
    "local_rows": 2292800,
    "remote_rows": 2292800,
    "joined_rows": 2292800,
    "local_not_remote": 0,
    "remote_not_local": 0,
    "oi_diff_rows": 0.0,
    "bid_diff_rows": 0.0,
    "ask_diff_rows": 0.0,
    "max_gamma_diff": 5.397796631889662e-08,
    "max_iv_diff": 4.0557861247236815e-07,
    "assessment": "MIRROR_OR_SAME_UPSTREAM_FLOAT_PRECISION_DIFFERENCES_ONLY"
  },
  "QQQ": {
    "local_rows": 1958960,
    "remote_rows": 1958960,
    "joined_rows": 1958960,
    "local_not_remote": 0,
    "remote_not_local": 0,
    "oi_diff_rows": 0.0,
    "bid_diff_rows": 0.0,
    "ask_diff_rows": 0.0,
    "max_gamma_diff": 5.905151367890937e-08,
    "max_iv_diff": 4.660034171877214e-07,
    "assessment": "MIRROR_OR_SAME_UPSTREAM_FLOAT_PRECISION_DIFFERENCES_ONLY"
  },
  "IWM": {
    "local_rows": 1188822,
    "remote_rows": 1188822,
    "joined_rows": 1188822,
    "local_not_remote": 0,
    "remote_not_local": 0,
    "oi_diff_rows": 0.0,
    "bid_diff_rows": 0.0,
    "ask_diff_rows": 0.0,
    "max_gamma_diff": 1.1863708504478154e-07,
    "max_iv_diff": 2.3803710913483656e-07,
    "assessment": "MIRROR_OR_SAME_UPSTREAM_FLOAT_PRECISION_DIFFERENCES_ONLY"
  }
}
```

## Provenance assessment

The pilot data is suitable for `PIPELINE_TEST` and `EXPLORATORY_RESEARCH`. It is not yet reliable enough for `SERIOUS_BACKTEST` because the original upstream sourcing and publication timing are not documented and at least one holiday/anomaly row exists.
