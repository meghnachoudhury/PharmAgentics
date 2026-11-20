# Contract: `reporting.v_rx_projection`

A governed, read-only view in `sql/001_reporting_views.sql`, listed in `Registry.ALLOWED`. Columns and rules are in [data-model.md](../data-model.md#projection-row-reportingv_rx_projection).

## Guarantees

- One row per (`week_start`, `territory_id`, `product_id`) for every cut in `reporting.v_feed_health`.
- `observed_trx` and `projected_trx` are NULL for `basis = 'estimated'`, so a duplicate-key or under-review cut never exposes a level.
- For `basis = 'observed'`, `observed_trx` equals the sum in `reporting.v_weekly_rx_kpis` for that cut.
- The view adds no row to the import manifest, so the data version does not change.

## Consumers

- `pharmagentics.tools.projection` (claims for §1 and §2).
- Golden facts in `eval/golden/briefing/P1-Q2.yaml` and `P3-Q6.yaml`.

## Not for

- Growth, change or driver tests. Those stay on like-for-like cuts in `reporting.v_reportable_rx` (ADR 0001, FR-023).
