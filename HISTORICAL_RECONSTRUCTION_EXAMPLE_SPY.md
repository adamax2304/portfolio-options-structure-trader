# Historical Reconstruction Example: SPY

Generated: 2026-09-04T17:43:02.288245+00:00

This example demonstrates the Phase 3C rule: the replay for `2024-01-03` may use only the EOD option chain from `2024-01-02`.

## Inputs

- Symbol: SPY
- Chain source: SaidBahaDev/options-dataset-hist via GitHub media LFS
- Chain quote date: 2024-01-02
- Trade date: 2024-01-03
- Lookahead safe: True
- Publication timing verified: False
- Publication note: D-1 EOD snapshot used for next trading day; exact upstream publication time not documented.
- Model: GEX_MODEL_A_CALL_POSITIVE_PUT_NEGATIVE
- Formula version: phase3c_gex_eod_v2_near_spot_gamma_flip_proxy

## D-1 / D daily underlying context

| date | open | high | low | close | volume |
| --- | --- | --- | --- | --- | --- |
| 2024-01-02 | 472.16 | 473.67 | 470.49 | 472.65 | 123007793 |
| 2024-01-03 | 470.43 | 471.19 | 468.17 | 468.79 | 103585866 |

## Top strikes by OI on D-1

| type | strike | open_interest |
| --- | --- | --- |
| put | 400.0 | 549776.0 |
| put | 440.0 | 435105.0 |
| put | 450.0 | 418827.0 |
| put | 430.0 | 406338.0 |
| put | 460.0 | 395443.0 |
| put | 420.0 | 395221.0 |
| put | 405.0 | 390935.0 |
| call | 480.0 | 387541.0 |
| put | 415.0 | 362470.0 |
| call | 460.0 | 255409.0 |

## Top strikes by gamma × OI on D-1

| type | strike | gamma_oi |
| --- | --- | --- |
| put | 473.0 | 13511.58328 |
| call | 473.0 | 10891.224180000001 |
| call | 480.0 | 8243.165200000001 |
| call | 476.0 | 7253.659189999999 |
| put | 470.0 | 6394.868850000001 |
| call | 475.0 | 6387.680899999998 |
| put | 472.0 | 5304.720070000002 |
| put | 475.0 | 5116.639070000001 |
| put | 460.0 | 4872.0986299999995 |
| call | 470.0 | 4320.7102099999975 |

## Reconstructed levels for D

- Spot reference from D-1 close: 472.65
- Gamma flip: 474.1411
- Call wall: 473.0
- Put wall: 473.0
- Top positive GEX nodes: `[{"strike": 480.0, "value": 1598555660.4074}, {"strike": 476.0, "value": 1119498559.5354}, {"strike": 485.0, "value": 482554439.3598}, {"strike": 490.0, "value": 444094959.6158}, {"strike": 495.0, "value": 391224573.8519}]`
- Top negative GEX nodes: `[{"strike": 472.0, "value": -680516045.7927}, {"strike": 473.0, "value": -585383041.1799}, {"strike": 450.0, "value": -488335879.653}, {"strike": 469.0, "value": -471129567.3698}, {"strike": 470.0, "value": -463362938.5273}]`
- Top absolute gamma nodes: `[{"strike": 473.0, "value": 5451538930.0122}, {"strike": 475.0, "value": 2570042331.5053}, {"strike": 470.0, "value": 2393839171.9464}, {"strike": 476.0, "value": 2121407678.3345}, {"strike": 480.0, "value": 2084457949.2343}]`
- Top OI call nodes: `[{"strike": 480.0, "value": 387541.0}, {"strike": 460.0, "value": 255409.0}, {"strike": 495.0, "value": 215635.0}, {"strike": 500.0, "value": 201689.0}, {"strike": 490.0, "value": 201417.0}]`
- Top OI put nodes: `[{"strike": 400.0, "value": 549776.0}, {"strike": 440.0, "value": 435105.0}, {"strike": 450.0, "value": 418827.0}, {"strike": 430.0, "value": 406338.0}, {"strike": 460.0, "value": 395443.0}]`

## Intraday replay status

The D-1 → D option-level snapshot is valid for an honest Level 2 EOD reconstruction. The LEVEL_RECLAIM intraday replay is not run yet because no validated free 2024-2025 SPY/QQQ/IWM 5-minute OHLCV source is available locally.
