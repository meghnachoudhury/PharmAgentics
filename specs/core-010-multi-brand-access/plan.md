# Implementation plan — core-010

Keep the current Python/FastAPI, React, DuckDB and Keycloak stack. Add an allowlisted product catalog in `tools/brands.py` and account-grant policy in `api/brand_access.py`.

1. Carry a validated `brand_id` through the scripted pipeline's resolved period, primary queries, driver checks, projection, memo and charts. BXA is the default for existing callers. Qualify shared feed failures for both brands.
2. Split sign-in persona claims from brand-grant claims. Intersect release membership, implemented engines and grants for the browser context. Reuse one stored-brand check for brief reads, decisions, threads and votes. Require BXA for Forecast; check owner, brand and scope for agent jobs.
3. Keep BXA IDs stable and add brand to non-BXA brief/triage identities. Validate the engine's returned brand before persistence. BXC agent execution stays refused in both the API and worker.
4. Populate the existing selector from authorized capabilities, preserve the reporting week, reset report/plan/thread/evidence on brand change, and ignore late async results. Show brand IDs on approved rows and existing reports.
5. Test same-role/different-grant users, numeric/evidence correctness, hidden records, queues, plans and flagged cuts. Gate the unchanged BXA scripted suite against main. Document the live Keycloak rollout separately from code deployment.

## Constitution check

- Shared I and Briefing B-IV: all Rx metrics and chart points use governed queries and recorded evidence; no model-generated numbers.
- Shared II: analyst plan review and publication approval remain mandatory; leadership responses retain their allowlists.
- Shared III: no runtime eval imports, no access to private ground truth. Only the requested harness evaluates committed development cases.
- Shared IV and Briefing B-III: explicit typed brands and capabilities; legacy BXA identifiers and pinned versions remain compatible.
- Shared V and feed-health rule: withheld cuts get no story or causal driver; projected/estimated levels retain their assumptions.
- Shared VII: no new agent loop. BXC is scripted-only.
- Briefing B-VII: compare candidate against a pre-change scripted evaluation and require no gated regressions before merge.

No constitutional deviation or new runtime dependency.
