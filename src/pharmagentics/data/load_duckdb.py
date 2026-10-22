"""Load the fourteen agent-visible CSVs without cleaning feed artifacts."""

from __future__ import annotations

import argparse
import csv
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import duckdb

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA_DIR = ROOT / "data" / "agent_visible"
DEFAULT_DB_PATH = ROOT / "local" / "pharmagentics.duckdb"
REPORTING_SQL = ROOT / "sql" / "001_reporting_views.sql"

# Explicit types prevent inference changes between releases (including all-null
# columns). Dates are typed except launch_date, which also has BEFORE_* sentinels.
TABLE_SCHEMAS = {
    "rx_weekly": {
        "week_start": "DATE", "territory_id": "VARCHAR", "region": "VARCHAR",
        "plan_id": "VARCHAR", "payer_channel": "VARCHAR", "hcp_specialty": "VARCHAR",
        "product_id": "VARCHAR", "trx": "BIGINT", "nrx": "BIGINT", "nbrx": "BIGINT",
        "trx_30day_equivalent": "DOUBLE", "share_90day_fills_proxy": "DOUBLE",
        "source": "VARCHAR",
    },
    "dim_product": {
        "product_id": "VARCHAR", "product_name": "VARCHAR", "role": "VARCHAR",
        "fictional_product": "BOOLEAN", "therapeutic_area": "VARCHAR",
        "dosage_form": "VARCHAR", "route": "VARCHAR", "product_ndc": "VARCHAR",
    },
    "dim_plan": {
        "plan_id": "VARCHAR", "territory_id": "VARCHAR", "region": "VARCHAR",
        "payer_channel": "VARCHAR", "plan_weight": "DOUBLE",
        "covered_lives_weight": "DOUBLE", "is_synthetic": "BOOLEAN",
    },
    "dim_territory": {
        "territory_id": "VARCHAR", "region": "VARCHAR", "population_weight": "DOUBLE",
    },
    "dim_specialty": {"hcp_specialty": "VARCHAR", "specialty_weight": "DOUBLE"},
    "market_basket": {
        "product_id": "VARCHAR", "effective_start": "DATE", "effective_end": "DATE",
        "in_basket_flag": "BOOLEAN", "market_id": "VARCHAR", "launch_date": "VARCHAR",
    },
    "access_status_monthly": {
        "month": "DATE", "plan_id": "VARCHAR", "territory_id": "VARCHAR",
        "payer_channel": "VARCHAR", "product_id": "VARCHAR", "covered": "BIGINT",
        "formulary_tier": "BIGINT", "prior_authorization": "BIGINT",
        "step_therapy": "BIGINT", "quantity_limit": "BIGINT",
        "covered_lives_weight": "DOUBLE",
    },
    "promo_activity": {
        "week_start": "DATE", "territory_id": "VARCHAR", "product_id": "VARCHAR",
        "rep_calls_aggregated": "BIGINT", "digital_impressions": "BIGINT",
        "samples_units": "BIGINT", "speaker_programs": "BIGINT",
        "rep_vacancy_count_aggregated": "BIGINT",
    },
    "inventory_weekly": {
        "week_start": "DATE", "territory_id": "VARCHAR", "product_id": "VARCHAR",
        "inventory_fill_rate": "DOUBLE", "distribution_backorder_rate": "DOUBLE",
    },
    "calendar": {
        "week_start": "DATE", "holiday_flag": "BIGINT", "holiday_name": "VARCHAR",
        "business_days": "BIGINT", "plan_year_reset": "BIGINT", "week_end": "DATE",
    },
    "feed_metadata": {
        "week_start": "DATE", "territory_id": "VARCHAR", "expected_rows": "BIGINT",
        "received_rows": "BIGINT", "row_count_delta": "BIGINT",
        "panel_coverage_ratio": "DOUBLE", "loaded_at_utc": "TIMESTAMPTZ",
        "expected_lag_days": "BIGINT", "actual_lag_days": "DOUBLE",
        "schema_version": "VARCHAR", "source": "VARCHAR", "restatement_flag": "BIGINT",
        "restatement_recorded_at": "DATE", "status": "VARCHAR",
    },
    "restatement_log": {
        "week_start": "DATE", "territory_id": "VARCHAR", "plan_id": "VARCHAR",
        "hcp_specialty": "VARCHAR", "product_id": "VARCHAR", "trx_revised": "BIGINT",
        "nrx_revised": "BIGINT", "nbrx_revised": "BIGINT", "trx_prior": "BIGINT",
        "nrx_prior": "BIGINT", "nbrx_prior": "BIGINT", "revised_at": "DATE",
        "revision_reason": "VARCHAR",
    },
    "market_share_weekly": {
        "week_start": "DATE", "territory_id": "VARCHAR", "product_id": "VARCHAR",
        "trx": "BIGINT", "nrx": "BIGINT", "nbrx": "BIGINT", "market_trx": "BIGINT",
        "market_share": "DOUBLE", "data_quality_status": "VARCHAR",
    },
    "forecast_vs_actual_weekly": {
        "forecast_issue_week": "DATE", "week_start": "DATE", "territory_id": "VARCHAR",
        "product_id": "VARCHAR", "forecast_trx": "BIGINT", "actual_trx": "BIGINT",
        "variance_trx": "BIGINT", "variance_pct": "DOUBLE",
        "actual_is_provisional": "BIGINT", "horizon_weeks": "BIGINT",
    },
}

# Natural grains for diagnostics across every source, not just the Rx table.
TABLE_KEYS = {
    "rx_weekly": ("week_start", "territory_id", "plan_id", "hcp_specialty", "product_id"),
    "dim_product": ("product_id",),
    "dim_plan": ("plan_id",),
    "dim_territory": ("territory_id",),
    "dim_specialty": ("hcp_specialty",),
    "market_basket": ("market_id", "product_id", "effective_start"),
    "access_status_monthly": ("month", "plan_id", "product_id"),
    "promo_activity": ("week_start", "territory_id", "product_id"),
    "inventory_weekly": ("week_start", "territory_id", "product_id"),
    "calendar": ("week_start",),
    "feed_metadata": ("week_start", "territory_id"),
    "restatement_log": (
        "week_start", "territory_id", "plan_id", "hcp_specialty", "product_id", "revised_at",
    ),
    "market_share_weekly": ("week_start", "territory_id", "product_id"),
    "forecast_vs_actual_weekly": (
        "forecast_issue_week", "week_start", "territory_id", "product_id", "horizon_weeks",
    ),
}
OPTIONAL_COLUMNS = {"feed_metadata": {"restatement_recorded_at"}}


def file_sha256(path: Path) -> str:
    """Fingerprint the exact source bytes, including line endings."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_database(
    data_dir: Path | str = DEFAULT_DATA_DIR,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> dict[str, int]:
    """Atomically replace source tables and views; retain successful import history.

    Only the fixed allowlist is read, never an arbitrary directory glob. Missing
    files, schema errors, or failed SQL leave the previous database load intact.
    Duplicate rows and NULLs are retained; restatements are not applied.
    """
    data_dir = Path(data_dir).expanduser().resolve()
    db_path = Path(db_path).expanduser().resolve()
    sql = REPORTING_SQL.read_text(encoding="utf-8")
    for table, columns in TABLE_SCHEMAS.items():
        source = data_dir / f"{table}.csv"
        with source.open(encoding="utf-8-sig", newline="") as stream:
            header = next(csv.reader(stream), [])
        if header != list(columns):
            raise ValueError(f"{source.name}: expected header {list(columns)}, got {header}")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    load_id = str(uuid4())
    counts = {}
    with duckdb.connect(str(db_path)) as connection:
        connection.execute("BEGIN TRANSACTION")
        try:
            connection.execute("CREATE SCHEMA IF NOT EXISTS raw")
            connection.execute("CREATE SCHEMA IF NOT EXISTS metadata")
            connection.execute("CREATE SCHEMA IF NOT EXISTS reporting")
            connection.execute("""
                CREATE TABLE IF NOT EXISTS metadata.import_runs (
                    load_id VARCHAR PRIMARY KEY,
                    started_at TIMESTAMPTZ NOT NULL,
                    completed_at TIMESTAMPTZ,
                    source_directory VARCHAR NOT NULL
                );
                CREATE TABLE IF NOT EXISTS metadata.import_manifest (
                    load_id VARCHAR NOT NULL REFERENCES metadata.import_runs(load_id),
                    table_name VARCHAR NOT NULL,
                    source_file VARCHAR NOT NULL,
                    sha256 VARCHAR NOT NULL,
                    source_bytes BIGINT NOT NULL,
                    row_count BIGINT NOT NULL,
                    PRIMARY KEY (load_id, table_name)
                );
            """)
            connection.execute(
                "INSERT INTO metadata.import_runs VALUES (?, current_timestamp, NULL, ?)",
                [load_id, str(data_dir)],
            )
            for table, columns in TABLE_SCHEMAS.items():
                source = data_dir / f"{table}.csv"
                fingerprint = file_sha256(source)
                connection.execute(
                    f'CREATE OR REPLACE TABLE raw."{table}" AS '
                    "SELECT * FROM read_csv(?, columns = ?, header = true, "
                    "auto_detect = false, strict_mode = true, null_padding = false, "
                    "dateformat = '%Y-%m-%d')",
                    [str(source), columns],
                )
                if file_sha256(source) != fingerprint:
                    raise ValueError(f"Source changed during import: {source.name}")
                count = connection.execute(f'SELECT count(*) FROM raw."{table}"').fetchone()[0]
                counts[table] = count
                connection.execute(
                    "INSERT INTO metadata.import_manifest VALUES (?, ?, ?, ?, ?, ?)",
                    [load_id, table, source.name, fingerprint, source.stat().st_size, count],
                )
            connection.execute(sql)
            connection.execute(
                "UPDATE metadata.import_runs SET completed_at = ? WHERE load_id = ?",
                [datetime.now(timezone.utc), load_id],
            )
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    args = parser.parse_args()
    try:
        counts = load_database(args.data_dir, args.db_path)
    except (OSError, ValueError, duckdb.Error) as error:
        parser.exit(1, f"Import failed: {error}\n")
    for table, count in counts.items():
        print(f"raw.{table}: {count:,} rows")
    print(f"Loaded {len(counts)} tables into {args.db_path.resolve()}")


if __name__ == "__main__":
    main()
