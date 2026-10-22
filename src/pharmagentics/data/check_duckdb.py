"""Read-only import verification, data-quality evidence, and example KPIs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb

# Support both the documented direct-script invocation and package/module use.
if __package__:
    from .load_duckdb import DEFAULT_DB_PATH, OPTIONAL_COLUMNS, TABLE_KEYS, TABLE_SCHEMAS
else:
    from load_duckdb import DEFAULT_DB_PATH, OPTIONAL_COLUMNS, TABLE_KEYS, TABLE_SCHEMAS


def _records(connection: duckdb.DuckDBPyConnection, query: str) -> list[dict]:
    result = connection.execute(query)
    columns = [column[0] for column in result.description]
    return [dict(zip(columns, row)) for row in result.fetchall()]


def check_database(db_path: Path | str = DEFAULT_DB_PATH) -> dict:
    """Raise on an incomplete import; report intentional artifacts as evidence."""
    db_path = Path(db_path).expanduser().resolve()
    if not db_path.is_file():
        raise FileNotFoundError(f"No database at {db_path}; run load_duckdb.py first")
    with duckdb.connect(str(db_path), read_only=True) as connection:
        latest = connection.execute(
            "SELECT load_id FROM metadata.import_runs WHERE completed_at IS NOT NULL "
            "ORDER BY completed_at DESC, started_at DESC LIMIT 1"
        ).fetchone()
        if latest is None:
            raise ValueError("Database has no completed import")
        manifests = connection.execute(
            "SELECT table_name, row_count, sha256 FROM metadata.import_manifest WHERE load_id = ?",
            [latest[0]],
        ).fetchall()
        if {row[0] for row in manifests} != set(TABLE_SCHEMAS):
            raise ValueError("Latest import manifest does not contain all 14 source tables")
        counts = {}
        source_quality = []
        for table, expected, fingerprint in sorted(manifests):
            actual = connection.execute(f'SELECT count(*) FROM raw."{table}"').fetchone()[0]
            if actual != expected:
                raise ValueError(f"raw.{table}: manifest has {expected} rows, database has {actual}")
            if len(fingerprint) != 64 or any(c not in "0123456789abcdef" for c in fingerprint):
                raise ValueError(f"raw.{table}: invalid SHA-256 fingerprint")
            counts[table] = actual
            required = set(TABLE_SCHEMAS[table]) - OPTIONAL_COLUMNS.get(table, set())
            missing_predicate = " OR ".join(f'"{name}" IS NULL' for name in sorted(required))
            missing_values = connection.execute(
                f'SELECT count(*) FROM raw."{table}" WHERE {missing_predicate}'
            ).fetchone()[0]
            keys = ", ".join(f'"{key}"' for key in TABLE_KEYS[table])
            key_count, excess_rows = connection.execute(
                "SELECT count(*), coalesce(sum(n - 1), 0) FROM ("
                f'SELECT count(*) AS n FROM raw."{table}" GROUP BY {keys} HAVING count(*) > 1)'
            ).fetchone()
            source_quality.append({
                "table_name": table, "empty_table": actual == 0,
                "missing_value_rows": missing_values, "duplicate_key_count": key_count,
                "duplicate_rows": excess_rows,
            })
        duplicates = _records(connection, """
            SELECT * FROM reporting.v_rx_duplicate_keys
            ORDER BY week_start, territory_id, plan_id, hcp_specialty, product_id
        """)
        missing = _records(connection, """
            SELECT * FROM reporting.v_rx_missing_keys
            ORDER BY week_start, territory_id, plan_id, hcp_specialty, product_id
        """)
        flagged = _records(connection, """
            SELECT week_start, territory_id, observed_rows, expected_key_count,
                   missing_key_count, duplicate_key_count, duplicate_rows, flag_reasons
            FROM reporting.v_feed_health WHERE health_status = 'FLAG'
            ORDER BY week_start, territory_id
        """)
        samples = _records(connection, """
            SELECT week_start, territory_id, trx, nrx, nbrx
            FROM reporting.v_weekly_rx_kpis WHERE product_id = 'BXA'
            ORDER BY week_start, territory_id LIMIT 5
        """)
    return {
        "database": str(db_path), "load_id": latest[0], "row_counts": counts,
        "source_quality": source_quality,
        "duplicate_key_count": len(duplicates),
        "duplicate_rows": sum(row["duplicate_rows"] for row in duplicates),
        "missing_key_count": len(missing),
        "duplicate_keys": duplicates, "missing_keys": missing,
        "flagged_feeds": flagged, "example_bxa_kpis": samples,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--json", action="store_true", help="Include every missing and duplicate key")
    parser.add_argument("--fail-on-flags", action="store_true",
                        help="Exit 2 on feed flags or source-table quality issues")
    args = parser.parse_args()
    try:
        report = check_database(args.db_path)
    except (OSError, ValueError, duckdb.Error) as error:
        parser.exit(1, f"Verification failed: {error}\n")
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(f"Verified {len(report['row_counts'])} tables in {report['database']}")
        for table, count in report["row_counts"].items():
            print(f"  raw.{table}: {count:,} rows")
        print(f"Missing Rx keys: {report['missing_key_count']}")
        print(f"Duplicate Rx keys: {report['duplicate_key_count']} "
              f"({report['duplicate_rows']} excess rows)")
        print(f"Flagged feeds: {len(report['flagged_feeds'])}")
        for feed in report["flagged_feeds"]:
            print(f"  {feed['week_start']} / {feed['territory_id']}: {feed['flag_reasons']}")
        print("Source-table quality issues (all 14 tables checked):")
        for table in report["source_quality"]:
            if table["empty_table"] or table["missing_value_rows"] or table["duplicate_key_count"]:
                print(f"  {table['table_name']}: empty={table['empty_table']}, "
                      f"rows with missing required values={table['missing_value_rows']}, "
                      f"duplicate keys={table['duplicate_key_count']}")
        print("Example reportable BXA KPIs:")
        for row in report["example_bxa_kpis"]:
            print(f"  {row['week_start']} / {row['territory_id']}: "
                  f"TRx={row['trx']} NRx={row['nrx']} NBRx={row['nbrx']}")
        print("Use --json for all missing and duplicate keys; raw data remain unchanged.")
    has_source_issues = any(
        table["empty_table"] or table["missing_value_rows"] or table["duplicate_key_count"]
        for table in report["source_quality"]
    )
    if args.fail_on_flags and (report["flagged_feeds"] or has_source_issues):
        parser.exit(2)


if __name__ == "__main__":
    main()
