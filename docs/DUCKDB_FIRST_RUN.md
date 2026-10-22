# DuckDB data foundation

This step prepares a persistent local database for future Python analytical tools.
It does not connect to Gemini or implement the planned agent tools.
Use Python **3.11 or newer**. DuckDB is the only third-party dependency; the tests
use Python's built-in `unittest` runner.

## Install, load, and verify

From the repository root on macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

python src/pharmagentics/data/load_duckdb.py
python src/pharmagentics/data/check_duckdb.py
python -m unittest discover -s tests -v
```

On Windows, activate with `.venv\Scripts\Activate.ps1` in PowerShell. All other
Python commands are the same.

The default input is `data/agent_visible/`; the output is
`local/pharmagentics.duckdb`. Default paths are relative to the repository, even
when a script is invoked from another working directory. Override them explicitly
when needed (relative overrides are relative to your current directory):

```bash
python src/pharmagentics/data/load_duckdb.py \
  --data-dir /path/to/PharmAgentics_Day1_Agent_Visible_Data \
  --db-path /path/to/local/pharmagentics.duckdb
python src/pharmagentics/data/check_duckdb.py \
  --db-path /path/to/local/pharmagentics.duckdb --json
```

No service, external API, credentials, or API keys are needed. The database and
virtual environment are ignored by Git; the supplied synthetic source files are
versioned so a fresh checkout has everything needed to reproduce this step.

## Data provenance and scope

The 14 CSVs and accompanying README, dictionary, and validation report were copied
byte-for-byte from `Data/PharmAgentics_Day1_Agent_Visible_Data/` in the supplied
`drive-download-20261021T172122Z-1-001.zip`. The archive's private evaluation
directory and unrelated presentation documents are not included or ingested.
The loader reads an explicit list of filenames, not all CSVs it finds nearby.

These are fictional, schema-aligned commercial data, not real patients,
prescribers, products, or calibrated industry measurements. Read the
[source README](../data/agent_visible/README.md) and
[data dictionary](../data/agent_visible/data_dictionary.json) for metric meanings
and limits.

## Database layout and repeat imports

| Schema | Contents |
| --- | --- |
| `raw` | All 14 CSVs as typed source tables, including duplicates and NULL values |
| `metadata` | Successful import runs, source filenames, row counts, sizes, and exact-byte SHA-256 fingerprints |
| `reporting` | Expected/missing Rx keys, duplicate Rx keys, feed health, reportable rows, and weekly KPIs |

Dates, counts, booleans, and numeric measures have explicit types. Empty source
fields become SQL NULL. `market_basket.launch_date` stays text because its source
also contains `BEFORE_*` sentinels. The manifest fingerprints the original bytes.

Each import replaces the 14 raw tables and reporting views in one transaction.
Rerunning the loader does not append duplicate source data. It adds a new audit
run and 14 manifest entries; previous successful manifests remain available.
Missing files, unexpected headers, invalid types, changing files during ingestion,
or SQL errors fail the import without replacing a previously successful load.
Parsing errors are never ignored. Missing or duplicate records that are valid CSV
data are retained for the checks below; the loader never backfills, deduplicates,
or applies restatements automatically.

Run imports before opening long-lived analytical connections. Close those
connections before reloading; DuckDB's normal process-level locking applies.

## Missing and duplicate data checks

`check_duckdb.py` verifies all 14 source row counts against the latest completed
manifest and checks required fields, empty tables, and duplicate natural keys
across every table. All fields are required in this release except the optional
`feed_metadata.restatement_recorded_at`. Natural keys are defined in `TABLE_KEYS`
in the loader; a restatement's key includes its revision date, and a forecast's
key includes its issue week and horizon.

Rx missing cells are calculated independently of the feed's advertised row count:
the expected key universe is `calendar × dim_plan × dim_specialty × dim_product`.
The Rx composite key is `(week_start, territory_id, plan_id, hcp_specialty,
product_id)`. This release contains a cell for every product even before launch,
when its volume is zero. A zero-volume cell is not missing. This check also
detects a missing key when an unrelated duplicate keeps the total count unchanged.
Completely absent week/territory cuts and missing/duplicate feed metadata are
flagged explicitly.

The supplied release must show:

| Check | Expected result |
| --- | --- |
| Source tables | 14 |
| Observed Rx rows | 106,467 |
| Expected unique Rx cells | 106,496 |
| Missing Rx keys | 44 |
| Duplicate Rx keys / excess rows | 15 / 15 |
| `2026-05-04 / NEW_ENGLAND` | Missing keys, incomplete and late feed, low coverage |
| `2026-07-06 / GREAT_LAKES` | Duplicate keys and excess rows |
| `2026-04-06 / MID_ATLANTIC` | Restatement requires review |

The 44 missing cells and 15 extra rows explain `106,496 - 44 + 15 = 106,467`.
They are intentional test cases, not installation failures.

The default checker exits **0** when import verification completes, even when it
reports these expected artifacts. Use `--json` for every missing and duplicate Rx
key plus all source-quality results, or query the evidence views directly. Use
`--fail-on-flags` for a strict data-quality gate: it exits **2** if feed or
source-quality issues exist (expected for the supplied release). Missing databases,
manifest mismatches, or SQL errors exit **1**. Neither check mode modifies data.

```sql
SELECT * FROM reporting.v_rx_missing_keys
ORDER BY week_start, territory_id, plan_id, hcp_specialty, product_id;

SELECT * FROM reporting.v_rx_duplicate_keys
ORDER BY week_start, territory_id, plan_id, hcp_specialty, product_id;

SELECT week_start, territory_id, expected_key_count, observed_rows,
       missing_key_count, duplicate_key_count, duplicate_rows, flag_reasons
FROM reporting.v_feed_health
WHERE health_status = 'FLAG'
ORDER BY week_start, territory_id;
```

## Reportable KPI rules

`reporting.v_feed_health` includes every expected week/territory cut and any extra
cut found in the inputs. The provisional gate requires:

- Exactly one metadata record with `COMPLETE` status and schema `rx_v1`.
- Advertised and independently expected row counts that reconcile to observed
  rows, with no missing keys, duplicate keys, or invalid Rx metrics.
- Panel coverage between **0.98 and 1.0**, inclusive.
- Known, nonnegative delivery lag no more than **one day** beyond the stated
  target. The day of tolerance accommodates the normal fractional 7.29-day lag.
- No restatement flag, recorded restatement date, or matching restatement-log rows.

Required Rx metric checks reject NULL/negative counts, `NRx > TRx`, `NBRx > NRx`,
and missing, negative, or non-finite normalized fills. Issues are labeled in
`flag_reasons`; multiple reasons are retained.

The whole affected week/territory cut is excluded from `v_reportable_rx` and
`v_weekly_rx_kpis` across all products. Its raw records and anomaly evidence
remain queryable. The restatement cut is withheld conservatively, not silently
revised. Other source-table quality issues are reported separately; these initial
Rx KPI views do not use inventory, access, promotion, or forecast inputs.

Weekly KPIs have grain `week_start × territory_id × product_id`:

```python
import duckdb

with duckdb.connect("local/pharmagentics.duckdb", read_only=True) as connection:
    rows = connection.execute("""
        SELECT week_start, territory_id,
               SUM(trx) AS total_trx, SUM(nrx) AS total_nrx, SUM(nbrx) AS total_nbrx
        FROM reporting.v_weekly_rx_kpis
        WHERE product_id = 'BXA'
        GROUP BY week_start, territory_id
        ORDER BY week_start, territory_id
    """).fetchall()
```

Do not interpret an excluded cut as zero demand, or a sum over remaining
territories as a complete national total. The raw market-share and forecast
tables contain provisional measures and are not reportable replacements for the
gated Rx view. Final governed metrics and validation rules from Specs 002–004
remain future work; these initial thresholds are deliberately documented here.

## Test coverage

The integration suite loads the actual release into temporary databases. It
compares missing/duplicate keys and all reportable TRx/NRx/NBRx aggregates against
independent Python CSV calculations, verifies manifests and explicit types,
and tests repeat imports, rollback, allowlisted ingestion, complete missing cuts,
balanced missing/duplicate counts, NULL/invalid metrics, metadata defects,
freshness/coverage gates, CLI behavior, and read-only verification.
