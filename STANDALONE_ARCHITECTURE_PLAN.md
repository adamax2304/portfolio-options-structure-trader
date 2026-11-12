# Standalone Architecture Plan

## Boundary

`options_structure_trader` is an isolated local service. Its runtime, configuration, SQLite database, migrations, source adapters, paper broker, journal, replay jobs, exports, alerts, API, and dashboard live under this project. It does not import from or write to Portfolio OS.

Canonical identity:

```text
service_name = options_structure_trader
strategy_module = options_structure_trader
signal_family = OPTIONS_STRUCTURE
runtime_mode = standalone_paper_validation
```

Live automatic execution is structurally unavailable. The only executable modes are `research_scan`, `shadow_paper`, and `production_paper`; `live_assisted` is a future read-only proposal state.

## Runtime flow

```text
source adapters -> normalized snapshots -> standalone SQLite
                                      -> level engine
                                      -> macro guard
                                      -> reclaim detector
                                      -> deterministic score
                                      -> trade constructor
                                      -> Production/Shadow paper broker
                                      -> journal, reports, replay, exports
                                      -> read-only API and dashboard
```

The scanner persists source and ingestion timestamps, raw payload references, normalized feature snapshots, configuration version, and score-model version. Signal snapshots are immutable inputs to replay.

## Database and migrations

SQLite is the default local store; the repository layer keeps SQL isolated so PostgreSQL can be added without changing strategy logic. `migrations/001_initial.sql` owns the schema. Raw payloads and normalized observations are separate. Production and Shadow trades share a table but are always filtered by `mode`; primary performance excludes Shadow by default.

## Paper broker

The standalone broker supports pending, open, partial, closed, cancelled, and expired lifecycle states. Market simulations fill at next-bar open plus adverse slippage. Conservative limits require trade-through. Same-bar target/stop collisions resolve to the stop. Risk and maximum-position checks occur before acceptance.

## Alerts

Console/GUI notifications are built in. Telegram is an optional standalone adapter using its own environment variables and never the existing alert pipeline. Only Production Paper alerts are enabled by default and every alert states that no real order was placed.

## API and dashboard

FastAPI exposes health, source state, macro guard, ticker maps, setups, paper trades, performance, scanner, replay, and export operations. Static dashboard assets are served by the same local process. The API returns copies of stable objects and never exposes database handles or mutable internal state.

## Explicit non-touch list

This service must not read from, import, mutate, or depend on the existing Master Orchestrator internals, stock-module schema, production paper broker, live signal pipeline, Telegram pipeline, risk/review workflow, post-mortem jobs, or production configurations. The sibling `portfolio-strategy-os` directory is outside this service boundary.

