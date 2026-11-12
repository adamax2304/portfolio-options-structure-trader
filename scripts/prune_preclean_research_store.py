"""Prune invalid pre-clean-forward research rows and build a compact SQLite store.

This is deliberately narrow: it never touches canonical setup events, paper
trades, observations, provider/raw records, or historical datasets.  It only
removes Phase 4 research parents and counterfactual branches created before a
specified clean-forward cutoff.  Those rows were already quarantined from
forward statistics after the instrumentation QA failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


RESEARCH_TABLES = (
    "intraday_options_edge_events",
    "intraday_options_edge_branches",
)
PRESERVED_TABLES = (
    "scan_observations",
    "setup_events",
    "paper_trades",
    "trade_management_branches",
    "options_raw_payloads",
    "options_gex_snapshots",
    "option_levels",
    "market_bars",
    "audit_events",
)
TRANSIENT_TABLES = {
    "real_ablation_results": "created_at_utc",
    "options_raw_payloads": "ingestion_timestamp_utc",
    "options_gex_snapshots": "ingestion_timestamp_utc",
    "option_levels": "known_at_utc",
    "market_bars": "ingestion_timestamp_utc",
    "ticker_states": "ingestion_timestamp_utc",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def count(connection: sqlite3.Connection, table: str) -> int:
    return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remove only pre-clean Phase 4 research rows and compact the DB."
    )
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--cutoff", required=True)
    parser.add_argument("--compact-db", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--confirm-research-purge",
        action="store_true",
        help="Required acknowledgement that pre-cutoff research rows are discarded.",
    )
    parser.add_argument(
        "--purge-transient-before-cutoff",
        action="store_true",
        help=("Also remove stale raw/options/ablation cache rows before the cutoff. "
              "Canonical trades, setups, scans, and historical files remain untouched."),
    )
    args = parser.parse_args()
    if not args.confirm_research_purge:
        raise SystemExit("Refusing to purge without --confirm-research-purge")

    database = args.database.resolve()
    compact_db = args.compact_db.resolve()
    manifest = args.manifest.resolve()
    if not database.exists():
        raise FileNotFoundError(database)
    if compact_db.exists():
        raise FileExistsError(f"Refusing to overwrite compact DB: {compact_db}")
    if database == compact_db:
        raise ValueError("Compact DB must be a different file")

    connection = sqlite3.connect(database, timeout=120)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 120000")
        original_size = database.stat().st_size
        tracked_tables = (*RESEARCH_TABLES, *PRESERVED_TABLES, *TRANSIENT_TABLES)
        before = {table: count(connection, table) for table in tracked_tables}
        candidates = {
            table: int(
                connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE created_at_utc < ?",
                    (args.cutoff,),
                ).fetchone()[0]
            )
            for table in RESEARCH_TABLES
        }
        transient_candidates = {
            table: int(
                connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE {timestamp_column} < ?",
                    (args.cutoff,),
                ).fetchone()[0]
            )
            for table, timestamp_column in TRANSIENT_TABLES.items()
        } if args.purge_transient_before_cutoff else {}

        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "DELETE FROM intraday_options_edge_branches WHERE created_at_utc < ?",
            (args.cutoff,),
        )
        connection.execute(
            "DELETE FROM intraday_options_edge_events WHERE created_at_utc < ?",
            (args.cutoff,),
        )
        if args.purge_transient_before_cutoff:
            for table, timestamp_column in TRANSIENT_TABLES.items():
                connection.execute(
                    f"DELETE FROM {table} WHERE {timestamp_column} < ?",
                    (args.cutoff,),
                )
        connection.commit()
        remaining = {table: count(connection, table) for table in tracked_tables}
        foreign_key_violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_key_violations:
            raise RuntimeError(f"Foreign-key check failed: {foreign_key_violations[:5]}")

        escaped = str(compact_db).replace("'", "''")
        connection.execute(f"VACUUM INTO '{escaped}'")
    finally:
        connection.close()

    compact_connection = sqlite3.connect(compact_db, timeout=120)
    try:
        quick_check = compact_connection.execute("PRAGMA quick_check").fetchone()[0]
        compact_counts = {table: count(compact_connection, table) for table in tracked_tables}
    finally:
        compact_connection.close()
    if quick_check != "ok":
        raise RuntimeError(f"Compact DB quick_check failed: {quick_check}")
    if compact_counts != remaining:
        raise RuntimeError("Compact DB row counts do not match the post-prune source")

    manifest.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "Remove QA/accounting-invalid pre-clean Phase 4 research rows only.",
        "clean_forward_cutoff_utc": args.cutoff,
        "source_database": str(database),
        "source_size_bytes_before": original_size,
        "compact_database": str(compact_db),
        "compact_size_bytes": compact_db.stat().st_size,
        "compact_sha256": sha256(compact_db),
        "research_rows_purged": candidates,
        "transient_cache_rows_purged": transient_candidates,
        "counts_before": before,
        "counts_after": compact_counts,
        "integrity": {"foreign_key_check": "ok", "quick_check": quick_check},
        "preserved": list(PRESERVED_TABLES),
        "transient_cache_scope": TRANSIENT_TABLES if args.purge_transient_before_cutoff else {},
        "canonical_strategy_changed": False,
        "canonical_paper_records_changed": False,
        "live_trading_enabled": False,
    }
    manifest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2), flush=True)


if __name__ == "__main__":
    main()
