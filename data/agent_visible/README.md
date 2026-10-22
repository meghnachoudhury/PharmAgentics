# PharmAgentics: Day 1 synthetic commercial data (v1)

**FICTIONAL DATA — NOT A REAL PHARMA COMPANY, MEDICARE PLAN, PATIENT, NDC OR DRUG.**

## Scope
- Both agent use cases share one data universe.
- Briefing/Surveillance: validate feed data, calculate weekly TRx / NRx / NBRx, market and competitor share, flag material shifts, produce structured handoffs, draft verified brief.
- Forecast Explanation: compare forecast vs actual, query contextual access/promotion/inventory/calendar data, quantify/qualify drivers, return structured evidence with uncertainty.
- No HCP next-best-action or payer causal-effect model is implemented. Formulary/access is contextual to the investigation, not a causal estimate.

## Size
- RNG: `numpy.random.default_rng(7)`.
- 104 Monday-start weeks: 2024-10-14 to 2026-10-05.
- 8 territories, 64 fictional territory-specific plans (4 payer channels), 4 specialties, 4 products (one index brand + three competitors).
- 106,467 observed weekly Rx cells; other tables at their documented grains.

## Most important tables
- `rx_weekly.csv`: **raw observed feed**, may contain missing or duplicated keys; validate before calculations.
- `market_share_weekly.csv`: derived territory competitor share; use only with data-health checks.
- `access_status_monthly.csv`: monthly formulary conditions. Join on `plan_id`, `product_id` and effective month, **not** merely payer channel.
- `promo_activity.csv` and `inventory_weekly.csv`: at week × territory × product, contextual indicators for possible drivers; aggregated only.
- `forecast_vs_actual_weekly.csv`: exactly reconciles *actual_trx* to observed Rx index brand by territory; carries an `actual_is_provisional` warning on bad-feed weeks.
- `feed_metadata.csv` and `restatement_log.csv`: run data-quality screening.

## Important metric semantics
- **TRx**: number of synthetic prescription fills (new + refills).
- **NRx**: synthetic new prescriptions, and modeled as a subset of TRx.
- **NBRx**: synthetic new-to-brand prescriptions, modeled as a subset of NRx (a simplification; real brands require claims-derived lookback definitions).
- `trx_30day_equivalent` is simulated from days-supply mix and is not an independently sourced CMS metric.
- `market_share` is observed volume within this **fictional** four-brand therapy basket, not a real nationwide commercial market share.
- All numbers are synthetic; source schemas do not validate numerical realism.

## Validating data
`DATA_VALIDATION_REPORT.json` records intentionally detected duplicates and missing-cell counts. The observed feed is not clean on purpose: commercial agents should flag questionable inputs, not silently backfill them or treat them as demand shocks.

## Public-source grounding and limits
The publicly documented CMS Medicare Part D Prescriber by Provider & Drug dataset is **annual and Medicare-only**, not weekly all-payer NRx/NBRx/CRM data; CMS monthly plan formularies provide tier/PA/step-therapy structure; openFDA NDC defines product metadata fields. This release is **schema-aligned** and contains purposefully assumed numeric parameters, not a measured statistical fit to those resources.

The forecast model here is a simple planning baseline built from predictable calendar/trend effects, and deliberately excludes unanticipated competitor launch, payer, promotion, and inventory shocks. Forecast variance is an experimental signal, not independently validated industry accuracy.

The generator and hidden answer key are distributed **separately** from this agent-visible directory. Do not give agents access to truth labels or generator internals during scoring.
