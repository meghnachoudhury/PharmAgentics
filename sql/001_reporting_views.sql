-- Provisional Day 1 rules, not yet the governed metrics from Specs 002–004.
-- Every product has a source cell even before launch (with zero counts).
CREATE OR REPLACE VIEW reporting.v_rx_expected_keys AS
SELECT c.week_start, p.territory_id, p.plan_id, s.hcp_specialty, b.product_id
FROM raw.calendar c
CROSS JOIN raw.dim_plan p
CROSS JOIN raw.dim_specialty s
CROSS JOIN raw.dim_product b;

CREATE OR REPLACE VIEW reporting.v_rx_duplicate_keys AS
SELECT week_start, territory_id, plan_id, hcp_specialty, product_id,
       count(*) AS record_count, count(*) - 1 AS duplicate_rows
FROM raw.rx_weekly
GROUP BY week_start, territory_id, plan_id, hcp_specialty, product_id
HAVING count(*) > 1;

-- The anti-join finds missing cells even when duplicates mask a row-count deficit.
CREATE OR REPLACE VIEW reporting.v_rx_missing_keys AS
SELECT e.*
FROM reporting.v_rx_expected_keys e
ANTI JOIN raw.rx_weekly r
USING (week_start, territory_id, plan_id, hcp_specialty, product_id);

CREATE OR REPLACE VIEW reporting.v_feed_health AS
WITH cuts AS (
    -- Include completely absent cuts as well as unexpected input cuts.
    SELECT c.week_start, t.territory_id FROM raw.calendar c CROSS JOIN raw.dim_territory t
    UNION SELECT week_start, territory_id FROM raw.feed_metadata
    UNION SELECT week_start, territory_id FROM raw.rx_weekly
), expected AS (
    SELECT week_start, territory_id, count(*) AS expected_key_count
    FROM reporting.v_rx_expected_keys GROUP BY week_start, territory_id
), observed AS (
    SELECT week_start, territory_id, count(*) AS observed_rows,
           count(*) FILTER (WHERE plan_id IS NULL OR product_id IS NULL
               OR hcp_specialty IS NULL OR trx IS NULL OR nrx IS NULL OR nbrx IS NULL
               OR trx < 0 OR nrx < 0 OR nbrx < 0 OR nrx > trx OR nbrx > nrx
               OR trx_30day_equivalent IS NULL OR NOT isfinite(trx_30day_equivalent)
               OR trx_30day_equivalent < 0) AS invalid_metric_rows
    FROM raw.rx_weekly GROUP BY week_start, territory_id
), missing AS (
    SELECT week_start, territory_id, count(*) AS missing_key_count
    FROM reporting.v_rx_missing_keys GROUP BY week_start, territory_id
), duplicates AS (
    SELECT week_start, territory_id, count(*) AS duplicate_key_count,
           sum(duplicate_rows) AS duplicate_rows
    FROM reporting.v_rx_duplicate_keys GROUP BY week_start, territory_id
), feed AS (
    -- Aggregate metadata first so duplicate metadata never multiplies Rx rows.
    SELECT week_start, territory_id, count(*) AS metadata_row_count,
           max(expected_rows) AS expected_rows, max(received_rows) AS received_rows,
           max(row_count_delta) AS row_count_delta,
           min(panel_coverage_ratio) AS panel_coverage_ratio,
           min(expected_lag_days) AS expected_lag_days,
           max(actual_lag_days) AS actual_lag_days,
           min(loaded_at_utc) AS loaded_at_utc, min(status) AS source_status,
           min(schema_version) AS schema_version,
           max(restatement_flag) AS restatement_flag,
           max(restatement_recorded_at) AS restatement_recorded_at
    FROM raw.feed_metadata GROUP BY week_start, territory_id
), restatements AS (
    SELECT week_start, territory_id, count(*) AS restatement_rows
    FROM raw.restatement_log GROUP BY week_start, territory_id
), evidence AS (
    SELECT c.week_start, c.territory_id,
           coalesce(e.expected_key_count, 0) AS expected_key_count,
           coalesce(o.observed_rows, 0) AS observed_rows,
           coalesce(m.missing_key_count, 0) AS missing_key_count,
           coalesce(d.duplicate_key_count, 0) AS duplicate_key_count,
           coalesce(d.duplicate_rows, 0) AS duplicate_rows,
           coalesce(o.invalid_metric_rows, 0) AS invalid_metric_rows,
           coalesce(f.metadata_row_count, 0) AS metadata_row_count,
           f.expected_rows, f.received_rows, f.row_count_delta,
           f.panel_coverage_ratio, f.expected_lag_days, f.actual_lag_days,
           f.loaded_at_utc, f.source_status, f.schema_version,
           f.restatement_flag, f.restatement_recorded_at,
           coalesce(r.restatement_rows, 0) AS restatement_rows
    FROM cuts c
    LEFT JOIN expected e USING (week_start, territory_id)
    LEFT JOIN observed o USING (week_start, territory_id)
    LEFT JOIN missing m USING (week_start, territory_id)
    LEFT JOIN duplicates d USING (week_start, territory_id)
    LEFT JOIN feed f USING (week_start, territory_id)
    LEFT JOIN restatements r USING (week_start, territory_id)
), reasons AS (
    SELECT *, concat_ws(';',
        CASE WHEN expected_key_count = 0 THEN 'UNEXPECTED_CUT' END,
        CASE WHEN metadata_row_count = 0 THEN 'MISSING_FEED_METADATA' END,
        CASE WHEN metadata_row_count > 1 THEN 'DUPLICATE_FEED_METADATA' END,
        CASE WHEN missing_key_count > 0 THEN 'MISSING_RX_KEYS' END,
        CASE WHEN duplicate_key_count > 0 THEN 'DUPLICATE_RX_KEYS' END,
        CASE WHEN invalid_metric_rows > 0 THEN 'INVALID_RX_METRICS' END,
        CASE WHEN expected_rows IS DISTINCT FROM expected_key_count
               OR received_rows IS DISTINCT FROM observed_rows
               OR observed_rows <> expected_key_count
               OR row_count_delta IS DISTINCT FROM (observed_rows - expected_key_count)
             THEN 'ROW_COUNT_MISMATCH' END,
        CASE WHEN panel_coverage_ratio IS NULL OR NOT isfinite(panel_coverage_ratio)
               OR panel_coverage_ratio < 0.98 OR panel_coverage_ratio > 1
             THEN 'LOW_OR_INVALID_COVERAGE' END,
        -- Source lag is fractional: allow one day beyond the stated target.
        CASE WHEN loaded_at_utc IS NULL OR expected_lag_days IS NULL
               OR actual_lag_days IS NULL OR NOT isfinite(actual_lag_days)
               OR expected_lag_days < 0 OR actual_lag_days < 0
               OR actual_lag_days > expected_lag_days + 1
             THEN 'LATE_OR_UNKNOWN_DELIVERY' END,
        CASE WHEN source_status IS DISTINCT FROM 'COMPLETE' THEN 'SOURCE_NOT_COMPLETE' END,
        CASE WHEN schema_version IS DISTINCT FROM 'rx_v1' THEN 'UNKNOWN_SCHEMA' END,
        CASE WHEN restatement_flag IS DISTINCT FROM 0 OR restatement_rows > 0
               OR restatement_recorded_at IS NOT NULL THEN 'RESTATEMENT_REVIEW' END
    ) AS flag_reasons
    FROM evidence
)
SELECT *, CASE WHEN flag_reasons = '' THEN 'PASS' ELSE 'FLAG' END AS health_status
FROM reasons;

-- Raw records and anomaly views remain queryable. The conservative gate excludes
-- the entire week/territory cut, across products, until its issues are resolved.
CREATE OR REPLACE VIEW reporting.v_reportable_rx AS
SELECT r.* FROM raw.rx_weekly r
JOIN reporting.v_feed_health h USING (week_start, territory_id)
WHERE h.health_status = 'PASS';

CREATE OR REPLACE VIEW reporting.v_weekly_rx_kpis AS
SELECT week_start, territory_id, product_id,
       sum(trx) AS trx, sum(nrx) AS nrx, sum(nbrx) AS nbrx,
       sum(trx_30day_equivalent) AS trx_30day_equivalent,
       count(*) AS source_row_count
FROM reporting.v_reportable_rx
GROUP BY week_start, territory_id, product_id;
