# Phase 2A Reclaim Specification

## Common gate

A level must exist before interaction. The confirmation bar is a closed 5-minute bar. Required inputs are the level zone, previous and confirmation bars, ATR, spread, at least one directional options-structure confirmation, target nodes, source timestamps, macro state, and immutable feature snapshot. A one-minute bar cannot create a setup.

## Long

`LEVEL_RECLAIM_LONG` requires the prior/confirmation price path to trade below the zone's lower boundary (or into it when configured) and the closed confirmation bar to finish above the upper boundary. A retest hold is optional in the baseline. Directional confirmation is either bullish flow at/above 0.55 or strong bullish dealer/OI structure at/above 0.65. Opposite flow below 0.25 blocks Production.

Entry zone starts at the greater of the reclaimed upper boundary and confirmation close, with a maximum half-ATR chase allowance. Stop is `min(sweep_low, zone_low) - max(ATR_5m*buffer_multiplier, spread*2, $0.01)`. Targets are the nearest three distinct known structure nodes above entry. TP1 must be at least 1.8R.

## Short

`LEVEL_RECLAIM_SHORT` is symmetric: trade above the upper boundary followed by a closed 5-minute close below the lower boundary. Bearish flow or dealer/OI structure must pass the same thresholds. Stop is `max(sweep_high, zone_high) + buffer`; targets are descending structure nodes below entry and TP1 must be at least 1.8R.

## Score and paper behavior

Each feature component is normalized to 0..1 and multiplied by the versioned configured weight. The production threshold is 75. Freshness/conflict, halt, liquidity, valid stop/targets/RR, family enablement, and Macro Event Guard are hard gates even when the score passes.

Every qualified event creates one canonical candidate. A Production Paper trade is possible only when all gates pass and the input is non-fixture. Shadow records blocked macro candidates and parameter variants without entering Production metrics or sending default alerts. Variants cover entry, ATR stop buffers, target logic, breakeven policy, and score-weight sets.

## Acceptance tests

Tests cover both directions, pre-existing levels, closed-candle enforcement, structural stops, target ordering and 1.8R, score versioning, source conflict, stale data, macro block with Shadow allowance, pessimistic same-bar handling, pending expiry, immutable snapshots, deterministic replay, and Production/Shadow metric separation.

