from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import Bar, GexMap, Level, PaperTrade, SetupEvent, TickerState, new_id


def _json(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


class Repository:
    # These records are operational caches.  The canonical journal, paper
    # trades, setup records, scan receipts, daily reports, and research branch
    # outcomes deliberately live outside this retention set.
    TRANSIENT_RETENTION_TABLES = {
        "real_ablation_results": "created_at_utc",
        "options_raw_payloads": "ingestion_timestamp_utc",
        "options_gex_snapshots": "ingestion_timestamp_utc",
        "option_levels": "known_at_utc",
        "market_bars": "ingestion_timestamp_utc",
        "ticker_states": "ingestion_timestamp_utc",
    }

    def __init__(self, path: Path, migrations_dir: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.migrations_dir = migrations_dir
        self.migrate()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        return connection

    def _write_with_retry(self, operation, *, attempts: int = 5) -> Any:
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                with self.connect() as connection:
                    return operation(connection)
            except sqlite3.OperationalError as exc:
                last_error = exc
                if "database is locked" not in str(exc).lower() or attempt == attempts - 1:
                    raise
                time.sleep(0.05 * (2 ** attempt))
        if last_error:
            raise last_error
        return None

    def migrate(self) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at_utc TEXT NOT NULL
                )
                """
            )
            for script in sorted(self.migrations_dir.glob("*.sql")):
                if connection.execute(
                    "SELECT 1 FROM schema_migrations WHERE version = ?", (script.stem,)
                ).fetchone():
                    continue
                connection.executescript(script.read_text(encoding="utf-8"))
                connection.execute(
                    "INSERT OR IGNORE INTO schema_migrations(version,applied_at_utc) VALUES (?,?)",
                    (script.stem, datetime.now(timezone.utc).isoformat()),
                )

    def store_raw(self, source: str, ticker: str | None, payload_type: str, payload: Any,
                  source_timestamp: datetime | None = None) -> str:
        raw = _json(payload)
        payload_id = new_id("raw")
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO options_raw_payloads VALUES (?,?,?,?,?,?,?,?)",
                (payload_id, source, ticker, payload_type,
                 source_timestamp.isoformat() if source_timestamp else None,
                 datetime.now(timezone.utc).isoformat(), raw,
                 hashlib.sha256(raw.encode()).hexdigest()),
            )
        return payload_id

    def store_gex(self, value: GexMap, raw_payload_id: str | None = None) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO options_gex_snapshots VALUES (?,?,?,?,?,?,?,?)",
                (new_id("gex"), value.ticker, value.source, value.source_timestamp_utc.isoformat(),
                 value.ingestion_timestamp_utc.isoformat(), value.spot, _json(value), raw_payload_id),
            )

    def store_level(self, value: Level) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO option_levels VALUES (?,?,?,?,?,?,?,?,?,?)",
                (value.level_id, value.ticker, value.level_type, value.price, value.zone_low,
                 value.zone_high, value.known_at_utc.isoformat(), value.source,
                 value.strength_score, _json(value)),
            )

    def store_setup(self, value: SetupEvent) -> None:
        lane = ("production_paper" if value.production_paper_allowed else
                "free_validation_paper" if value.free_validation_paper_allowed else "shadow_paper")
        with self.connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO setup_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (value.setup_event_id, value.ticker, value.setup_type.value, value.side.value,
                 lane,
                 value.created_at_utc.isoformat(), value.score.total, value.score.score_model_version,
                 value.config_version, int(value.production_paper_allowed), _json(value.blocking_reasons), _json(value)),
            )
            connection.execute(
                "INSERT OR REPLACE INTO signal_snapshots VALUES (?,?,?,?,?,?,?)",
                (new_id("snap"), value.setup_event_id, value.created_at_utc.isoformat(),
                 value.signal_snapshot.get("source_timestamp_utc"),
                 value.signal_snapshot.get("ingestion_timestamp_utc"),
                 _json(value.signal_snapshot.get("features", {})), _json(value.signal_snapshot)),
            )
            connection.execute(
                "INSERT INTO score_results VALUES (?,?,?,?,?,?)",
                (new_id("score"), value.setup_event_id, value.score.total, _json(value.score.breakdown),
                 _json(value.score.raw_components), value.score.score_model_version),
            )

    def store_trade(self, value: PaperTrade) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO paper_trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (value.trade_id, value.setup_event_id, value.ticker, value.setup_type, value.side.value,
                 value.mode.value, value.status, value.created_at_utc.isoformat(), value.realized_r,
                 value.score_total, value.score_model_version, value.config_version, _json(value)),
            )

    def store_variant(self, setup_id: str, variant_type: str, variant_value: str, payload: Any,
                      parent_trade_id: str | None = None) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO paper_trade_variants VALUES (?,?,?,?,?,?)",
                (new_id("variant"), parent_trade_id, setup_id, variant_type, variant_value, _json(payload)),
            )

    def list_json(self, table: str, where: str = "", params: tuple[Any, ...] = (), limit: int = 500) -> list[dict[str, Any]]:
        allowed = {"option_levels", "options_gex_snapshots", "setup_events", "paper_trades", "paper_trade_variants", "macro_events", "audit_events",
                   "market_bars", "ticker_states", "scan_observations", "provider_failures", "real_ablation_results",
                   "daily_reports", "trade_management_branches", "edge_candidates", "forward_edge_activation",
                   "forward_edge_memberships", "short_failure_analysis", "phase4a_activation",
                   "intraday_options_edge_events", "intraday_options_edge_branches"}
        if table not in allowed:
            raise ValueError("Table not queryable")
        json_column = "payload_json" if table == "audit_events" else "normalized_json"
        sql = f"SELECT {json_column} FROM {table} {where} ORDER BY rowid DESC LIMIT ?"
        with self.connect() as connection:
            return [json.loads(row[0]) for row in connection.execute(sql, (*params, limit)).fetchall()]

    def get_setup(self, setup_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT normalized_json FROM setup_events WHERE id=?", (setup_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def upsert_macro(self, event_id: str, event_time: str, importance: str, payload: Any) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO macro_events VALUES (?,?,?,?)",
                (event_id, event_time, importance, _json(payload)),
            )

    def counts(self) -> dict[str, int]:
        tables = ["options_raw_payloads", "options_gex_snapshots", "market_bars", "option_levels",
                  "scan_observations", "setup_events", "paper_trades", "provider_failures", "audit_events",
                  "trade_management_branches", "edge_candidates", "forward_edge_activation",
                  "forward_edge_memberships", "short_failure_analysis", "phase4a_activation",
                  "intraday_options_edge_events", "intraday_options_edge_branches"]
        with self.connect() as connection:
            return {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables}

    def observation_counts_between(self, start_utc: str, end_utc: str) -> dict[str, int]:
        """Return dashboard counters without materializing full JSON scan rows.

        The former implementation loaded every normalized observation payload
        into memory for a daily counter.  That is unnecessary and can become a
        daemon reliability risk as a forward sample grows.
        """
        with self.connect() as connection:
            row = connection.execute(
                """SELECT
                       COUNT(*) AS scans_today,
                       COALESCE(SUM(CASE WHEN free_validation_eligible=1 THEN 1 ELSE 0 END), 0) AS free_validation_scans_today,
                       COALESCE(SUM(CASE WHEN lane='shadow_paper' OR
                                             (free_validation_eligible=0 AND production_eligible=0)
                                         THEN 1 ELSE 0 END), 0) AS shadow_scans_today,
                       COALESCE(SUM(CASE WHEN production_eligible=1 THEN 1 ELSE 0 END), 0) AS production_scans_today,
                       COUNT(DISTINCT CASE WHEN free_validation_eligible=1 OR production_eligible=1
                                           THEN ticker END) AS symbols_valid_today,
                       COUNT(DISTINCT CASE WHEN free_validation_eligible=0 AND production_eligible=0
                                           THEN ticker END) AS symbols_blocked_today
                   FROM scan_observations
                   WHERE observed_at_utc>=? AND observed_at_utc<?""",
                (start_utc, end_utc),
            ).fetchone()
            failures = int(connection.execute(
                "SELECT COUNT(*) FROM provider_failures WHERE occurred_at_utc>=? AND occurred_at_utc<?",
                (start_utc, end_utc),
            ).fetchone()[0])
        return {**{key: int(row[key] or 0) for key in row.keys()}, "provider_failures_today": failures}

    def prune_transient_before(self, cutoff_utc: str) -> dict[str, int]:
        """Prune only replaceable market-data/ablation caches before a cutoff.

        It intentionally does not touch canonical trades, setup events, scan
        receipts, research parents/branches, reports, or historical files.
        """
        def operation(connection: sqlite3.Connection) -> dict[str, int]:
            removed: dict[str, int] = {}
            for table, timestamp_column in self.TRANSIENT_RETENTION_TABLES.items():
                cursor = connection.execute(
                    f"DELETE FROM {table} WHERE {timestamp_column} < ?", (cutoff_utc,)
                )
                removed[table] = int(cursor.rowcount)
            return removed

        return self._write_with_retry(operation)

    def store_audit(self, event_type: str, outcome: str, reasons: list[str], payload: Any,
                    ticker: str | None = None, severity: str = "INFO") -> str:
        event_id = new_id("audit")
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO audit_events VALUES (?,?,?,?,?,?,?,?)",
                (event_id, event_type, datetime.now(timezone.utc).isoformat(), severity,
                 ticker, outcome, _json(reasons), _json({"event_id": event_id, "event_type": event_type,
                 "outcome": outcome, "ticker": ticker, "severity": severity, "reasons": reasons,
                 "payload": payload, "timestamp_utc": datetime.now(timezone.utc).isoformat()})),
            )
        return event_id

    def store_bar(self, value: Bar, raw_payload_id: str | None = None) -> None:
        source_time = value.source_timestamp_utc or value.bar_end_utc
        with self.connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO market_bars VALUES (?,?,?,?,?,?,?,?)",
                (new_id("bar"), value.ticker, value.timeframe, value.source, source_time.isoformat(),
                 value.ingestion_timestamp_utc.isoformat(), raw_payload_id or value.raw_payload_reference, _json(value)),
            )

    def store_ticker_state(self, value: TickerState, raw_payload_id: str | None = None) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO ticker_states VALUES (?,?,?,?,?,?,?)",
                (new_id("state"), value.ticker, value.source, value.timestamp_utc.isoformat(),
                 value.ingestion_timestamp_utc.isoformat(), raw_payload_id or value.raw_payload_reference, _json(value)),
            )

    def levels_before(self, ticker: str, cutoff_utc: datetime, limit: int = 1000) -> list[dict[str, Any]]:
        return self.list_json("option_levels", "WHERE ticker=? AND known_at_utc<?",
                              (ticker.upper(), cutoff_utc.isoformat()), limit)

    def store_observation(self, run_id: str, ticker: str, data_mode: str, outcome: str,
                          production_eligible: bool, reasons: list[str], providers: dict[str, Any],
                          payload: dict[str, Any], setup_event_id: str | None = None,
                          score_total: float | None = None, *, free_validation_eligible: bool = False,
                          lane: str = "shadow_paper", candle_end_utc: datetime | None = None,
                          data_quality: dict[str, Any] | None = None) -> str:
        observation_id = new_id("obs")
        observed = datetime.now(timezone.utc).isoformat()
        record = {"observation_id": observation_id, "run_id": run_id, "ticker": ticker,
                  "observed_at_utc": observed, "data_mode": data_mode, "outcome": outcome,
                  "production_eligible": production_eligible, "setup_event_id": setup_event_id,
                  "free_validation_eligible": free_validation_eligible, "lane": lane,
                  "candle_end_utc": candle_end_utc.isoformat() if candle_end_utc else None,
                  "reasons": reasons, "providers": providers, "score_total": score_total,
                  "data_quality": data_quality or {}, "payload": payload}
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO scan_observations
                   (id,run_id,ticker,observed_at_utc,data_mode,outcome,production_eligible,setup_event_id,
                    reasons_json,providers_json,score_total,normalized_json,free_validation_eligible,lane,
                    candle_end_utc,data_quality_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (observation_id, run_id, ticker, observed, data_mode, outcome, int(production_eligible),
                 setup_event_id, _json(reasons), _json(providers), score_total, _json(record),
                 int(free_validation_eligible), lane, record["candle_end_utc"], _json(data_quality or {})),
            )
        return observation_id

    def store_provider_failure(self, provider: str, error: Exception | str, *, run_id: str | None = None,
                               ticker: str | None = None, retryable: bool = True) -> str:
        failure_id = new_id("failure")
        occurred = datetime.now(timezone.utc).isoformat()
        error_type = error.__class__.__name__ if isinstance(error, Exception) else "ProviderError"
        message = str(error)
        record = {"failure_id": failure_id, "run_id": run_id, "ticker": ticker, "provider": provider,
                  "occurred_at_utc": occurred, "error_type": error_type, "error_message": message,
                  "retryable": retryable}
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO provider_failures VALUES (?,?,?,?,?,?,?,?,?)",
                (failure_id, run_id, ticker, provider, occurred, error_type, message, int(retryable), _json(record)),
            )
        return failure_id

    def store_ablation(self, run_id: str, observation_id: str, ticker: str, model_name: str,
                       payload: dict[str, Any], score_total: float | None = None,
                       variant_type: str | None = None, variant_value: str | None = None) -> None:
        record = {"run_id": run_id, "observation_id": observation_id, "ticker": ticker,
                  "created_at_utc": datetime.now(timezone.utc).isoformat(), "model_name": model_name,
                  "score_total": score_total, "variant_type": variant_type, "variant_value": variant_value,
                  "payload": payload}
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO real_ablation_results VALUES (?,?,?,?,?,?,?,?,?,?)",
                (new_id("ablation"), run_id, observation_id, ticker, record["created_at_utc"],
                 model_name, score_total, variant_type, variant_value, _json(record)),
            )

    def store_daily_report(self, report_date: str, report_path: str, payload: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO daily_reports VALUES (?,?,?,?,?)",
                (new_id("report"), report_date, datetime.now(timezone.utc).isoformat(), report_path, _json(payload)),
            )

    def store_trade_management_branch(self, value: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        value.setdefault("updated_at_utc", now)
        with self.connect() as connection:
            connection.execute(
                """INSERT OR REPLACE INTO trade_management_branches
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (value["branch_id"], value["parent_setup_id"], value["branch"],
                 value["management_version"], value["ticker"], value["status"],
                 value["created_at_utc"], value["updated_at_utc"], _json(value)),
            )

    def store_edge_candidate(self, value: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute(
                """INSERT OR REPLACE INTO edge_candidates
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (value["edge_id"], value["description"], value["discovered_at"],
                 int(value["sample_n"]), float(value["expectancy"]), str(value["PF"]),
                 value.get("MFE"), value.get("MAE"), _json(value.get("bootstrap_CI", {})),
                 _json(value.get("discovery_result", {})), _json(value.get("holdout_result", {})),
                 value["status"], _json(value)),
            )

    def store_forward_edge_activation(self, value: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute(
                """INSERT OR REPLACE INTO forward_edge_activation
                   VALUES (?,?,?,?)""",
                (value["id"], value["activated_at_utc"], value["discovery_cutoff_utc"], _json(value)),
            )

    def store_forward_edge_membership(self, value: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute(
                """INSERT OR REPLACE INTO forward_edge_memberships
                   VALUES (?,?,?,?,?,?,?,?)""",
                (value["id"], value["parent_setup_id"], value["cohort"], value["management_version"],
                 value["ticker"], value["side"], value["created_at_utc"], _json(value)),
            )

    def store_short_failure_analysis(self, value: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute(
                """INSERT OR REPLACE INTO short_failure_analysis
                   VALUES (?,?,?,?,?)""",
                (value["id"], value["parent_setup_id"], value["ticker"], value["created_at_utc"], _json(value)),
            )

    def store_phase4a_activation(self, value: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute(
                """INSERT OR REPLACE INTO phase4a_activation
                   VALUES (?,?,?,?)""",
                (value["id"], value["activated_at_utc"], value["discovery_cutoff_utc"], _json(value)),
            )

    def store_intraday_edge_event(self, value: dict[str, Any]) -> None:
        def op(connection: sqlite3.Connection) -> None:
            connection.execute(
                """INSERT OR REPLACE INTO intraday_options_edge_events
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (value["id"], value["parent_event_id"], value["ticker"], value["trade_date"],
                 value["created_at_utc"], value["level_cluster_id"], value["direction"],
                 value["structural_family"], value["level_tier"], value["level_type"],
                 value["interaction_episode"], value.get("source_setup_id"),
                 value.get("source_observation_id"), _json(value)),
            )
        self._write_with_retry(op)

    def store_intraday_edge_branch(self, value: dict[str, Any]) -> None:
        def op(connection: sqlite3.Connection) -> None:
            connection.execute(
                """INSERT OR REPLACE INTO intraday_options_edge_branches
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (value["id"], value["parent_event_id"], value["strategy_variant"],
                 value["timeframe_context"], value["confirmation_tf"], value["execution_tf"],
                 value["entry_variant"], value["management_variant"], value["stop_variant"],
                 value["ticker"], value["status"], value["created_at_utc"], value["updated_at_utc"],
                 value.get("result_R"), value.get("MFE"), value.get("MAE"),
                 value.get("holding_time_minutes"), value.get("exit_reason"), _json(value)),
            )
        self._write_with_retry(op)

    def store_intraday_edge_branches(self, values: list[dict[str, Any]]) -> None:
        if not values:
            return

        def row(value: dict[str, Any]) -> tuple[Any, ...]:
            return (
                value["id"], value["parent_event_id"], value["strategy_variant"],
                value["timeframe_context"], value["confirmation_tf"], value["execution_tf"],
                value["entry_variant"], value["management_variant"], value["stop_variant"],
                value["ticker"], value["status"], value["created_at_utc"], value["updated_at_utc"],
                value.get("result_R"), value.get("MFE"), value.get("MAE"),
                value.get("holding_time_minutes"), value.get("exit_reason"), _json(value),
            )

        def op(connection: sqlite3.Connection) -> None:
            connection.executemany(
                """INSERT OR REPLACE INTO intraday_options_edge_branches
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [row(value) for value in values],
            )
        self._write_with_retry(op)
