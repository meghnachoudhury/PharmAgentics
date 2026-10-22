"""Integration tests using the real synthetic release and isolated databases."""

import csv
import itertools
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections import Counter, defaultdict
from pathlib import Path
from unittest.mock import patch

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pharmagentics.data import load_duckdb  # noqa: E402
from pharmagentics.data.check_duckdb import check_database  # noqa: E402

DATA = ROOT / "data" / "agent_visible"
RX_KEYS = ("week_start", "territory_id", "plan_id", "hcp_specialty", "product_id")
CLEAN_CUT = "week_start = DATE '2024-10-14' AND territory_id = 'GREAT_LAKES'"


def read_csv(table):
    with (DATA / f"{table}.csv").open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


class DataLoadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = tempfile.TemporaryDirectory(prefix="pharmagentics-tests-")
        cls.addClassCleanup(cls.workspace.cleanup)
        cls.baseline = Path(cls.workspace.name) / "baseline.duckdb"
        load_duckdb.load_database(DATA, cls.baseline)
        cls.release = json.loads((DATA / "DATA_VALIDATION_REPORT.json").read_text())
        cls.csv_rx = read_csv("rx_weekly")

    def setUp(self):
        self.sandbox = tempfile.TemporaryDirectory(dir=self.workspace.name)
        self.addCleanup(self.sandbox.cleanup)
        self.db_path = Path(self.sandbox.name) / "test.duckdb"
        shutil.copyfile(self.baseline, self.db_path)

    def copied_sources(self):
        return Path(shutil.copytree(DATA, Path(self.sandbox.name) / "source's CSVs"))

    def health(self, connection):
        return connection.execute(
            f"SELECT health_status, flag_reasons FROM reporting.v_feed_health WHERE {CLEAN_CUT}"
        ).fetchone()

    def assert_cut_withheld(self, connection):
        self.assertEqual(connection.execute(
            f"SELECT count(*) FROM reporting.v_weekly_rx_kpis WHERE {CLEAN_CUT}"
        ).fetchone()[0], 0)

    def test_all_fourteen_tables_and_manifest_match_the_supplied_release(self):
        report = check_database(self.db_path)
        self.assertEqual(report["row_counts"], self.release["public_table_rows"])
        self.assertEqual(len(report["source_quality"]), 14)
        with duckdb.connect(str(self.db_path), read_only=True) as connection:
            manifest = connection.execute(
                "SELECT table_name, source_file, sha256, source_bytes FROM metadata.import_manifest"
            ).fetchall()
            self.assertEqual(len(manifest), 14)
            for table, filename, fingerprint, size in manifest:
                self.assertEqual(filename, f"{table}.csv")
                self.assertEqual(fingerprint, load_duckdb.file_sha256(DATA / filename))
                self.assertEqual(size, (DATA / filename).stat().st_size)
            self.assertEqual(connection.execute(
                "SELECT count(*) FROM metadata.import_runs WHERE completed_at >= started_at"
            ).fetchone()[0], 1)
            types = dict(connection.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = 'raw' AND table_name = 'rx_weekly'"
            ).fetchall())
            self.assertEqual(types["week_start"], "DATE")
            self.assertEqual(types["trx"], "BIGINT")

    def test_missing_and_duplicate_keys_match_an_independent_csv_calculation(self):
        observed = Counter(tuple(row[key] for key in RX_KEYS) for row in self.csv_rx)
        expected = {
            (week["week_start"], plan["territory_id"], plan["plan_id"],
             specialty["hcp_specialty"], product["product_id"])
            for week, plan, specialty, product in itertools.product(
                read_csv("calendar"), read_csv("dim_plan"),
                read_csv("dim_specialty"), read_csv("dim_product"),
            )
        }
        report = check_database(self.db_path)
        missing = {tuple(str(row[key]) for key in RX_KEYS) for row in report["missing_keys"]}
        duplicates = {
            tuple(str(row[key]) for key in RX_KEYS): row["record_count"]
            for row in report["duplicate_keys"]
        }
        self.assertEqual(missing, expected - observed.keys())
        self.assertEqual(duplicates, {key: n for key, n in observed.items() if n > 1})
        self.assertEqual(report["missing_key_count"], 44)
        self.assertEqual(report["duplicate_key_count"], 15)
        self.assertEqual(report["duplicate_rows"], 15)
        self.assertEqual(len(self.csv_rx), 106467)

    def test_known_artifacts_and_restatement_are_flagged(self):
        report = check_database(self.db_path)
        flags = {
            (str(row["week_start"]), row["territory_id"]): row["flag_reasons"]
            for row in report["flagged_feeds"]
        }
        self.assertEqual(set(flags), {
            ("2026-05-04", "NEW_ENGLAND"),
            ("2026-07-06", "GREAT_LAKES"),
            ("2026-04-06", "MID_ATLANTIC"),
        })
        self.assertIn("MISSING_RX_KEYS", flags[("2026-05-04", "NEW_ENGLAND")])
        self.assertIn("DUPLICATE_RX_KEYS", flags[("2026-07-06", "GREAT_LAKES")])
        self.assertIn("RESTATEMENT_REVIEW", flags[("2026-04-06", "MID_ATLANTIC")])

    def test_reportable_kpis_reconcile_to_independent_csv_sums(self):
        excluded = {
            ("2026-05-04", "NEW_ENGLAND"), ("2026-07-06", "GREAT_LAKES"),
            ("2026-04-06", "MID_ATLANTIC"),
        }
        totals = defaultdict(lambda: [0, 0, 0])
        for row in self.csv_rx:
            if (row["week_start"], row["territory_id"]) in excluded:
                continue
            key = (row["week_start"], row["territory_id"], row["product_id"])
            for index, metric in enumerate(("trx", "nrx", "nbrx")):
                totals[key][index] += int(row[metric])
        with duckdb.connect(str(self.db_path), read_only=True) as connection:
            actual = connection.execute(
                "SELECT week_start, territory_id, product_id, trx, nrx, nbrx "
                "FROM reporting.v_weekly_rx_kpis"
            ).fetchall()
            self.assertEqual(len(actual), (832 - 3) * 4)
            self.assertEqual({(str(w), t, p): [trx, nrx, nbrx]
                              for w, t, p, trx, nrx, nbrx in actual}, dict(totals))
            self.assertEqual(connection.execute(
                "SELECT count(*) FROM reporting.v_reportable_rx r "
                "JOIN reporting.v_feed_health h USING (week_start, territory_id) "
                "WHERE h.health_status = 'FLAG'"
            ).fetchone()[0], 0)

    def test_reimport_is_idempotent_and_retains_audit_history(self):
        before = check_database(self.db_path)
        load_duckdb.load_database(DATA, self.db_path)
        after = check_database(self.db_path)
        self.assertNotEqual(before["load_id"], after["load_id"])
        for key in ("row_counts", "flagged_feeds", "missing_keys", "duplicate_keys"):
            self.assertEqual(before[key], after[key])
        with duckdb.connect(str(self.db_path), read_only=True) as connection:
            self.assertEqual(connection.execute(
                "SELECT count(*) FROM metadata.import_runs"
            ).fetchone()[0], 2)
            self.assertEqual(connection.execute(
                "SELECT count(*) FROM metadata.import_manifest"
            ).fetchone()[0], 28)

    def test_missing_file_fails_without_replacing_the_database(self):
        sources = self.copied_sources()
        (sources / "inventory_weekly.csv").unlink()
        before = check_database(self.db_path)
        with self.assertRaises(FileNotFoundError):
            load_duckdb.load_database(sources, self.db_path)
        self.assertEqual(check_database(self.db_path), before)

    def test_bad_header_fails_explicitly(self):
        sources = self.copied_sources()
        (sources / "dim_specialty.csv").write_text("hcp_specialty\nCARDIOLOGY\n")
        with self.assertRaisesRegex(ValueError, "dim_specialty.csv: expected header"):
            load_duckdb.load_database(sources, self.db_path)

    def test_empty_source_table_is_preserved_and_reported(self):
        sources = self.copied_sources()
        inventory = sources / "inventory_weekly.csv"
        inventory.write_text(inventory.read_text().splitlines()[0] + "\n")
        load_duckdb.load_database(sources, self.db_path)
        report = check_database(self.db_path)
        self.assertEqual(report["row_counts"]["inventory_weekly"], 0)
        quality = {row["table_name"]: row for row in report["source_quality"]}
        self.assertTrue(quality["inventory_weekly"]["empty_table"])

    def test_missing_csv_metric_is_loaded_as_null_and_reported(self):
        sources = self.copied_sources()
        rx_path = sources / "rx_weekly.csv"
        rows = rx_path.read_text().splitlines(keepends=True)
        cells = rows[1].rstrip("\r\n").split(",")
        cells[7] = ""  # First source row's TRx value, not a missing key.
        rows[1] = ",".join(cells) + "\n"
        rx_path.write_text("".join(rows))
        load_duckdb.load_database(sources, self.db_path)
        report = check_database(self.db_path)
        self.assertEqual(report["row_counts"]["rx_weekly"], 106467)
        quality = {row["table_name"]: row for row in report["source_quality"]}
        self.assertEqual(quality["rx_weekly"]["missing_value_rows"], 1)
        with duckdb.connect(str(self.db_path), read_only=True) as connection:
            self.assertEqual(connection.execute(
                "SELECT count(*) FROM raw.rx_weekly WHERE trx IS NULL"
            ).fetchone()[0], 1)
            self.assertIn("INVALID_RX_METRICS", self.health(connection)[1])
            self.assert_cut_withheld(connection)

    def test_type_error_rolls_back_tables_and_manifest(self):
        sources = self.copied_sources()
        # An earlier table would change, but a later table fails conversion.
        rx_path = sources / "rx_weekly.csv"
        rx_path.write_text(rx_path.read_text().replace(
            "SYNTHETIC_RX_PANEL", "CHANGED_SOURCE", 1))
        inventory = sources / "inventory_weekly.csv"
        inventory.write_text(inventory.read_text().replace(
            ",BXA,1.0,", ",BXA,not_a_number,", 1))
        before = check_database(self.db_path)
        with self.assertRaises(duckdb.Error):
            load_duckdb.load_database(sources, self.db_path)
        self.assertEqual(check_database(self.db_path), before)
        with duckdb.connect(str(self.db_path), read_only=True) as connection:
            self.assertEqual(connection.execute(
                "SELECT count(*) FROM raw.rx_weekly WHERE source = 'CHANGED_SOURCE'"
            ).fetchone()[0], 0)

    def test_view_failure_rolls_back_the_import(self):
        bad_sql = Path(self.sandbox.name) / "broken.sql"
        bad_sql.write_text("SELECT * FROM nonexistent_setup_table;")
        before = check_database(self.db_path)
        with patch.object(load_duckdb, "REPORTING_SQL", bad_sql):
            with self.assertRaises(duckdb.Error):
                load_duckdb.load_database(DATA, self.db_path)
        self.assertEqual(check_database(self.db_path), before)

    def test_unlisted_csvs_are_never_ingested(self):
        sources = self.copied_sources()
        (sources / "private_evaluation.csv").write_text("invalid CSV that must not be read")
        load_duckdb.load_database(sources, self.db_path)
        with duckdb.connect(str(self.db_path), read_only=True) as connection:
            names = {row[0] for row in connection.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'raw'"
            ).fetchall()}
        self.assertEqual(names, set(load_duckdb.TABLE_SCHEMAS))

    def test_wholly_missing_cut_is_detected_and_not_reported_as_zero(self):
        with duckdb.connect(str(self.db_path)) as connection:
            connection.execute(f"DELETE FROM raw.rx_weekly WHERE {CLEAN_CUT}")
            self.assertIn("MISSING_RX_KEYS", self.health(connection)[1])
            self.assertEqual(connection.execute(
                f"SELECT missing_key_count FROM reporting.v_feed_health WHERE {CLEAN_CUT}"
            ).fetchone()[0], 128)
            self.assert_cut_withheld(connection)

    def test_missing_key_and_duplicate_are_detected_even_when_counts_balance(self):
        with duckdb.connect(str(self.db_path)) as connection:
            connection.execute(
                f"DELETE FROM raw.rx_weekly WHERE {CLEAN_CUT} "
                "AND plan_id = 'SYN_GREAT_LAKES_CASH_1' "
                "AND hcp_specialty = 'CARDIOLOGY' AND product_id = 'BXA'"
            )
            connection.execute(
                f"INSERT INTO raw.rx_weekly SELECT * FROM raw.rx_weekly WHERE {CLEAN_CUT} LIMIT 1"
            )
            observed, missing, duplicates, reasons = connection.execute(
                "SELECT observed_rows, missing_key_count, duplicate_rows, flag_reasons "
                f"FROM reporting.v_feed_health WHERE {CLEAN_CUT}"
            ).fetchone()
            self.assertEqual((observed, missing, duplicates), (128, 1, 1))
            self.assertIn("MISSING_RX_KEYS", reasons)
            self.assertIn("DUPLICATE_RX_KEYS", reasons)
            self.assert_cut_withheld(connection)

    def test_missing_or_duplicate_metadata_fails_closed(self):
        for mode, reason in (("missing", "MISSING_FEED_METADATA"),
                             ("duplicate", "DUPLICATE_FEED_METADATA")):
            with self.subTest(mode=mode), duckdb.connect(str(self.db_path)) as connection:
                connection.execute("BEGIN")
                try:
                    if mode == "missing":
                        connection.execute(f"DELETE FROM raw.feed_metadata WHERE {CLEAN_CUT}")
                    else:
                        connection.execute(
                            "INSERT INTO raw.feed_metadata SELECT * FROM raw.feed_metadata "
                            f"WHERE {CLEAN_CUT}"
                        )
                    self.assertIn(reason, self.health(connection)[1])
                    self.assert_cut_withheld(connection)
                finally:
                    connection.execute("ROLLBACK")

    def test_missing_and_invalid_metric_values_are_retained_and_flagged(self):
        for value in ("NULL", "-1", "nrx - 1"):
            with self.subTest(value=value), duckdb.connect(str(self.db_path)) as connection:
                connection.execute("BEGIN")
                try:
                    connection.execute(f"UPDATE raw.rx_weekly SET trx = {value} WHERE {CLEAN_CUT}")
                    self.assertIn("INVALID_RX_METRICS", self.health(connection)[1])
                    self.assertEqual(connection.execute(
                        f"SELECT count(*) FROM raw.rx_weekly WHERE {CLEAN_CUT}"
                    ).fetchone()[0], 128)
                    self.assert_cut_withheld(connection)
                finally:
                    connection.execute("ROLLBACK")

    def test_quality_checks_cover_missing_values_and_duplicates_in_other_sources(self):
        with duckdb.connect(str(self.db_path)) as connection:
            connection.execute("UPDATE raw.inventory_weekly SET inventory_fill_rate = NULL "
                               f"WHERE {CLEAN_CUT} AND product_id = 'BXA'")
            connection.execute("UPDATE raw.dim_product SET product_name = NULL WHERE product_id = 'BXA'")
            # Same table row count so manifest reconciliation still passes.
            connection.execute("UPDATE raw.dim_specialty SET hcp_specialty = 'CARDIOLOGY'")
        report = check_database(self.db_path)
        quality = {row["table_name"]: row for row in report["source_quality"]}
        self.assertEqual(quality["inventory_weekly"]["missing_value_rows"], 1)
        self.assertEqual(quality["dim_product"]["missing_value_rows"], 1)
        self.assertEqual(quality["dim_specialty"]["duplicate_key_count"], 1)
        self.assertEqual(quality["dim_specialty"]["duplicate_rows"], 3)

    def test_delivery_coverage_and_schema_checks(self):
        for assignment, reason in (
            ("actual_lag_days = 10", "LATE_OR_UNKNOWN_DELIVERY"),
            ("actual_lag_days = NULL", "LATE_OR_UNKNOWN_DELIVERY"),
            ("panel_coverage_ratio = 0.90", "LOW_OR_INVALID_COVERAGE"),
            ("panel_coverage_ratio = NULL", "LOW_OR_INVALID_COVERAGE"),
            ("schema_version = 'rx_v2'", "UNKNOWN_SCHEMA"),
        ):
            with self.subTest(assignment=assignment), duckdb.connect(str(self.db_path)) as connection:
                connection.execute("BEGIN")
                try:
                    connection.execute(f"UPDATE raw.feed_metadata SET {assignment} WHERE {CLEAN_CUT}")
                    self.assertIn(reason, self.health(connection)[1])
                    self.assert_cut_withheld(connection)
                finally:
                    connection.execute("ROLLBACK")

    def test_checker_detects_manifest_drift(self):
        with duckdb.connect(str(self.db_path)) as connection:
            connection.execute("DELETE FROM raw.dim_product WHERE product_id = 'BXA'")
        with self.assertRaisesRegex(ValueError, "manifest has 4 rows, database has 3"):
            check_database(self.db_path)

    def test_cli_from_another_directory_and_strict_quality_exit_status(self):
        command = [sys.executable, str(ROOT / "src/pharmagentics/data/check_duckdb.py"),
                   "--db-path", str(self.db_path), "--json"]
        result = subprocess.run(command, cwd=self.sandbox.name, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["missing_key_count"], 44)
        strict = subprocess.run(command + ["--fail-on-flags"], capture_output=True, text=True)
        self.assertEqual(strict.returncode, 2, strict.stderr)

    def test_missing_database_is_not_created_by_the_checker(self):
        missing = Path(self.sandbox.name) / "absent.duckdb"
        with self.assertRaisesRegex(FileNotFoundError, "run load_duckdb.py first"):
            check_database(missing)
        self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
