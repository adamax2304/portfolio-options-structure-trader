from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def archive_scan_rows(connection: sqlite3.Connection, archive_path: Path) -> int:
    if archive_path.exists():
        raise FileExistsError(f"Refusing to overwrite archive: {archive_path}")
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    schema = pa.schema([("id", pa.string()), ("normalized_json", pa.string())])
    writer = pq.ParquetWriter(archive_path, schema, compression="zstd")
    count = 0
    try:
        cursor = connection.execute(
            "SELECT id, normalized_json FROM scan_observations ORDER BY rowid"
        )
        while True:
            rows = cursor.fetchmany(250)
            if not rows:
                break
            writer.write_table(pa.Table.from_pylist([
                {"id": row["id"], "normalized_json": row["normalized_json"]}
                for row in rows
            ], schema=schema))
            count += len(rows)
            if count % 1000 == 0:
                print(f"archived_scan_rows={count}", flush=True)
    finally:
        writer.close()
    return count


def compact_monitoring_payload(payload: object, archive_relative_path: str) -> tuple[object, bool]:
    if not isinstance(payload, dict) or "monitored_trades" not in payload:
        return payload, False
    legacy = payload.pop("monitored_trades")
    statuses: Counter[str] = Counter()
    kinds: Counter[str] = Counter()
    ids: list[str] = []
    if isinstance(legacy, list):
        for item in legacy:
            if not isinstance(item, dict):
                continue
            statuses[str(item.get("status") or "UNKNOWN")] += 1
            kinds[str(item.get("phase4b2_experiment_id") or item.get("management_version") or "canonical")] += 1
            identifier = item.get("id") or item.get("branch_id") or item.get("trade_id")
            if identifier and len(ids) < 10:
                ids.append(str(identifier))
    payload["monitoring_summary"] = {
        "legacy_embedded_update_count": len(legacy) if isinstance(legacy, list) else 0,
        "status_counts": dict(statuses),
        "kind_counts": dict(kinds),
        "record_ids_sample": ids,
        "full_payload_archived": True,
        "archive_path": archive_relative_path,
        "payload_version": "legacy_monitoring_receipt_compacted_v1",
    }
    return payload, True


def strip_repeated_monitoring_payloads(
    connection: sqlite3.Connection,
    archive_relative_path: str,
) -> int:
    connection.execute("PRAGMA wal_autocheckpoint=500")
    updated = 0
    last_rowid = 0
    while True:
        rows = connection.execute(
            """SELECT rowid, id, normalized_json FROM scan_observations
               WHERE rowid>? AND normalized_json LIKE '%\"monitored_trades\"%'
               ORDER BY rowid LIMIT 100""",
            (last_rowid,),
        ).fetchall()
        if not rows:
            break
        last_rowid = int(rows[-1]["rowid"])
        changes = []
        for row in rows:
            record = json.loads(row["normalized_json"])
            compacted, changed = compact_monitoring_payload(
                record.get("payload"), archive_relative_path
            )
            if not changed:
                continue
            record["payload"] = compacted
            record["storage_compaction"] = {
                "version": "scan_payload_compaction_v1",
                "compacted_at_utc": datetime.now(timezone.utc).isoformat(),
                "full_payload_archive": archive_relative_path,
            }
            changes.append((
                json.dumps(record, sort_keys=True, separators=(",", ":"), default=str),
                row["id"],
            ))
        connection.executemany(
            "UPDATE scan_observations SET normalized_json=? WHERE id=?", changes
        )
        connection.commit()
        updated += len(changes)
        print(f"compacted_scan_rows={updated}", flush=True)
    connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    return updated


def vacuum_into(connection: sqlite3.Connection, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite compact DB: {destination}")
    escaped = str(destination.resolve()).replace("'", "''")
    connection.execute(f"VACUUM INTO '{escaped}'")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Archive repeated scan payloads and build a compact SQLite copy."
    )
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--compact-db", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()

    database = args.database.resolve()
    root = Path.cwd().resolve()
    for path in (database, args.archive.resolve(), args.compact_db.resolve(), args.manifest.resolve()):
        if root not in path.parents and path != root:
            raise ValueError(f"Path is outside project root: {path}")

    connection = sqlite3.connect(database, timeout=120)
    connection.row_factory = sqlite3.Row
    try:
        archived = archive_scan_rows(connection, args.archive.resolve())
        archive_hash = sha256(args.archive.resolve())
        compacted = strip_repeated_monitoring_payloads(
            connection,
            str(args.archive.resolve().relative_to(root)),
        )
        quick_check = connection.execute("PRAGMA quick_check").fetchone()[0]
        if quick_check != "ok":
            raise RuntimeError(f"Source DB quick_check failed: {quick_check}")
        vacuum_into(connection, args.compact_db.resolve())
    finally:
        connection.close()

    compact_connection = sqlite3.connect(args.compact_db.resolve(), timeout=120)
    try:
        compact_check = compact_connection.execute("PRAGMA quick_check").fetchone()[0]
        counts = {
            table: compact_connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "scan_observations",
                "setup_events",
                "paper_trades",
                "intraday_options_edge_events",
                "intraday_options_edge_branches",
            )
        }
    finally:
        compact_connection.close()
    if compact_check != "ok":
        raise RuntimeError(f"Compact DB quick_check failed: {compact_check}")

    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_database": str(database.relative_to(root)),
        "full_scan_payload_archive": str(args.archive.resolve().relative_to(root)),
        "archive_sha256": archive_hash,
        "archive_rows": archived,
        "scan_rows_compacted": compacted,
        "compact_database": str(args.compact_db.resolve().relative_to(root)),
        "compact_database_sha256": sha256(args.compact_db.resolve()),
        "source_quick_check": "ok",
        "compact_quick_check": compact_check,
        "row_counts": counts,
        "canonical_strategy_changed": False,
        "canonical_paper_records_changed": False,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2), flush=True)


if __name__ == "__main__":
    main()
